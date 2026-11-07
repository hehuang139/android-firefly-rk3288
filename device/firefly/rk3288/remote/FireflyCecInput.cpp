// SPDX-License-Identifier: Apache-2.0
// Claim a playback logical address and let Linux CEC/rc-core emit input keys.
// Android HDMI system control, ARC and protected content are separate features.
#include <cerrno>
#include <cstring>
#include <fcntl.h>
#include <linux/cec.h>
#include <poll.h>
#include <signal.h>
#include <sys/ioctl.h>
#include <sys/signalfd.h>
#include <unistd.h>
#include <android-base/logging.h>
#include <android-base/unique_fd.h>
#include "CecConfiguration.h"

namespace {

int run(int fd, int signalFd) {
    LOG(INFO) << "Firefly HDMI CEC input enabled; TV must enable CEC on this HDMI input";
    for (;;) {
        pollfd descriptors[] = {{fd, POLLPRI, 0}, {signalFd, POLLIN, 0}};
        int ready = poll(descriptors, 2, -1);
        if (ready < 0 && errno == EINTR) continue;
        if (ready < 0) return 1;
        if (descriptors[1].revents & POLLIN) {
            signalfd_siginfo info{};
            if (read(signalFd, &info, sizeof(info)) == sizeof(info)) return 0;
        }
        for (const auto& descriptor : descriptors) {
            if (descriptor.revents & (POLLERR | POLLHUP | POLLNVAL)) return 1;
        }
        if (descriptors[0].revents & POLLPRI) {
            cec_event event{};
            while (ioctl(fd, CEC_DQEVENT, &event) == 0) {
                if (event.event == CEC_EVENT_STATE_CHANGE) {
                    LOG(INFO) << "CEC physical address=" << event.state_change.phys_addr
                              << " logical mask=" << event.state_change.log_addr_mask;
                }
            }
        }
    }
}

}  // namespace

int main() {
    sigset_t signals;
    sigemptyset(&signals);
    sigaddset(&signals, SIGTERM);
    sigaddset(&signals, SIGINT);
    if (sigprocmask(SIG_BLOCK, &signals, nullptr) != 0) return 1;
    android::base::unique_fd signalFd(signalfd(-1, &signals, SFD_NONBLOCK | SFD_CLOEXEC));
    if (signalFd < 0) return 1;
    android::base::unique_fd fd(open("/dev/cec0", O_RDWR | O_NONBLOCK | O_CLOEXEC));
    if (fd < 0) {
        PLOG(ERROR) << "Open Firefly HDMI CEC adapter";
        return 1;
    }
    cec_caps caps{};
    constexpr uint32_t required = CEC_CAP_LOG_ADDRS | CEC_CAP_TRANSMIT | CEC_CAP_RC;
    if (ioctl(fd, CEC_ADAP_G_CAPS, &caps) != 0 || (caps.capabilities & required) != required) {
        LOG(ERROR) << "HDMI CEC adapter lacks kernel remote-control support";
        return 1;
    }
    cec_log_addrs existing{};
    if (ioctl(fd, CEC_ADAP_G_LOG_ADDRS, &existing) != 0) return 1;
    // Adopt our configuration after a previous crash, while preserving another
    // CEC application's logical address configuration.
    if (existing.num_log_addrs != 0) {
        if (!firefly::cec::isFireflyConfiguration(existing)) {
            LOG(ERROR) << "CEC adapter already configured by another application";
            return 1;
        }
    } else {
        cec_log_addrs addresses{};
        addresses.cec_version = CEC_OP_CEC_VERSION_1_4;
        addresses.num_log_addrs = 1;
        addresses.vendor_id = CEC_VENDOR_ID_NONE;
        addresses.flags = CEC_LOG_ADDRS_FL_ALLOW_RC_PASSTHRU;
        addresses.log_addr_type[0] = CEC_LOG_ADDR_TYPE_PLAYBACK;
        addresses.primary_device_type[0] = CEC_OP_PRIM_DEVTYPE_PLAYBACK;
        strncpy(addresses.osd_name, firefly::cec::kOsdName, sizeof(addresses.osd_name) - 1);
        if (ioctl(fd, CEC_ADAP_S_LOG_ADDRS, &addresses) != 0) {
            PLOG(ERROR) << "Claim CEC playback logical address";
            return 1;
        }
    }
    const int result = run(fd.get(), signalFd.get());
    return firefly::cec::releaseAddress(fd.get()) ? result : 1;
}
