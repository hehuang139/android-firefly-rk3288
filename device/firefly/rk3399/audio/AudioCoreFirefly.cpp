// SPDX-License-Identifier: Apache-2.0
// Original Firefly-RK3399 RT5640 analog and separate HDMI PCM backend.
// Analog remains the attached/default fallback; HDMI is a real external port.
#include <algorithm>
#include <atomic>
#include <dirent.h>
#include <map>
#include <sstream>
#include <cstdlib>
#include <limits>
#include <optional>
#include <memory>
#include <tinyalsa/asoundlib.h>
#include <string>
#include <vector>

#include <android-base/file.h>
#include <android-base/logging.h>
#include <android-base/strings.h>
#include <android/binder_manager.h>
#include <android/binder_process.h>
#include <system/audio_config.h>

#include "core-impl/AudioPolicyConfigXmlConverter.h"
#include "core-impl/ChildInterface.h"
#include "core-impl/Config.h"
#include "core-impl/Module.h"
#include "core-impl/StreamAlsa.h"

using aidl::android::hardware::audio::common::SinkMetadata;
using aidl::android::hardware::audio::common::SourceMetadata;
using aidl::android::media::audio::common::AudioDevice;
using aidl::android::media::audio::common::AudioDeviceAddress;
using aidl::android::media::audio::common::AudioDeviceType;
using aidl::android::media::audio::common::AudioOffloadInfo;
using aidl::android::media::audio::common::AudioPortConfig;
using aidl::android::media::audio::common::AudioPort;
using aidl::android::media::audio::common::AudioPortExt;
using aidl::android::media::audio::common::AudioChannelLayout;
using aidl::android::media::audio::common::AudioFormatType;
using aidl::android::media::audio::common::PcmType;
using aidl::android::media::audio::common::MicrophoneInfo;

namespace aidl::android::hardware::audio::core {
namespace {

// Card numbers can change when a USB DAC is plugged in. Match the DT card ID
// instead of assuming card0; never route television audio to an unrelated card.
std::optional<int> findAnalogCard() {
    for (int card = 0; card < 32; ++card) {
        std::string id;
        if (::android::base::ReadFileToString(
                    "/proc/asound/card" + std::to_string(card) + "/id", &id) &&
            ::android::base::Trim(id) == "FireflyRT5640") {
            return card;
        }
    }
    LOG(ERROR) << "Firefly RT5640 ALSA card not found (expected card ID FireflyRT5640)";
    return std::nullopt;
}

// RK3399 has two independent simple-audio-card devices. HDMI must work even
// if the analog codec is unavailable, and USB card numbering is not stable.
std::optional<int> findHdmiCard() {
    for (int card = 0; card < 32; ++card) {
        std::string id;
        if (::android::base::ReadFileToString(
                    "/proc/asound/card" + std::to_string(card) + "/id", &id) &&
            ::android::base::Trim(id) == "FireflyHDMI") return card;
    }
    return std::nullopt;
}

bool isAnalog(const AudioDevice& device) {
    return device.type.type == AudioDeviceType::OUT_BUS && device.type.connection.empty() &&
           device.address == AudioDeviceAddress(std::string("firefly-rt5640"));
}

bool isHdmi(const AudioDevice& device) {
    return device.type.type == AudioDeviceType::OUT_DEVICE && device.type.connection == "hdmi" &&
           device.address == AudioDeviceAddress(std::string("firefly-hdmi"));
}

bool containsNumber(const std::string& values, long expected) {
    std::istringstream stream(values);
    std::string token;
    while (stream >> token) {
        char* end = nullptr;
        const long number = std::strtol(token.c_str(), &end, 10);
        if (end != token.c_str() && *end == '\0' && number == expected) return true;
    }
    return false;
}

bool eldConnectionValid(const std::string& eld) {
    std::istringstream lines(eld);
    std::string line;
    while (std::getline(lines, line)) {
        std::istringstream tokens(line);
        std::string key, value;
        if (tokens >> key >> value &&
            (key == "monitor_present" || key == "eld_valid") && value != "1") return false;
    }
    // hdmi-codec's actual ELD format omits these two fields entirely.
    return true;
}

// Kernel ELD describes the connected sink, not merely an HDMI connector.
// Require one LPCM SAD covering the only advertised profile: 48 kHz, 16-bit stereo.
bool eldSupportsPcm(const std::string& eld) {
    std::map<std::string, std::string> fields;
    std::istringstream lines(eld);
    std::string line;
    while (std::getline(lines, line)) {
        std::istringstream tokens(line);
        std::string key, value;
        if (tokens >> key) {
            std::getline(tokens, value);
            fields[key] = ::android::base::Trim(value);
        }
    }
    if (!eldConnectionValid(eld)) return false;
    const int count = std::atoi(fields["sad_count"].c_str());
    if (count < 1 || count > 15) return false;
    for (int sad = 0; sad < count; ++sad) {
        const std::string prefix = "sad" + std::to_string(sad) + "_";
        if (fields[prefix + "coding_type"].find("LPCM") == std::string::npos) continue;
        if (std::atoi(fields[prefix + "channels"].c_str()) < 2) continue;
        if (containsNumber(fields[prefix + "rates"], 48000) &&
            containsNumber(fields[prefix + "bits"], 16)) return true;
    }
    return false;
}

// A valid CTA Basic Audio flag guarantees LPCM stereo at 32/44.1/48 kHz,
// 16-bit. Otherwise require all three capabilities in the same LPCM SAD.
bool edidSupportsPcm(const std::string& bytes) {
    static const unsigned char header[] = {0,255,255,255,255,255,255,0};
    if (bytes.size() < 128) return false;
    const auto byte = [&](size_t offset) { return static_cast<unsigned char>(bytes[offset]); };
    for (size_t i = 0; i < sizeof(header); ++i) if (byte(i) != header[i]) return false;
    const size_t blocks = 1 + byte(126);
    if (bytes.size() != blocks * 128) return false;
    for (size_t block = 0; block < blocks; ++block) {
        unsigned sum = 0;
        for (size_t i = 0; i < 128; ++i) sum += byte(block * 128 + i);
        if ((sum & 255) != 0) return false;
    }
    bool supported = false;
    for (size_t block = 1; block < blocks; ++block) {
        const size_t base = block * 128;
        if (byte(base) != 0x02 || byte(base + 1) < 3) continue;
        const size_t end = byte(base + 2);
        if (end != 0 && (end < 4 || end > 127)) return false;
        supported |= (byte(base + 3) & 0x40) != 0;
        for (size_t pos = 4; end != 0 && pos < end;) {
            const unsigned tag = byte(base + pos) >> 5;
            const size_t count = byte(base + pos) & 31;
            ++pos;
            if (pos + count > end) return false;
            if (tag == 1) {
                if (count % 3 != 0) return false;
                for (size_t sad = pos; sad + 2 < pos + count; sad += 3) {
                    const unsigned info = byte(base + sad);
                    if (((info >> 3) & 15) == 1 && (info & 7) + 1 >= 2 &&
                        (byte(base + sad + 1) & 4) && (byte(base + sad + 2) & 1)) {
                        supported = true;
                    }
                }
            }
            pos += count;
        }
    }
    return supported;
}

bool hdmiSinkSupportsPcm(int card) {
    bool connected = false;
    bool edidCapable = false;
    std::unique_ptr<DIR, decltype(&closedir)> drm(opendir("/sys/class/drm"), closedir);
    if (!drm) return false;
    while (dirent* entry = readdir(drm.get())) {
        const std::string name(entry->d_name);
        if (name.find("-HDMI-A-") == std::string::npos) continue;
        const std::string path = "/sys/class/drm/" + name;
        std::string status, edid;
        if (!::android::base::ReadFileToString(path + "/status", &status) ||
            ::android::base::Trim(status) != "connected") continue;
        connected = true;
        if (::android::base::ReadFileToString(path + "/edid", &edid)) {
            edidCapable |= edidSupportsPcm(edid);
        }
    }
    // hdmi-codec can retain parsed ELD after unplug. Fresh connected DRM EDID
    // is therefore mandatory; stale ELD or permissive PCM params cannot connect.
    if (!connected || !edidCapable) return false;
    const std::string directory = "/proc/asound/card" + std::to_string(card);
    std::unique_ptr<DIR, decltype(&closedir)> dir(opendir(directory.c_str()), closedir);
    if (!dir) return edidCapable;
    while (dirent* entry = readdir(dir.get())) {
        const std::string name(entry->d_name);
        if (name.rfind("eld#", 0) != 0) continue;
        std::string eld;
        if (::android::base::ReadFileToString(directory + "/" + name, &eld)) {
            if (!eldConnectionValid(eld)) return false;
            if (!eldSupportsPcm(eld)) {
                LOG(VERBOSE) << "Current EDID supports PCM; ELD has no matching SAD";
            }
        }
    }
    return edidCapable;
}

bool hdmiPcmSupportsProfile(int card) {
    std::unique_ptr<pcm_params, decltype(&pcm_params_free)> params(
            pcm_params_get(card, 0, PCM_OUT), pcm_params_free);
    if (!params) return false;
    return pcm_params_format_test(params.get(), PCM_FORMAT_S16_LE) &&
           pcm_params_get_min(params.get(), PCM_PARAM_CHANNELS) <= 2 &&
           pcm_params_get_max(params.get(), PCM_PARAM_CHANNELS) >= 2 &&
           pcm_params_get_min(params.get(), PCM_PARAM_RATE) <= 48000 &&
           pcm_params_get_max(params.get(), PCM_PARAM_RATE) >= 48000;
}

// Configure only the real, named RT5640 controls. Missing controls fail the
// stream instead of silently discarding audio or using another ALSA card.
bool configureAnalogMixer(int card) {
    std::unique_ptr<mixer, decltype(&mixer_close)> mix(mixer_open(card), mixer_close);
    if (!mix) return false;
    const auto set = [&](const char* name, int value) {
        mixer_ctl* ctl = mixer_get_ctl_by_name(mix.get(), name);
        if (!ctl) { LOG(ERROR) << "Missing RT5640 control " << name; return false; }
        for (unsigned i = 0; i < mixer_ctl_get_num_values(ctl); ++i) {
            if (mixer_ctl_set_value(ctl, i, value) != 0) {
                LOG(ERROR) << "Failed RT5640 control " << name; return false;
            }
        }
        return true;
    };
    const auto select = [&](const char* name, const char* value) {
        mixer_ctl* ctl = mixer_get_ctl_by_name(mix.get(), name);
        if (!ctl || mixer_ctl_set_enum_by_string(ctl, value) != 0) {
            LOG(ERROR) << "Missing or invalid RT5640 enum " << name;
            return false;
        }
        return true;
    };
    // Linux 6.18.60 RT5640: DAC1 175 = 0 dB, HP 23 = -12 dB.
    // Use the headphone-volume path; keep ADC loopback and direct DAC bypass off.
    // These are source-verified controls, pending real-board listening acceptance.
    return set("HP Channel Switch", 0) &&
           set("HP L Playback Switch", 0) &&
           set("HP R Playback Switch", 0) &&
           select("DAI1 RX Mux", "1:1|2:2") &&
           set("DAC1 Playback Volume", 175) &&
           set("HP Playback Volume", 23) &&
           set("DAC MIXL Stereo ADC Switch", 0) &&
           set("DAC MIXR Stereo ADC Switch", 0) &&
           set("DAC MIXL INF1 Switch", 1) &&
           set("DAC MIXR INF1 Switch", 1) &&
           set("Stereo DAC MIXL DAC L1 Switch", 1) &&
           set("Stereo DAC MIXR DAC R1 Switch", 1) &&
           set("OUT MIXL DAC L1 Switch", 1) &&
           set("OUT MIXR DAC R1 Switch", 1) &&
           set("HPO MIX L HPO MIX DAC1 Switch", 0) &&
           set("HPO MIX R HPO MIX DAC1 Switch", 0) &&
           set("HPO MIX L HPO MIX HPVOL Switch", 1) &&
           set("HPO MIX R HPO MIX HPVOL Switch", 1) &&
           set("Headphone Jack Switch", 1) &&
           // Separate DAPM output switches gate HP Amp -> HPOL/HPOR. The
           // HP Channel Switch alone does not enable these playback routes.
           set("HP L Playback Switch", 1) &&
           set("HP R Playback Switch", 1) &&
           set("HP Channel Switch", 1);
}

class StreamOutFirefly final : public StreamOut, public StreamAlsa {
  public:
    StreamOutFirefly(StreamContext&& context, const SourceMetadata& metadata,
                     const std::optional<AudioOffloadInfo>& offloadInfo)
        : StreamOut(std::move(context), offloadInfo),
          StreamAlsa(&mContextInstance, metadata, 1 /*readWriteRetries*/) {}

    ndk::ScopedAStatus setConnectedDevices(const ConnectedDevices& devices) override {
        if (devices.size() > 1 ||
            (!devices.empty() && !isAnalog(devices[0]) && !isHdmi(devices[0]))) {
            return ndk::ScopedAStatus::fromExceptionCode(EX_ILLEGAL_ARGUMENT);
        }
        // Binder only changes the atomic target. The audio worker alone owns PCM proxies.
        if (!devices.empty()) mDesiredPcm.store(isHdmi(devices[0]) ? 1 : 0);
        return StreamCommonImpl::setConnectedDevices(devices);
    }

    ::android::status_t start() override {
        return ensureSelectedRoute();
    }

    ::android::status_t transfer(void* buffer, size_t frames, size_t* actual,
                                 int32_t* latencyMs) override {
        *actual = 0;
        *latencyMs = StreamDescriptor::LATENCY_UNKNOWN;
        if (const auto status = ensureSelectedRoute(); status != ::android::OK) return status;
        if (mAlsaDeviceProxies.size() != 1 || !mConfig.has_value()) {
            return ::android::NO_INIT;
        }
        const size_t bytes = frames * mFrameSizeBytes;
        alsa::applyGain(buffer, mGain.load(), bytes, mConfig->format, mConfig->channels);
        auto* proxy = mAlsaDeviceProxies.front().get();
        // A zero-byte AIDL burst is a state transition, not a PCM write.
        if (bytes == 0) {
            *latencyMs = static_cast<int32_t>(proxy_get_latency(proxy));
            return ::android::OK;
        }
        int error = proxy_write_with_retries(proxy, buffer, bytes, mReadWriteRetries);
        if (error != 0) {
            // Do not permanently poison the AIDL stream after a transient XRUN.
            // Reopen at most once, retaining the proxy's cumulative frame count.
            // The already gained buffer is retried directly, without double gain.
            LOG(WARNING) << "Firefly PCM write failed: " << error
                         << "; reopening once: " << pcm_get_error(proxy->pcm);
            proxy_close(proxy);
            error = proxy_open(proxy);
            if (error == 0) {
                error = proxy_write_with_retries(proxy, buffer, bytes, mReadWriteRetries);
            }
            if (error != 0) {
                LOG(ERROR) << "Firefly PCM recovery failed: " << error;
                return ::android::INVALID_OPERATION;
            }
            LOG(INFO) << "Firefly PCM recovered and current buffer written";
        }
        *actual = frames;
        *latencyMs = static_cast<int32_t>(std::min(
                proxy_get_latency(proxy), static_cast<unsigned>(std::numeric_limits<int32_t>::max())));
        return ::android::OK;
    }

  private:
    void onClose(StreamDescriptor::State) override { defaultOnClose(); }

    // AudioFlinger applies user volume in software; the real DAC mixer is
    // initialized to a fixed conservative analog gain, never a dummy sink.
    ndk::ScopedAStatus getHwVolume(std::vector<float>*) override {
        return ndk::ScopedAStatus::fromExceptionCode(EX_UNSUPPORTED_OPERATION);
    }
    ndk::ScopedAStatus setHwVolume(const std::vector<float>&) override {
        return ndk::ScopedAStatus::fromExceptionCode(EX_UNSUPPORTED_OPERATION);
    }
    ::android::status_t ensureSelectedRoute() {
        const int selected = mDesiredPcm.load();
        if (selected == mActivePcm && !mAlsaDeviceProxies.empty()) return ::android::OK;
        mAlsaDeviceProxies.clear();
        mOpeningPcm = selected;
        const auto status = openDeviceProxies(&mAlsaDeviceProxies);
        if (status == ::android::OK) mActivePcm = selected;
        return status;
    }

    std::vector<alsa::DeviceProfile> getDeviceProfiles() override {
        if (mOpeningPcm == 1) {
            const auto card = findHdmiCard();
            if (!card || !hdmiSinkSupportsPcm(*card)) return {};
            return {{*card, 0, PCM_OUT, false}};
        }
        const auto card = findAnalogCard();
        if (card && configureAnalogMixer(*card)) return {{*card, 0, PCM_OUT, false}};
        return {};
    }

    std::atomic<int> mDesiredPcm{0};
    int mActivePcm = -1;  // Accessed only by the audio worker.
    int mOpeningPcm = 0;
};

class ModuleFirefly final : public Module {
  public:
    explicit ModuleFirefly(std::unique_ptr<Configuration>&& config)
        : Module(Type::DEFAULT, std::move(config)) {}

  private:
    ndk::ScopedAStatus populateConnectedDevicePort(AudioPort* port, int32_t) override {
        if (port->ext.getTag() != AudioPortExt::device ||
            !isHdmi(port->ext.get<AudioPortExt::device>().device)) {
            return ndk::ScopedAStatus::fromExceptionCode(EX_ILLEGAL_ARGUMENT);
        }
        const auto card = findHdmiCard();
        if (!card || !hdmiSinkSupportsPcm(*card) || !hdmiPcmSupportsProfile(*card)) {
            LOG(WARNING) << "HDMI connection rejected: no ready 48k/16-bit/stereo sink and HDMI PCM0";
            return ndk::ScopedAStatus::fromExceptionCode(EX_ILLEGAL_STATE);
        }
        if (port->profiles.size() != 1) {
            return ndk::ScopedAStatus::fromExceptionCode(EX_ILLEGAL_ARGUMENT);
        }
        const auto& profile = port->profiles.front();
        if (profile.format.type != AudioFormatType::PCM ||
            profile.format.pcm != PcmType::INT_16_BIT ||
            profile.sampleRates != std::vector<int32_t>{48000} ||
            profile.channelMasks.size() != 1 ||
            profile.channelMasks.front().getTag() != AudioChannelLayout::layoutMask ||
            profile.channelMasks.front().get<AudioChannelLayout::layoutMask>() !=
                    AudioChannelLayout::LAYOUT_STEREO) {
            return ndk::ScopedAStatus::fromExceptionCode(EX_ILLEGAL_ARGUMENT);
        }
        // Module allocates a new connected port id and copies the valid route.
        // Keep external HDMI semantics; analog stays the sole attached default.
        return ndk::ScopedAStatus::ok();
    }

    ndk::ScopedAStatus createInputStream(StreamContext&&, const SinkMetadata&,
                                         const std::vector<MicrophoneInfo>&,
                                         std::shared_ptr<StreamIn>*) override {
        return ndk::ScopedAStatus::fromExceptionCode(EX_UNSUPPORTED_OPERATION);
    }
    ndk::ScopedAStatus createOutputStream(
            StreamContext&& context, const SourceMetadata& metadata,
            const std::optional<AudioOffloadInfo>& offloadInfo,
            std::shared_ptr<StreamOut>* result) override {
        if (context.isMmap() || offloadInfo.has_value() || context.getSampleRate() != 48000 ||
            context.getFrameSize() != 4) {
            return ndk::ScopedAStatus::fromExceptionCode(EX_UNSUPPORTED_OPERATION);
        }
        return createStreamInstance<StreamOutFirefly>(result, std::move(context), metadata,
                                                      offloadInfo);
    }
    int32_t getNominalLatencyMs(const AudioPortConfig&) override { return 40; }
    ndk::ScopedAStatus onMasterMuteChanged(bool) override {
        return ndk::ScopedAStatus::fromExceptionCode(EX_UNSUPPORTED_OPERATION);
    }
    ndk::ScopedAStatus onMasterVolumeChanged(float) override {
        return ndk::ScopedAStatus::fromExceptionCode(EX_UNSUPPORTED_OPERATION);
    }
};

}  // namespace
}  // namespace aidl::android::hardware::audio::core

int main() {
    using namespace aidl::android::hardware::audio::core;
    ::android::base::SetMinimumLogSeverity(::android::base::INFO);
    ABinderProcess_setThreadPoolMaxThreadCount(8);
    ABinderProcess_startThreadPool();
    internal::AudioPolicyConfigXmlConverter converter{
            ::android::audio_get_audio_policy_config_file()};
    auto config = ndk::SharedRefBase::make<Config>(converter);
    CHECK_EQ(STATUS_OK, AServiceManager_addService(
                               config->asBinder().get(),
                               (std::string(Config::descriptor) + "/default").c_str()));
    std::vector<ChildInterface<Module>> instances;
    auto configs = converter.releaseModuleConfigs();
    CHECK(configs != nullptr);
    for (auto& [name, moduleConfig] : *configs) {
        ChildInterface<Module> module;
        if (name == "default") {
            module = ndk::SharedRefBase::make<ModuleFirefly>(std::move(moduleConfig));
        } else if (name == "r_submix") {
            module = Module::createInstance(Module::Type::R_SUBMIX, std::move(moduleConfig));
        } else {
            LOG(FATAL) << "Unsupported audio policy module: " << name;
        }
        CHECK(static_cast<bool>(module));
        CHECK_EQ(STATUS_OK, AServiceManager_addService(
                                   module.getBinder(),
                                   (std::string(Module::descriptor) + "/" + name).c_str()));
        instances.push_back(std::move(module));
    }
    CHECK(!instances.empty());
    ABinderProcess_joinThreadPool();
    return EXIT_FAILURE;
}
