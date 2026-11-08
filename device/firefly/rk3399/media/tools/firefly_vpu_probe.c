/* SPDX-License-Identifier: Apache-2.0
 * Inspect the RK3399 stateless H.264 and VP9 request interfaces.
 * A successful probe checks the API, not decoded video output.
 */
#include <errno.h>
#include <fcntl.h>
#include <linux/media.h>
#include <linux/videodev2.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>

static int call_ioctl(int fd, unsigned long operation, void *argument) {
    int result;
    do { result = ioctl(fd, operation, argument); } while (result < 0 && errno == EINTR);
    return result;
}

static void json_string(const char *value) {
    putchar('"');
    for (const unsigned char *p = (const unsigned char *)value; *p; ++p) {
        if (*p == '"' || *p == '\\') { putchar('\\'); putchar(*p); }
        else if (*p < 32 || *p >= 127) printf("\\u%04x", *p);
        else putchar(*p);
    }
    putchar('"');
}

static bool has_format(int fd, enum v4l2_buf_type type, uint32_t fourcc) {
    struct v4l2_fmtdesc format = {0};
    format.type = type;
    for (format.index = 0; format.index < 256; ++format.index) {
        if (call_ioctl(fd, VIDIOC_ENUM_FMT, &format) < 0) break;
        if (format.pixelformat == fourcc) return true;
    }
    return false;
}

static bool has_control(int fd, uint32_t id) {
    struct v4l2_query_ext_ctrl control = {0};
    control.id = id;
    return call_ioctl(fd, VIDIOC_QUERY_EXT_CTRL, &control) == 0 &&
           !(control.flags & V4L2_CTRL_FLAG_DISABLED);
}

static bool can_allocate_request(const char *bus, char *path, size_t capacity) {
    for (unsigned i = 0; i < 64; ++i) {
        char candidate[64];
        snprintf(candidate, sizeof(candidate), "/dev/media%u", i);
        int fd = open(candidate, O_RDWR | O_CLOEXEC);
        if (fd < 0) continue;
        struct media_device_info info = {0};
        if (call_ioctl(fd, MEDIA_IOC_DEVICE_INFO, &info) != 0 ||
            strncmp(info.bus_info, bus, sizeof(info.bus_info)) != 0) {
            close(fd); continue;
        }
        int request = -1;
        bool supported = call_ioctl(fd, MEDIA_IOC_REQUEST_ALLOC, &request) == 0 && request >= 0;
        if (request >= 0) close(request);
        close(fd);
        if (supported) { snprintf(path, capacity, "%s", candidate); return true; }
    }
    return false;
}

int main(int argc, char **argv) {
    if (argc > 1) {
        if (argc == 2 && strcmp(argv[1], "--help") == 0) {
            puts("firefly-vpu-probe: inspect rkvdec H264_SLICE/VP9_FRAME, NV12 and Media Request API.\n"
                 "Exit 0 means request API ready; it does not prove a frame was decoded.\n"
                 "Exit 3 means required device, permission or driver is unavailable.");
            return 0;
        }
        fprintf(stderr, "Unexpected argument; use --help\n");
        return 2;
    }
    bool any_ready = false;
    bool first = true;
    puts("{\"format\":1,\"scope\":\"kernel-interface-probe\",\"hardware_decode_verified\":false,\"devices\":[");
    for (unsigned i = 0; i < 64; ++i) {
        char path[64];
        snprintf(path, sizeof(path), "/dev/video%u", i);
        int fd = open(path, O_RDWR | O_NONBLOCK | O_CLOEXEC);
        if (fd < 0) continue;
        struct v4l2_capability capability = {0};
        if (call_ioctl(fd, VIDIOC_QUERYCAP, &capability) != 0) { close(fd); continue; }
        const uint32_t caps = (capability.capabilities & V4L2_CAP_DEVICE_CAPS) ?
                                  capability.device_caps : capability.capabilities;
        bool h264 = has_format(fd, V4L2_BUF_TYPE_VIDEO_OUTPUT_MPLANE, V4L2_PIX_FMT_H264_SLICE);
        bool vp9 = has_format(fd, V4L2_BUF_TYPE_VIDEO_OUTPUT_MPLANE, V4L2_PIX_FMT_VP9_FRAME);
        if (!h264 && !vp9) {
            close(fd); continue;
        }
        capability.driver[sizeof(capability.driver) - 1] = 0;
        capability.bus_info[sizeof(capability.bus_info) - 1] = 0;
        const uint32_t needed[] = {V4L2_CID_STATELESS_H264_SPS, V4L2_CID_STATELESS_H264_PPS,
            V4L2_CID_STATELESS_H264_SCALING_MATRIX, V4L2_CID_STATELESS_H264_DECODE_PARAMS,
            V4L2_CID_STATELESS_H264_DECODE_MODE, V4L2_CID_STATELESS_H264_START_CODE};
        bool controls = true;
        for (unsigned c = 0; c < sizeof(needed) / sizeof(needed[0]); ++c)
            controls = has_control(fd, needed[c]) && controls;
        bool vp9_controls = has_control(fd, V4L2_CID_STATELESS_VP9_FRAME) &&
                            has_control(fd, V4L2_CID_STATELESS_VP9_COMPRESSED_HDR);
        bool m2m = (caps & (V4L2_CAP_VIDEO_M2M_MPLANE | V4L2_CAP_STREAMING)) ==
                          (V4L2_CAP_VIDEO_M2M_MPLANE | V4L2_CAP_STREAMING);
        bool nv12 = has_format(fd, V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE, V4L2_PIX_FMT_NV12) ||
                    has_format(fd, V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE, V4L2_PIX_FMT_NV12M);
        char media[64] = "";
        bool requests = can_allocate_request((const char *)capability.bus_info, media, sizeof(media));
        bool ready = m2m && nv12 && requests && ((h264 && controls) || (vp9 && vp9_controls));
        any_ready = any_ready || ready;
        if (!first) puts(",");
        first = false;
        printf("{\"video\":"); json_string(path);
        printf(",\"driver\":"); json_string((const char *)capability.driver);
        printf(",\"bus\":"); json_string((const char *)capability.bus_info);
        printf(",\"media\":"); json_string(media);
        printf(",\"m2m_streaming\":%s,\"h264_slice\":%s,\"vp9_frame\":%s,\"nv12\":%s,"
               "\"h264_controls\":%s,\"vp9_controls\":%s,\"request_allocation\":%s,\"ready\":%s}",
               m2m ? "true" : "false", h264 ? "true" : "false", vp9 ? "true" : "false",
               nv12 ? "true" : "false", controls ? "true" : "false", vp9_controls ? "true" : "false",
               requests ? "true" : "false", ready ? "true" : "false");
        close(fd);
    }
    printf("\n],\"request_api_ready\":%s}\n", any_ready ? "true" : "false");
    return any_ready ? 0 : 3;
}
