/* SPDX-License-Identifier: GPL-2.0 */
#ifndef _LINUX_FIREFLY_BOOT_DIAG_H
#define _LINUX_FIREFLY_BOOT_DIAG_H

#include <linux/types.h>

/* Temporary RK3288 diagnostic: local preallocated RAM only, never printk. */
void firefly_boot_diag_mark(u32 tag, unsigned long a, unsigned long b);

/* Temporary synchronous raw UART boundary trace; no printk or timekeeping. */
void firefly_boot_diag_raw(const char *layer, const char *name, int on,
			   const char *mark);

#endif
