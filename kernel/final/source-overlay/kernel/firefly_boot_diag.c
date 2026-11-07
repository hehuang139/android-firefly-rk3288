// SPDX-License-Identifier: GPL-2.0
/* Temporary, one-shot Firefly RK3288 boot recorder. No printk or UART input. */
#include <linux/atomic.h>
#include <linux/cpu.h>
#include <linux/firefly_boot_diag.h>
#include <linux/hrtimer.h>
#include <linux/init.h>
#include <linux/io.h>
#include <linux/irq.h>
#include <linux/of.h>
#include <linux/percpu.h>
#include <linux/pid.h>
#include <linux/sched.h>
#include <linux/smp.h>
#include <linux/string.h>
#include <linux/timekeeping.h>
#include <asm/irq_regs.h>
#include <asm/ptrace.h>

#define ABD_RING 64
#define ABD_PRINT_MARKS 32
#define ABD_TICK_NS (250ULL * NSEC_PER_MSEC)
#define ABD_TIMEOUT_NS (30ULL * NSEC_PER_SEC)
#define ABD_UART_PHYS 0xff690000
#define ABD_UART_LCR 0x0c
#define ABD_UART_LSR 0x14
#define ABD_POLL_PER_CHAR 20000U
#define ABD_POLL_TOTAL 32000000U

struct abd_mark {
	u32 seq, tag, pid, irq_flags;
	unsigned long a, b, caller;
};

struct abd_snapshot {
	u32 valid, heartbeat, pid, regs_valid;
	u32 pc, lr, sp, fp, cpsr;
	u32 mark_head;
	struct abd_mark marks[ABD_RING];
	struct abd_mark sticky[5];
};

struct abd_cpu {
	struct hrtimer timer;
	call_single_data_t csd;
	u32 heartbeat, last_pc, last_lr, mark_head;
	struct abd_mark marks[ABD_RING];
	struct abd_mark sticky[5];
	struct abd_snapshot snapshot;
};

static DEFINE_PER_CPU(struct abd_cpu, abd_cpus);
/* The emitting CPU freezes all received/live evidence here before UART I/O. */
static struct abd_snapshot abd_dump[NR_CPUS];
static u32 abd_online_mask, abd_seen_mask, abd_last_pc[NR_CPUS];
static u32 abd_last_lr[NR_CPUS];
static atomic_t abd_phase = ATOMIC_INIT(0);
static u64 abd_deadline, abd_collect_deadline;
static bool abd_ready;
static void __iomem *abd_uart;
static unsigned int abd_poll_budget;
static bool abd_uart_failed;


/* Synchronous VIDEO boundary trace, independent of printk and ABD timers.
 * No global lock, shared output buffer, timekeeping, allocation or clock write.
 * Every call gets a fresh bounded budget: one timeout cannot hide later calls.
 * Other CPUs may interleave bytes. Even bounded polling cannot rescue a single
 * stalled MMIO transaction; successful complete lines are positive evidence.
 */
#define ABD_RAW_POLL_LINE 1000000U
#define ABD_RAW_TEXT_MAX 192U

struct abd_raw_text {
	char text[ABD_RAW_TEXT_MAX];
	unsigned int used;
};

static void notrace abd_raw_string(struct abd_raw_text *out, const char *s,
				  unsigned int limit)
{
	while (s && *s && limit-- && out->used < sizeof(out->text))
		out->text[out->used++] = *s++;
}

static void notrace abd_raw_hex(struct abd_raw_text *out, u32 value)
{
	static const char digits[] = "0123456789abcdef";
	int shift;

	for (shift = 28; shift >= 0 && out->used < sizeof(out->text); shift -= 4)
		out->text[out->used++] = digits[(value >> shift) & 0xf];
}

void notrace firefly_boot_diag_raw(const char *layer, const char *name, int on,
				 const char *mark)
{
	struct abd_raw_text out = { .used = 0 };
	void __iomem *uart = READ_ONCE(abd_uart);
	unsigned long flags;
	unsigned int i, n, budget = ABD_RAW_POLL_LINE;

	if (!uart)
		return;
	/* Keep the CPU/PID stable and avoid same-CPU nesting; never wait for CPUs. */
	local_irq_save(flags);
	abd_raw_string(&out, "\r\n#V ", 5);
	abd_raw_string(&out, layer, 4);
	abd_raw_string(&out, " cpu=", 5);
	abd_raw_hex(&out, raw_smp_processor_id());
	abd_raw_string(&out, " pid=", 5);
	abd_raw_hex(&out, task_pid_nr(current));
	abd_raw_string(&out, " on=", 4);
	abd_raw_string(&out, on < 0 ? "-" : on ? "1" : "0", 1);
	abd_raw_string(&out, " ", 1);
	abd_raw_string(&out, name, 32);
	abd_raw_string(&out, " ", 1);
	abd_raw_string(&out, mark, 80);
	abd_raw_string(&out, "\r\n", 2);
	for (i = 0; i < out.used; i++) {
		for (n = 0; n < ABD_POLL_PER_CHAR && budget; n++) {
			budget--;
			if (readl_relaxed(uart + ABD_UART_LCR) & 0x80)
				goto done;
			if (readl_relaxed(uart + ABD_UART_LSR) & 0x20)
				break;
			cpu_relax();
		}
		if (n == ABD_POLL_PER_CHAR || !budget)
			goto done;
		writel_relaxed((u8)out.text[i], uart);
	}
	/* Drain the final character before the operation this line precedes. */
	for (n = 0; n < ABD_POLL_PER_CHAR && budget; n++, budget--) {
		if (readl_relaxed(uart + ABD_UART_LSR) & 0x40)
			break;
		cpu_relax();
	}
done:
	local_irq_restore(flags);
}

void notrace firefly_boot_diag_mark(u32 tag, unsigned long a, unsigned long b)
{
	struct abd_cpu *c;
	struct abd_mark *m, *last;
	unsigned long flags;
	u32 seq;

	if (!READ_ONCE(abd_ready))
		return;
	local_irq_save(flags);
	c = this_cpu_ptr(&abd_cpus);
	seq = c->mark_head + 1;
	m = &c->marks[(seq - 1) % ABD_RING];
	WRITE_ONCE(m->seq, 0);
	smp_wmb();
	WRITE_ONCE(m->tag, tag);
	WRITE_ONCE(m->pid, task_pid_nr(current));
	WRITE_ONCE(m->irq_flags, flags);
	WRITE_ONCE(m->a, a);
	WRITE_ONCE(m->b, b);
	WRITE_ONCE(m->caller, (unsigned long)__builtin_return_address(0));
	smp_wmb();
	WRITE_ONCE(m->seq, seq);
	/* UART polling must not evict the last initcall/genpd/printk boundary. */
	if ((tag >> 12) >= 1 && (tag >> 12) <= 4) {
		last = &c->sticky[tag >> 12];
		WRITE_ONCE(last->seq, 0);
		smp_wmb();
		WRITE_ONCE(last->tag, tag);
		WRITE_ONCE(last->pid, task_pid_nr(current));
		WRITE_ONCE(last->irq_flags, flags);
		WRITE_ONCE(last->a, a);
		WRITE_ONCE(last->b, b);
		WRITE_ONCE(last->caller, m->caller);
		smp_wmb();
		WRITE_ONCE(last->seq, seq);
	}
	WRITE_ONCE(c->mark_head, seq);
	local_irq_restore(flags);
}

/* Bounded stable-copy check: a racing entry is marked invalid, never retried. */
static void notrace abd_copy_marks(struct abd_snapshot *out, struct abd_cpu *c)
{
	unsigned int i;
	u32 seq;

	out->mark_head = READ_ONCE(c->mark_head);
	for (i = 0; i < ABD_RING + 4; i++) {
		struct abd_mark *dst = i < ABD_RING ? &out->marks[i] :
			&out->sticky[i - ABD_RING + 1];
		struct abd_mark *src = i < ABD_RING ? &c->marks[i] :
			&c->sticky[i - ABD_RING + 1];

		seq = READ_ONCE(src->seq);
		smp_rmb();
		dst->tag = READ_ONCE(src->tag);
		dst->pid = READ_ONCE(src->pid);
		dst->irq_flags = READ_ONCE(src->irq_flags);
		dst->a = READ_ONCE(src->a);
		dst->b = READ_ONCE(src->b);
		dst->caller = READ_ONCE(src->caller);
		smp_rmb();
		dst->seq = seq == READ_ONCE(src->seq) ? seq : 0;
	}
}

/* Runs with local IRQs disabled in a timer/IPI; no allocation or sleeping lock. */
static void notrace abd_capture(void *unused)
{
	struct abd_cpu *c = this_cpu_ptr(&abd_cpus);
	struct abd_snapshot *s = &c->snapshot;
	struct pt_regs *regs = get_irq_regs();

	if (smp_load_acquire(&s->valid))
		return;
	s->heartbeat = READ_ONCE(c->heartbeat);
	s->pid = task_pid_nr(current);
	s->regs_valid = !!regs;
	if (regs) {
		s->pc = regs->ARM_pc;
		s->lr = regs->ARM_lr;
		s->sp = regs->ARM_sp;
		s->fp = regs->ARM_fp;
		s->cpsr = regs->ARM_cpsr;
	}
	abd_copy_marks(s, c);
	smp_store_release(&s->valid, 1);
}

/* Only TX, LSR, and LCR are accessed. Never change IER, clock, or UART format.
 * Poll loops have hard iteration limits. A stalled MMIO bus transaction itself
 * cannot be bounded in software. Concurrent normal UART output may interleave.
 */
static void notrace abd_putc(char ch)
{
	unsigned int n;

	if (abd_uart_failed)
		return;
	for (n = 0; n < ABD_POLL_PER_CHAR && abd_poll_budget; n++) {
		abd_poll_budget--;
		if (readl_relaxed(abd_uart + ABD_UART_LCR) & 0x80) {
			abd_uart_failed = true;
			return;
		}
		if (readl_relaxed(abd_uart + ABD_UART_LSR) & 0x20) {
			writel_relaxed((u8)ch, abd_uart);
			return;
		}
		cpu_relax();
	}
	abd_uart_failed = true;
}

static void notrace abd_puts(const char *s)
{
	while (*s && !abd_uart_failed)
		abd_putc(*s++);
}

static void notrace abd_hex(u32 value)
{
	static const char digits[] = "0123456789abcdef";
	int shift;

	for (shift = 28; shift >= 0 && !abd_uart_failed; shift -= 4)
		abd_putc(digits[(value >> shift) & 0xf]);
}

static void notrace abd_field(const char *name, u32 value)
{
	abd_puts(name);
	abd_hex(value);
}

static void notrace abd_emit(void)
{
	unsigned int cpu, i;

	/* Freeze every slot before output; the recorder never uses printk itself. */
	for_each_online_cpu(cpu) {
		struct abd_cpu *c = per_cpu_ptr(&abd_cpus, cpu);
		struct abd_snapshot *s = &abd_dump[cpu];

		abd_online_mask |= BIT(cpu);
		abd_last_pc[cpu] = READ_ONCE(c->last_pc);
		abd_last_lr[cpu] = READ_ONCE(c->last_lr);
		if (smp_load_acquire(&c->snapshot.valid)) {
			memcpy(s, &c->snapshot, sizeof(*s));
			abd_seen_mask |= BIT(cpu);
		} else {
			s->heartbeat = READ_ONCE(c->heartbeat);
			abd_copy_marks(s, c);
		}
	}
	abd_poll_budget = ABD_POLL_TOTAL;
	abd_puts("\r\n### ABD BEGIN v1 all_values_hex\r\n");
	abd_field("ABD online=", abd_online_mask);
	abd_field(" responded=", abd_seen_mask);
	abd_field(" emitter=", raw_smp_processor_id());
	abd_puts("\r\n");
	for_each_online_cpu(cpu) {
		struct abd_snapshot *s = &abd_dump[cpu];

		abd_field("ABD CPU=", cpu);
		abd_field(" response=", s->valid);
		abd_field(" heartbeat=", s->heartbeat);
		abd_field(" last_pc=", abd_last_pc[cpu]);
		abd_field(" last_lr=", abd_last_lr[cpu]);
		abd_puts("\r\n");
		abd_field("ABD REG pid=", s->pid);
		abd_field(" valid=", s->regs_valid);
		abd_field(" pc=", s->pc);
		abd_field(" lr=", s->lr);
		abd_field(" sp=", s->sp);
		abd_field(" fp=", s->fp);
		abd_field(" cpsr=", s->cpsr);
		abd_puts("\r\n");
	}
	/* Sticky classes are printed before UART-heavy ring history. */
	for_each_online_cpu(cpu) {
		for (i = 1; i <= 4; i++) {
			struct abd_mark *m = &abd_dump[cpu].sticky[i];

			abd_field("ABD LAST cpu=", cpu);
			abd_field(" class=", i);
			abd_field(" seq=", m->seq);
			abd_field(" tag=", m->tag);
			abd_field(" pid=", m->pid);
			abd_field(" irq=", m->irq_flags);
			abd_field(" a=", m->a);
			abd_field(" b=", m->b);
			abd_field(" caller=", m->caller);
			abd_puts("\r\n");
		}
	}
	/* Core evidence from every CPU precedes the longer marker history. */
	for_each_online_cpu(cpu) {
		struct abd_snapshot *s = &abd_dump[cpu];
		u32 count = min_t(u32, s->mark_head, ABD_PRINT_MARKS);
		u32 first = s->mark_head - count + 1;

		abd_field("ABD RING cpu=", cpu);
		abd_field(" head=", s->mark_head);
		abd_puts("\r\n");
		for (i = 0; i < count && !abd_uart_failed; i++) {
			u32 seq = first + i;
			struct abd_mark *m = &s->marks[(seq - 1) % ABD_RING];

			abd_field("ABD M seq=", seq);
			abd_field(" ok=", m->seq == seq);
			abd_field(" tag=", m->tag);
			abd_field(" pid=", m->pid);
			abd_field(" irq=", m->irq_flags);
			abd_field(" a=", m->a);
			abd_field(" b=", m->b);
			abd_field(" caller=", m->caller);
			abd_puts("\r\n");
		}
	}
	abd_puts("### ABD END\r\n");
}

static enum hrtimer_restart notrace abd_tick(struct hrtimer *timer)
{
	struct abd_cpu *c = this_cpu_ptr(&abd_cpus);
	struct pt_regs *regs = get_irq_regs();
	u64 now = ktime_get_mono_fast_ns();
	unsigned int cpu;
	int phase;

	WRITE_ONCE(c->heartbeat, c->heartbeat + 1);
	if (regs) {
		WRITE_ONCE(c->last_pc, regs->ARM_pc);
		WRITE_ONCE(c->last_lr, regs->ARM_lr);
	}
	phase = atomic_read(&abd_phase);
	if (!phase && now >= abd_deadline &&
	    atomic_cmpxchg(&abd_phase, 0, -1) == 0) {
		/* Initiate, never wait for CPUs with interrupts disabled. */
		abd_capture(NULL);
		for_each_online_cpu(cpu) {
			if (cpu == raw_smp_processor_id())
				continue;
			smp_call_function_single_async(cpu, &per_cpu(abd_cpus, cpu).csd);
		}
		WRITE_ONCE(abd_collect_deadline, now + ABD_TICK_NS);
		atomic_set_release(&abd_phase, 1);
	}
	phase = atomic_read_acquire(&abd_phase);
	if (phase == 1 && now >= READ_ONCE(abd_collect_deadline) &&
	    atomic_cmpxchg(&abd_phase, 1, 2) == 1) {
		abd_emit();
		atomic_set(&abd_phase, 3);
	}
	if (atomic_read(&abd_phase) >= 2)
		return HRTIMER_NORESTART;
	hrtimer_forward_now(timer, ns_to_ktime(ABD_TICK_NS));
	return HRTIMER_RESTART;
}

static void __init abd_start_cpu(void *unused)
{
	struct abd_cpu *c = this_cpu_ptr(&abd_cpus);

	INIT_CSD(&c->csd, abd_capture, NULL);
	hrtimer_setup(&c->timer, abd_tick, CLOCK_MONOTONIC, HRTIMER_MODE_REL_HARD);
	hrtimer_start(&c->timer, ns_to_ktime(ABD_TICK_NS), HRTIMER_MODE_REL_PINNED_HARD);
}

static int __init firefly_boot_diag_init(void)
{
	if (!of_machine_is_compatible("firefly,firefly-rk3288"))
		return 0;
	abd_uart = ioremap(ABD_UART_PHYS, 0x100);
	if (!abd_uart)
		return -ENOMEM;
	abd_deadline = ktime_get_mono_fast_ns() + ABD_TIMEOUT_NS;
	WRITE_ONCE(abd_ready, true);
	on_each_cpu(abd_start_cpu, NULL, 1);
	abd_poll_budget = ABD_POLL_TOTAL;
	abd_puts("\r\n### ABD ARMED delay_seconds=30 receive_only\r\n");
	/* A busy UART during the early acknowledgement must not cancel capture. */
	abd_uart_failed = false;
	firefly_boot_diag_raw("BOOT", "video-hevc-trace", -1, "armed_v2");
	return 0;
}
core_initcall(firefly_boot_diag_init);
