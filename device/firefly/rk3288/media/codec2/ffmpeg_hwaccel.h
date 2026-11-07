// SPDX-License-Identifier: Apache-2.0
#pragma once
extern "C" {
#include "libavcodec/avcodec.h"
#include "libavutil/hwcontext.h"
int ffmpeg_hwaccel_init(AVCodecContext *ctx);
void ffmpeg_hwaccel_deinit(AVCodecContext *ctx);
int ffmpeg_hwaccel_get_frame(AVCodecContext *ctx, AVFrame *frame);
}
