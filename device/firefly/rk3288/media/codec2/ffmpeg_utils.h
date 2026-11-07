// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <utils/Errors.h>
extern "C" {
#include "libavcodec/avcodec.h"
#include "libswscale/swscale.h"
#include "libavutil/opt.h"
#include "libavutil/pixdesc.h"
}
namespace android {
status_t initFFmpeg();
void deInitFFmpeg();
}
