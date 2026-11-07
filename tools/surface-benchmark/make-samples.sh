#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
mkdir -p assets generated-fixture-info
for fps in 30 60; do
  level=4.1
  if [ "$fps" = 60 ]; then level=4.2; fi
  ffmpeg -hide_banner -loglevel error -f lavfi \
    -i "testsrc2=size=1920x1080:rate=$fps" -t 12 -c:v libx264 \
    -preset fast -threads 4 -profile:v high -level:v "$level" \
    -pix_fmt yuv420p -b:v 6000k -maxrate 8000k -bufsize 12000k \
    -g "$((fps*2))" -bf 3 -an -movflags +faststart \
    -y "assets/h264-1080p$fps.mp4"
  ffprobe -v error -show_streams -of json "assets/h264-1080p$fps.mp4" \
    > "generated-fixture-info/sample-$fps-info.json"
  ffmpeg -hide_banner -loglevel error -i "assets/h264-1080p$fps.mp4" \
    -pix_fmt yuv420p -f hash -hash sha256 \
    -y "generated-fixture-info/reference-$fps-i420.sha256"
done
sha256sum assets/*.mp4 > generated-fixture-info/samples.sha256
