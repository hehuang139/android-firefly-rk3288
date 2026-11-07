#!/usr/bin/env python3
"""Run the real CEC input source against deterministic adapter/syscall fixtures."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    port = Path(__file__).resolve().parents[1]
    remote = port / 'device/firefly/rk3288/remote'
    with tempfile.TemporaryDirectory(prefix='firefly-cec-') as name:
        work = Path(name)
        headers = work / 'android-base'
        headers.mkdir()
        (headers / 'logging.h').write_text(r'''
#pragma once
struct FixtureLog {
    template<class T> FixtureLog& operator<<(const T&) { return *this; }
};
#define LOG(...) FixtureLog{}
#define PLOG(...) FixtureLog{}
''')
        (headers / 'unique_fd.h').write_text(r'''
#pragma once
#include <unistd.h>
namespace android::base {
class unique_fd {
    int fd_;
  public:
    explicit unique_fd(int fd): fd_(fd) {}
    ~unique_fd() { if (fd_ >= 0) close(fd_); }
    operator int() const { return fd_; }
    int get() const { return fd_; }
};
}
''')
        source = work / 'fixture.cpp'
        source.write_text(r'''
#include <cassert>
#include <cstdarg>
#include <iostream>
#include <string>
#define main firefly_cec_main
#include "FireflyCecInput.cpp"
#undef main

cec_log_addrs state{};
int claims, clears, clearAttempts, busy, interrupted;
bool absent, capabilityMissing, pollFailure, clearFailure, replaceOwner, removed;
int signalNumber;

cec_log_addrs owned() {
    cec_log_addrs result{};
    result.cec_version = CEC_OP_CEC_VERSION_1_4;
    result.num_log_addrs = 1;
    result.vendor_id = CEC_VENDOR_ID_NONE;
    result.flags = CEC_LOG_ADDRS_FL_ALLOW_RC_PASSTHRU;
    result.log_addr_type[0] = CEC_LOG_ADDR_TYPE_PLAYBACK;
    result.primary_device_type[0] = CEC_OP_PRIM_DEVTYPE_PLAYBACK;
    result.log_addr[0] = CEC_LOG_ADDR_PLAYBACK_1;
    result.log_addr_mask = 1 << CEC_LOG_ADDR_PLAYBACK_1;
    strcpy(result.osd_name, "Firefly TV");
    return result;
}
extern "C" int __wrap_open(const char*, int, ...) {
    if (absent) { errno = ENOENT; return -1; }
    return 100;
}
extern "C" int __wrap_close(int) { return 0; }
extern "C" int __wrap_signalfd(int, const sigset_t*, int) { return 101; }
extern "C" int __wrap_sigprocmask(int, const sigset_t*, sigset_t*) { return 0; }
extern "C" int __wrap_usleep(useconds_t) { return 0; }
extern "C" int __wrap_ioctl(int, unsigned long request, ...) {
    va_list list;
    va_start(list, request);
    void* argument = va_arg(list, void*);
    va_end(list);
    if (request == CEC_ADAP_G_CAPS) {
        auto* caps = static_cast<cec_caps*>(argument);
        caps->capabilities = capabilityMissing ? 0 :
                CEC_CAP_LOG_ADDRS | CEC_CAP_TRANSMIT | CEC_CAP_RC;
        return 0;
    }
    if (request == CEC_ADAP_G_LOG_ADDRS) {
        if (removed) { errno = ENODEV; return -1; }
        *static_cast<cec_log_addrs*>(argument) = state;
        return 0;
    }
    if (request == CEC_ADAP_S_LOG_ADDRS) {
        const auto& desired = *static_cast<cec_log_addrs*>(argument);
        if (desired.num_log_addrs) {
            claims++;
            state = desired;
            state.log_addr[0] = CEC_LOG_ADDR_PLAYBACK_1;
            state.log_addr_mask = 1 << CEC_LOG_ADDR_PLAYBACK_1;
        } else {
            clearAttempts++;
            if (busy-- > 0) { errno = EBUSY; return -1; }
            if (clearFailure) { errno = EIO; return -1; }
            clears++;
            // Linux __cec_s_log_addrs(0) unconfigures logical addresses but
            // retains flags. No address mask means RC messages are ignored.
            state.num_log_addrs = 0;
            state.log_addr_mask = 0;
            memset(state.log_addr, CEC_LOG_ADDR_INVALID, sizeof(state.log_addr));
            state.osd_name[0] = '\0';
            state.vendor_id = CEC_VENDOR_ID_NONE;
            state.cec_version = CEC_OP_CEC_VERSION_2_0;
        }
        return 0;
    }
    errno = EAGAIN;
    return -1;
}
extern "C" int __wrap_poll(pollfd* descriptors, nfds_t count, int) {
    assert(count == 2);
    if (interrupted-- > 0) { errno = EINTR; return -1; }
    if (pollFailure) { errno = EIO; return -1; }
    if (replaceOwner) strcpy(state.osd_name, "Other player");
    descriptors[1].revents = POLLIN;
    return 1;
}
extern "C" ssize_t __wrap_read(int fd, void* data, size_t size) {
    assert(fd == 101 && size == sizeof(signalfd_siginfo));
    static_cast<signalfd_siginfo*>(data)->ssi_signo = signalNumber;
    return sizeof(signalfd_siginfo);
}

void reset() {
    state = {};
    claims = clears = clearAttempts = busy = interrupted = 0;
    absent = capabilityMissing = pollFailure = clearFailure = replaceOwner = removed = false;
    signalNumber = SIGTERM;
}
void expect(const char* name, int code, int expectedClaims, int expectedClears) {
    assert(firefly_cec_main() == code);
    assert(claims == expectedClaims && clears == expectedClears);
    std::cout << name << '\n';
}
int main() {
    reset(); expect("SIGTERM clears logical addresses to disable RC input", 0, 1, 1);
    assert(state.num_log_addrs == 0 && state.log_addr_mask == 0);
    reset(); signalNumber = SIGINT;
    expect("SIGINT clears logical addresses to disable RC input", 0, 1, 1);
    reset(); state = owned();
    expect("Reclaims Firefly configuration after an earlier crash", 0, 0, 1);
    reset(); state = owned(); strcpy(state.osd_name, "Other player");
    expect("Preserves another player's pre-existing configuration", 1, 0, 0);
    reset(); replaceOwner = true;
    expect("Preserves another player's replacement configuration", 0, 1, 0);
    reset(); busy = 2;
    expect("Retries temporary EBUSY during address release", 0, 1, 1);
    assert(clearAttempts == 3);
    reset(); interrupted = 1;
    expect("Interrupted poll still handles the pending shutdown", 0, 1, 1);
    reset(); pollFailure = true;
    expect("Poll failure releases its owned address", 1, 1, 1);
    reset(); clearFailure = true;
    expect("Release failure returns an error", 1, 1, 0);
    reset(); absent = true;
    expect("Missing adapter leaves configuration untouched", 1, 0, 0);
    reset(); capabilityMissing = true;
    expect("Missing RC capability leaves configuration untouched", 1, 0, 0);
    reset(); removed = true;
    assert(firefly::cec::releaseAddress(100));
    std::cout << "Removed adapter requires no further cleanup\n";
}
''')
        executable = work / 'fixture'
        wrappers = ['open', 'close', 'signalfd', 'sigprocmask', 'usleep', 'ioctl', 'poll', 'read']
        command = [os.environ.get('CXX', 'c++'), '-std=c++20', '-Wall', '-Wextra', '-Werror',
                   '-I' + str(work), '-I' + str(remote), str(source), '-o', str(executable)]
        command.extend('-Wl,--wrap=' + value for value in wrappers)
        build = subprocess.run(command, capture_output=True, text=True)
        if build.returncode:
            raise RuntimeError(build.stdout + build.stderr)
        result = subprocess.run([str(executable)], capture_output=True, text=True, timeout=10)
        checks = [{'name': value, 'passed': True} for value in result.stdout.splitlines()]
        if result.returncode or len(checks) != 12:
            raise RuntimeError('Fixture failed: ' + result.stdout + result.stderr)
        inputs = [remote / 'FireflyCecInput.cpp', remote / 'CecConfiguration.h']
        report = {
            'scope': 'Real FireflyCecInput.cpp compiled on host; mocked CEC adapter/syscalls',
            'checks': checks, 'passed': len(checks), 'failed': 0,
            'inputs': {str(value.relative_to(port)): hashlib.sha256(value.read_bytes()).hexdigest()
                       for value in inputs},
            'compiler': command[0],
        }
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps({'passed': len(checks), 'failed': 0}))


if __name__ == '__main__':
    main()
