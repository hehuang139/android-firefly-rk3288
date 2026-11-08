// SPDX-License-Identifier: Apache-2.0
#include <cstdlib>
#include <string>
#include <android-base/logging.h>
#include <android/binder_manager.h>
#include <android/binder_process.h>
#include "effectFactory-impl/EffectFactory.h"

int main() {
    ::android::base::SetMinimumLogSeverity(::android::base::INFO);
    ABinderProcess_setThreadPoolMaxThreadCount(0);
    auto factory = ndk::SharedRefBase::make<aidl::android::hardware::audio::effect::Factory>(
            "/vendor/etc/audio_effects_config.xml");
    CHECK_EQ(STATUS_OK, AServiceManager_addService(
                               factory->asBinder().get(),
                               (std::string(factory->descriptor) + "/default").c_str()));
    ABinderProcess_joinThreadPool();
    return EXIT_FAILURE;
}
