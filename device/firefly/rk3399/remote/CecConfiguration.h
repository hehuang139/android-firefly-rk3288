// SPDX-License-Identifier: Apache-2.0
#pragma once

#include <cerrno>
#include <chrono>
#include <cstring>
#include <linux/cec.h>
#include <sys/ioctl.h>
#include <unistd.h>
#include <android-base/logging.h>

namespace firefly::cec {

inline constexpr char kOsdName[] = "Firefly TV";

inline bool isFireflyConfiguration(const cec_log_addrs& addresses) {
    return addresses.num_log_addrs == 1 &&
            addresses.cec_version == CEC_OP_CEC_VERSION_1_4 &&
            addresses.vendor_id == CEC_VENDOR_ID_NONE &&
            addresses.flags == CEC_LOG_ADDRS_FL_ALLOW_RC_PASSTHRU &&
            addresses.log_addr_type[0] == CEC_LOG_ADDR_TYPE_PLAYBACK &&
            addresses.primary_device_type[0] == CEC_OP_PRIM_DEVTYPE_PLAYBACK &&
            strncmp(addresses.osd_name, kOsdName, sizeof(addresses.osd_name)) == 0;
}

inline bool releaseAddress(int fd) {
    // Logical addresses and RC passthrough belong to the adapter, not the open
    // file. Closing fd alone leaves remote keys enabled after init stops us.
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(3);
    do {
        cec_log_addrs current{};
        if (ioctl(fd, CEC_ADAP_G_LOG_ADDRS, &current) != 0) {
            if (errno == ENODEV) return true;
            PLOG(ERROR) << "Read CEC configuration on shutdown";
            return false;
        }
        if (current.num_log_addrs == 0 || !isFireflyConfiguration(current)) return true;
        cec_log_addrs cleared{};
        if (ioctl(fd, CEC_ADAP_S_LOG_ADDRS, &cleared) == 0) return true;
        if (errno == ENODEV) return true;
        if (errno != EBUSY) break;
        // A claim started just before shutdown may still be configuring.
        usleep(25000);
    } while (std::chrono::steady_clock::now() < deadline);
    PLOG(ERROR) << "Clear Firefly CEC logical address to disable RC input";
    return false;
}

}  // namespace firefly::cec
