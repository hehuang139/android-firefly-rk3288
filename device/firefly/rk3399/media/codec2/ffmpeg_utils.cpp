// SPDX-License-Identifier: Apache-2.0
#define LOG_TAG "FireflyRequestCodec2"
#include <log/log.h>
#include <cstdarg>
#include <cstdio>
#include "ffmpeg_utils.h"
namespace android {
static void logFFmpeg(void *, int level, const char *fmt, va_list args) {
    if (level > AV_LOG_INFO) return;
    char text[1024];
    vsnprintf(text, sizeof(text), fmt, args);
    __android_log_write(level <= AV_LOG_ERROR ? ANDROID_LOG_ERROR : ANDROID_LOG_INFO,
                        LOG_TAG, text);
}
status_t initFFmpeg() {
    av_log_set_level(AV_LOG_INFO);
    av_log_set_callback(logFFmpeg);
    return OK;
}
void deInitFFmpeg() {}
}
