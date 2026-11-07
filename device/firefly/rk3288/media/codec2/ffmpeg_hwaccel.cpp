// SPDX-License-Identifier: Apache-2.0
// The software parser supplies H.264 reference lists; Hantro decodes each frame.
#define LOG_TAG "FireflyHantro"
#include <log/log.h>
#include "ffmpeg_hwaccel.h"

static AVPixelFormat requestFormat(AVCodecContext *, const AVPixelFormat *formats) {
    for (; *formats != AV_PIX_FMT_NONE; ++formats) {
        if (*formats == AV_PIX_FMT_DRM_PRIME) return *formats;
    }
    ALOGE("Hantro Request output unavailable; refusing software decoding");
    return AV_PIX_FMT_NONE;
}

int ffmpeg_hwaccel_init(AVCodecContext *ctx) {
    if (ctx->codec_id != AV_CODEC_ID_H264 && ctx->codec_id != AV_CODEC_ID_HEVC)
        return AVERROR(ENOSYS);
    ctx->get_format = requestFormat;
    ctx->thread_count = 1;
    ctx->thread_type = 0;
    return av_hwdevice_ctx_create(&ctx->hw_device_ctx,
                                 AV_HWDEVICE_TYPE_V4L2REQUEST, nullptr, nullptr, 0);
}
void ffmpeg_hwaccel_deinit(AVCodecContext *) {}

int ffmpeg_hwaccel_get_frame(AVCodecContext *, AVFrame *frame) {
    if (frame->format != AV_PIX_FMT_DRM_PRIME || !frame->hw_frames_ctx)
        return AVERROR(ENOSYS);
    const auto *frames = reinterpret_cast<const AVHWFramesContext *>(frame->hw_frames_ctx->data);
    if (!frames->device_ctx || frames->device_ctx->type != AV_HWDEVICE_TYPE_V4L2REQUEST)
        return AVERROR(ENOSYS);
    // Map the linear NV12 capture read-only. The AVFrame mapping retains its
    // hardware frame and DMA synchronization until conversion to the C2 block.
    // This avoids a full-frame allocation/copy before the final layout conversion.
    AVFrame *out = av_frame_alloc();
    if (!out) return AVERROR(ENOMEM);
    out->format = AV_PIX_FMT_NV12;
    int error = av_hwframe_map(out, frame, AV_HWFRAME_MAP_READ);
    if (error >= 0) error = av_frame_copy_props(out, frame);
    // FFmpeg applies right/bottom crop to hardware frames; apply any remaining
    // left/top crop after the pixels become CPU-addressable.
    if (error >= 0) error = av_frame_apply_cropping(out, AV_FRAME_CROP_UNALIGNED);
    if (error >= 0) {
        av_frame_unref(frame);
        av_frame_move_ref(frame, out);
    }
    av_frame_free(&out);
    return error;
}
