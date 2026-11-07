// SPDX-License-Identifier: Apache-2.0
// VINTF-stable, privileged IR learning service. No shell commands are constructed.
#include <algorithm>
#include <array>
#include <cerrno>
#include <chrono>
#include <cstring>
#include <limits>
#include <map>
#include <memory>
#include <mutex>
#include <string>
#include <vector>
#include <fcntl.h>
#include <glob.h>
#include <linux/input.h>
#include <linux/lirc.h>
#include <linux/cec.h>
#include <poll.h>
#include <sys/ioctl.h>
#include <unistd.h>
#include <android-base/file.h>
#include <android-base/logging.h>
#include <android-base/properties.h>
#include <android-base/unique_fd.h>
#include <android/binder_ibinder.h>
#include <android/binder_manager.h>
#include <android/binder_process.h>
#include <aidl/vendor/firefly/hardware/remote/BnRemote.h>
#include <json/json.h>
#include "CecConfiguration.h"

using android::base::unique_fd;
using Keymap = std::map<uint32_t, uint32_t>;
constexpr char kDefaults[] = "/vendor/etc/firefly/ir-defaults.json";
constexpr char kSaved[] = "/data/vendor/firefly/ir-keymap.json";
constexpr char kCecProperty[] = "persist.vendor.firefly.cec_input";
constexpr char kCecServiceStatus[] = "init.svc.vendor.firefly-cec-input";
constexpr size_t kMaxKeys = 128;

std::vector<std::string> paths(const std::string& pattern) {
    glob_t result{};
    std::vector<std::string> matches;
    if (glob(pattern.c_str(), 0, nullptr, &result) == 0) {
        for (size_t i = 0; i < result.gl_pathc; ++i) matches.emplace_back(result.gl_pathv[i]);
    }
    globfree(&result);
    return matches;
}

bool parse(const std::string& text, Json::Value* value) {
    Json::CharReaderBuilder builder;
    builder["rejectDupKeys"] = true;
    builder["failIfExtra"] = true;
    std::unique_ptr<Json::CharReader> reader(builder.newCharReader());
    std::string error;
    return reader->parse(text.data(), text.data() + text.size(), value, &error);
}

std::string encode(const Json::Value& value) {
    Json::StreamWriterBuilder writer;
    writer["indentation"] = "";
    return Json::writeString(writer, value) + "\n";
}

Json::Value failure(const char* error) {
    Json::Value result;
    result["ok"] = false;
    result["error"] = error;
    return result;
}

bool readMap(const std::string& file, Keymap* map) {
    std::string text;
    Json::Value root;
    if (!android::base::ReadFileToString(file, &text) || text.size() > 32768 ||
        !parse(text, &root) || !root["keys"].isArray() || root["keys"].size() > kMaxKeys) {
        return false;
    }
    Keymap result;
    for (const auto& entry : root["keys"]) {
        if (!entry["scancode"].isUInt() || !entry["keycode"].isUInt() ||
            entry["keycode"].asUInt() == KEY_RESERVED || entry["keycode"].asUInt() > KEY_MAX) {
            return false;
        }
        if (!result.emplace(entry["scancode"].asUInt(), entry["keycode"].asUInt()).second) {
            return false;
        }
    }
    *map = std::move(result);
    return true;
}

bool saveMap(const Keymap& map) {
    Json::Value root;
    root["version"] = 1;
    root["keys"] = Json::Value(Json::arrayValue);
    for (const auto& [scan, key] : map) {
        Json::Value entry;
        entry["scancode"] = scan;
        entry["keycode"] = key;
        root["keys"].append(entry);
    }
    const std::string temp = std::string(kSaved) + ".tmp";
    unique_fd fd(open(temp.c_str(), O_CREAT | O_TRUNC | O_WRONLY | O_CLOEXEC | O_NOFOLLOW, 0600));
    if (fd < 0 || !android::base::WriteStringToFd(encode(root), fd) || fsync(fd) != 0 ||
        rename(temp.c_str(), kSaved) != 0) {
        unlink(temp.c_str());
        return false;
    }
    unique_fd dir(open("/data/vendor/firefly", O_DIRECTORY | O_RDONLY | O_CLOEXEC));
    return dir >= 0 && fsync(dir) == 0;
}

const char* protocolName(uint16_t protocol) {
    switch (protocol) {
        case RC_PROTO_NEC: return "nec";
        case RC_PROTO_NECX: return "necx";
        case RC_PROTO_NEC32: return "nec32";
        case RC_PROTO_RC5: return "rc5";
        case RC_PROTO_RC6_0: return "rc6_0";
        case RC_PROTO_RC6_MCE: return "rc6_mce";
        case RC_PROTO_SONY12: return "sony12";
        case RC_PROTO_SONY15: return "sony15";
        case RC_PROTO_SONY20: return "sony20";
        default: return "other";
    }
}

bool cecAvailable() {
    unique_fd fd(open("/dev/cec0", O_RDWR | O_NONBLOCK | O_CLOEXEC));
    cec_caps caps{};
    constexpr uint32_t required = CEC_CAP_LOG_ADDRS | CEC_CAP_TRANSMIT | CEC_CAP_RC;
    return fd >= 0 && ioctl(fd, CEC_ADAP_G_CAPS, &caps) == 0 &&
            (caps.capabilities & required) == required;
}

class Remote {
  public:
    bool load() {
        if (!readMap(kDefaults, &mDefaults)) return false;
        mCurrent = mDefaults;
        mInstalled = mDefaults;
        Keymap saved;
        if (access(kSaved, F_OK) == 0) {
            if (!readMap(kSaved, &saved)) {
                LOG(ERROR) << "Invalid saved IR keymap; using vendor defaults";
            } else {
                mCurrent = std::move(saved);
            }
        }
        return true;
    }

    Json::Value execute(const Json::Value& request) {
        if (!request.isObject() || !request["command"].isString()) return failure("bad_request");
        const std::string command = request["command"].asString();
        if (command == "cec") {
            if (!request["enabled"].isBool()) return failure("bad_cec_enabled");
            const bool enabled = request["enabled"].asBool();
            if (!android::base::SetProperty(kCecProperty, enabled ? "1" : "0")) {
                return failure("cec_property_failed");
            }
            if (!enabled) {
                // init normally kills stopped services; even gentle_kill gives
                // only 200 ms. Wait until it cannot reclaim an address, then
                // clear any adapter-wide configuration left after its exit.
                if (!android::base::WaitForProperty(kCecServiceStatus, "stopped",
                                                    std::chrono::seconds(3))) {
                    return failure("cec_stop_timeout");
                }
                unique_fd fd(open("/dev/cec0", O_RDWR | O_NONBLOCK | O_CLOEXEC));
                if ((fd < 0 && errno != ENOENT && errno != ENODEV && errno != ENXIO) ||
                    (fd >= 0 && !firefly::cec::releaseAddress(fd.get()))) {
                    return failure("cec_cleanup_failed");
                }
            }
            Json::Value result;
            result["ok"] = true;
            result["cec_enabled"] = android::base::GetBoolProperty(kCecProperty, false);
            result["cec_available"] = cecAvailable();
            return result;
        }
        if (command == "status") {
            Json::Value result;
            result["ok"] = true;
            result["available"] = connect();
            result["key_count"] = static_cast<Json::UInt>(mCurrent.size());
            result["default_profile"] = "Firefly 12-key NEC 00FF";
            result["cec_enabled"] = android::base::GetBoolProperty(kCecProperty, false);
            result["cec_available"] = cecAvailable();
            return result;
        }
        if (!connect()) return failure("ir_unavailable");
        if (command == "capture") {
            int timeout = 15;
            if (request.isMember("timeout")) {
                if (!request["timeout"].isInt()) return failure("bad_timeout");
                timeout = request["timeout"].asInt();
                if (timeout < 1 || timeout > 20) return failure("bad_timeout");
            }
            return capture(timeout);
        }
        Keymap desired = mCurrent;
        if (command == "set") {
            if (!request["scancode"].isUInt() || !request["keycode"].isUInt()) {
                return failure("bad_mapping");
            }
            const auto key = request["keycode"].asUInt();
            if (key == KEY_RESERVED || key > KEY_MAX) return failure("bad_keycode");
            desired[request["scancode"].asUInt()] = key;
            if (desired.size() > kMaxKeys) return failure("keymap_full");
        } else if (command == "reset") {
            desired = mDefaults;
        } else {
            return failure("unknown_command");
        }
        const Keymap old = mCurrent;
        if (!apply(desired)) {
            apply(old);
            return failure("keymap_ioctl_failed");
        }
        if (!saveMap(desired)) {
            apply(old);
            return failure("persist_failed");
        }
        mCurrent = std::move(desired);
        Json::Value result;
        result["ok"] = true;
        result["key_count"] = static_cast<Json::UInt>(mCurrent.size());
        return result;
    }

    bool connect() {
        if (mInput >= 0 && mLirc >= 0) return true;
        for (const auto& rc : paths("/sys/class/rc/rc*")) {
            bool gpioIr = false;
            for (const auto& nameFile : paths(rc + "/input*/name")) {
                std::string name;
                if (android::base::ReadFileToString(nameFile, &name) && name == "gpio_ir_recv\n") {
                    gpioIr = true;
                }
            }
            if (!gpioIr) continue;
            for (const auto& event : paths(rc + "/input*/event*")) {
                mInput.reset(open(("/dev/input/" + event.substr(event.rfind('/') + 1)).c_str(),
                                  O_RDWR | O_NONBLOCK | O_CLOEXEC));
                if (mInput >= 0) break;
            }
            for (const auto& lirc : paths(rc + "/lirc*")) {
                mLirc.reset(open(("/dev/" + lirc.substr(lirc.rfind('/') + 1)).c_str(),
                                 O_RDONLY | O_NONBLOCK | O_CLOEXEC));
                if (mLirc >= 0) break;
            }
            uint32_t mode = LIRC_MODE_SCANCODE;
            if (mInput >= 0 && mLirc >= 0 && ioctl(mLirc, LIRC_SET_REC_MODE, &mode) == 0 &&
                apply(mCurrent)) return true;
            mInput.reset();
            mLirc.reset();
        }
        return false;
    }

  private:
    bool setKey(uint32_t scancode, uint32_t keycode) {
        input_keymap_entry entry{};
        entry.len = sizeof(scancode);
        entry.keycode = keycode;
        memcpy(entry.scancode, &scancode, sizeof(scancode));
        if (ioctl(mInput, EVIOCSKEYCODE_V2, &entry) != 0) return false;
        if (keycode == KEY_RESERVED) mInstalled.erase(scancode);
        else mInstalled[scancode] = keycode;
        return true;
    }
    bool apply(const Keymap& desired) {
        // Both the built-in table and learned table are known; remove stale
        // entries without deleting unrelated input devices' keymaps.
        const Keymap old = mInstalled;
        for (const auto& [scan, key] : old) {
            (void)key;
            if (desired.count(scan) == 0 && !setKey(scan, KEY_RESERVED)) return false;
        }
        for (const auto& [scan, key] : desired) if (!setKey(scan, key)) return false;
        return true;
    }
    Json::Value capture(int timeout) {
        // Swallow the key while learning so Power/Home do not leave the wizard.
        if (ioctl(mInput, EVIOCGRAB, 1) != 0) return failure("input_grab_failed");
        struct Ungrab {
            int fd;
            ~Ungrab() { ioctl(fd, EVIOCGRAB, 0); }
        } ungrab{mInput.get()};
        std::array<lirc_scancode, 64> stale;
        while (read(mLirc, stale.data(), sizeof(stale)) > 0) {}
        const auto until = std::chrono::steady_clock::now() + std::chrono::seconds(timeout);
        while (std::chrono::steady_clock::now() < until) {
            const auto remaining = std::chrono::duration_cast<std::chrono::milliseconds>(
                    until - std::chrono::steady_clock::now()).count();
            pollfd pfd{mLirc.get(), POLLIN, 0};
            int ready = poll(&pfd, 1, static_cast<int>(std::max<int64_t>(1, remaining)));
            if (ready < 0 && errno == EINTR) continue;
            if (ready == 0) break;
            if (ready < 0 || (pfd.revents & (POLLERR | POLLHUP | POLLNVAL))) {
                return failure("capture_io_failed");
            }
            lirc_scancode event{};
            if (read(mLirc, &event, sizeof(event)) != sizeof(event)) continue;
            if ((event.flags & LIRC_SCANCODE_FLAG_REPEAT) ||
                event.scancode > std::numeric_limits<uint32_t>::max()) continue;
            Json::Value result;
            result["ok"] = true;
            result["scancode"] = static_cast<Json::UInt>(event.scancode);
            result["protocol"] = protocolName(event.rc_proto);
            return result;
        }
        return failure("timeout");
    }
    Keymap mDefaults;
    Keymap mCurrent;
    Keymap mInstalled;
    unique_fd mInput;
    unique_fd mLirc;
};

class RemoteService final : public aidl::vendor::firefly::hardware::remote::BnRemote {
  public:
    RemoteService() {
        CHECK(mRemote.load()) << "Cannot load Firefly IR defaults";
        mRemote.connect();
    }

    ndk::ScopedAStatus request(const std::string& json, std::string* result) override {
        const uid_t caller = AIBinder_getCallingUid();
        if (caller != 0 && caller != 1000) {
            return ndk::ScopedAStatus::fromExceptionCode(EX_SECURITY);
        }
        Json::Value request;
        if (json.size() > 4096 || !parse(json, &request)) {
            *result = encode(failure("bad_request"));
            return ndk::ScopedAStatus::ok();
        }
        // A capture can wait up to 20 seconds. Serialize it with keymap updates
        // so an independent Binder client cannot mutate the active keymap.
        std::lock_guard<std::mutex> lock(mMutex);
        *result = encode(mRemote.execute(request));
        return ndk::ScopedAStatus::ok();
    }

  private:
    Remote mRemote;
    std::mutex mMutex;
};

int main() {
    ABinderProcess_setThreadPoolMaxThreadCount(2);
    auto service = ndk::SharedRefBase::make<RemoteService>();
    const std::string name =
            std::string(aidl::vendor::firefly::hardware::remote::IRemote::descriptor) + "/default";
    CHECK_EQ(STATUS_OK, AServiceManager_addService(service->asBinder().get(), name.c_str()));
    ABinderProcess_joinThreadPool();
    return EXIT_FAILURE;
}
