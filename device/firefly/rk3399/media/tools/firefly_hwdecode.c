/* SPDX-License-Identifier: Apache-2.0
 * Decode raw H.264 or VP9 IVF using rkvdec's V4L2 Request backend, never CPU fallback.
 */
#include <errno.h>
#include <inttypes.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
#include "libavcodec/avcodec.h"
#include "libavutil/hwcontext.h"
#include "libavutil/sha.h"
#include "libavutil/intreadwrite.h"

struct result {
    unsigned frames;
    unsigned width;
    unsigned height;
    struct AVSHA *sha;
};

static enum AVPixelFormat hardware_format(AVCodecContext *ctx,
                                          const enum AVPixelFormat *formats)
{
    (void)ctx;
    while (*formats != AV_PIX_FMT_NONE) {
        if (*formats == AV_PIX_FMT_DRM_PRIME)
            return *formats;
        formats++;
    }
    return AV_PIX_FMT_NONE;
}

static int receive_frames(AVCodecContext *ctx, AVFrame *frame, struct result *result)
{
    int error;
    while ((error = avcodec_receive_frame(ctx, frame)) >= 0) {
        if (frame->format != AV_PIX_FMT_DRM_PRIME || !frame->hw_frames_ctx)
            return AVERROR(ENOSYS);
        const AVHWFramesContext *frames = (const AVHWFramesContext *)frame->hw_frames_ctx->data;
        if (!frames->device_ctx || frames->device_ctx->type != AV_HWDEVICE_TYPE_V4L2REQUEST)
            return AVERROR(ENOSYS);
        AVFrame *copy = av_frame_alloc();
        if (!copy)
            return AVERROR(ENOMEM);
        copy->format = AV_PIX_FMT_NV12;
        error = av_hwframe_transfer_data(copy, frame, 0);
        if (error < 0) {
            av_frame_free(&copy);
            return error;
        }
        /* Hash visible pixels, excluding driver padding and stride bytes. */
        for (int plane = 0; plane < 2; plane++) {
            int height = plane ? (frame->height + 1) / 2 : frame->height;
            int width = plane ? ((frame->width + 1) / 2) * 2 : frame->width;
            for (int row = 0; row < height; row++)
                av_sha_update(result->sha, copy->data[plane] + row * copy->linesize[plane], width);
        }
        result->width = frame->width;
        result->height = frame->height;
        result->frames++;
        av_frame_free(&copy);
        av_frame_unref(frame);
    }
    return error == AVERROR(EAGAIN) || error == AVERROR_EOF ? 0 : error;
}

static int send_packet(AVCodecContext *ctx, AVPacket *packet,
                       AVFrame *frame, struct result *result)
{
    int error = avcodec_send_packet(ctx, packet);
    if (error == AVERROR(EAGAIN)) {
        error = receive_frames(ctx, frame, result);
        if (error < 0)
            return error;
        error = avcodec_send_packet(ctx, packet);
    }
    if (error < 0)
        return error;
    return receive_frames(ctx, frame, result);
}

int main(int argc, char **argv)
{
    if (argc == 2 && !strcmp(argv[1], "--help")) {
        puts("Usage: firefly-hwdecode input.h264|input.ivf\n"
             "Requires RK3399 V4L2 Request; prints decoded NV12 SHA256 JSON.");
        return 0;
    }
    if (argc != 2) {
        fputs("Usage: firefly-hwdecode input.h264|input.ivf\n", stderr);
        return 2;
    }
    const char *extension = strrchr(argv[1], '.');
    if (!extension || (strcmp(extension, ".h264") && strcmp(extension, ".ivf"))) {
        fputs("Use raw .h264 or VP9 .ivf; unsupported formats are not guessed.\n", stderr);
        return 2;
    }
    const int ivf = !strcmp(extension, ".ivf");
    enum AVCodecID codec_id = ivf ? AV_CODEC_ID_VP9 : AV_CODEC_ID_H264;
    FILE *input = fopen(argv[1], "rb");
    if (!input) {
        perror(argv[1]);
        return 2;
    }
    const AVCodec *codec = avcodec_find_decoder(codec_id);
    AVCodecContext *ctx = avcodec_alloc_context3(codec);
    AVCodecParserContext *parser = ivf ? NULL : av_parser_init(codec_id);
    AVFrame *frame = av_frame_alloc();
    AVPacket *packet = av_packet_alloc();
    struct result result = {0};
    result.sha = av_sha_alloc();
    int error = AVERROR(ENOMEM);
    struct timespec start, stop;
    clock_gettime(CLOCK_MONOTONIC, &start);
    if (!codec || !ctx || (!ivf && !parser) || !frame || !packet || !result.sha)
        goto done;
    av_sha_init(result.sha, 256);
    ctx->get_format = hardware_format;
    ctx->thread_count = 1;
    ctx->thread_type = 0;
    error = av_hwdevice_ctx_create(&ctx->hw_device_ctx, AV_HWDEVICE_TYPE_V4L2REQUEST,
                                   NULL, NULL, 0);
    if (error < 0 || (error = avcodec_open2(ctx, codec, NULL)) < 0)
        goto done;

    if (ivf) {
        // VP9 packet boundaries are mandatory: an arbitrary raw-byte parser
        // cannot reconstruct IVF's length-delimited frames reliably.
        uint8_t header[32];
        if (fread(header, 1, sizeof(header), input) != sizeof(header) ||
            memcmp(header, "DKIF", 4) || AV_RL16(header + 4) != 0 ||
            AV_RL16(header + 6) != 32 || memcmp(header + 8, "VP90", 4) ||
            !AV_RL16(header + 12) || !AV_RL16(header + 14)) {
            error = AVERROR_INVALIDDATA;
            goto done;
        }
        ctx->width = AV_RL16(header + 12);
        ctx->height = AV_RL16(header + 14);
        for (;;) {
            uint8_t frame_header[12];
            size_t got = fread(frame_header, 1, sizeof(frame_header), input);
            if (!got && feof(input)) break;
            if (got != sizeof(frame_header)) { error = AVERROR_INVALIDDATA; goto done; }
            uint32_t size = AV_RL32(frame_header);
            if (!size || size > 32U * 1024 * 1024) { error = AVERROR_INVALIDDATA; goto done; }
            av_packet_unref(packet);
            error = av_new_packet(packet, (int)size);
            if (error < 0) goto done;
            if (fread(packet->data, 1, size, input) != size) { error = AVERROR_INVALIDDATA; goto done; }
            packet->pts = (int64_t)AV_RL64(frame_header + 4);
            error = send_packet(ctx, packet, frame, &result);
            if (error < 0) goto done;
        }
        error = send_packet(ctx, NULL, frame, &result);
        if (!error && !result.frames) error = AVERROR_INVALIDDATA;
        goto done;
    }

    uint8_t buffer[65536 + AV_INPUT_BUFFER_PADDING_SIZE];
    size_t length;
    while ((length = fread(buffer, 1, 65536, input)) > 0) {
        memset(buffer + length, 0, AV_INPUT_BUFFER_PADDING_SIZE);
        uint8_t *data = buffer;
        while (length) {
            int used = av_parser_parse2(parser, ctx, &packet->data, &packet->size,
                                       data, (int)length, AV_NOPTS_VALUE, AV_NOPTS_VALUE, 0);
            if (used < 0) {
                error = used;
                goto done;
            }
            if (!used && !packet->size) {
                error = AVERROR_INVALIDDATA;
                goto done;
            }
            data += used;
            length -= used;
            if (packet->size && (error = send_packet(ctx, packet, frame, &result)) < 0)
                goto done;
        }
    }
    if (ferror(input)) {
        error = AVERROR(EIO);
        goto done;
    }
    error = av_parser_parse2(parser, ctx, &packet->data, &packet->size,
                            NULL, 0, AV_NOPTS_VALUE, AV_NOPTS_VALUE, 0);
    if (error < 0)
        goto done;
    if (packet->size && (error = send_packet(ctx, packet, frame, &result)) < 0)
        goto done;
    error = send_packet(ctx, NULL, frame, &result);
    if (!error && !result.frames)
        error = AVERROR_INVALIDDATA;

done:
    clock_gettime(CLOCK_MONOTONIC, &stop);
    double seconds = stop.tv_sec - start.tv_sec + (stop.tv_nsec - start.tv_nsec) / 1e9;
    uint8_t digest[32] = {0};
    char hash[65];
    if (result.sha && result.frames)
        av_sha_final(result.sha, digest);
    for (unsigned i = 0; i < 32; i++)
        snprintf(hash + i * 2, 3, "%02x", digest[i]);
    printf("{\"format\":1,\"backend\":\"rockchip-v4l2-request\","
           "\"hardware_decode_verified\":%s,\"frames\":%u,\"width\":%u,\"height\":%u,"
           "\"seconds\":%.6f,\"fps\":%.3f,\"nv12_sha256\":\"%s\",\"error\":%d}\n",
           error >= 0 && result.frames ? "true" : "false", result.frames,
           result.width, result.height, seconds, seconds > 0 ? result.frames / seconds : 0,
           hash, error);
    if (error < 0) {
        char message[AV_ERROR_MAX_STRING_SIZE];
        av_strerror(error, message, sizeof(message));
        fprintf(stderr, "Hardware decode failed: %s\n", message);
    }
    fclose(input);
    av_free(result.sha);
    av_frame_free(&frame);
    av_packet_free(&packet);
    av_parser_close(parser);
    avcodec_free_context(&ctx);
    return error < 0 ? 3 : 0;
}
