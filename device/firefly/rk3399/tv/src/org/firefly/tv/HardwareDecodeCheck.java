/* SPDX-License-Identifier: Apache-2.0 */
package org.firefly.tv;

import android.media.MediaCodec;
import android.media.MediaCodecInfo;
import android.media.MediaExtractor;
import android.media.MediaFormat;
import android.os.SystemClock;
import org.json.JSONException;
import org.json.JSONObject;
import java.io.IOException;
import java.io.InterruptedIOException;
import java.nio.ByteBuffer;

/** Decodes a complete local sample with an explicitly named hardware component. */
final class HardwareDecodeCheck {
    private HardwareDecodeCheck() { }

    static JSONObject run(String kind) throws IOException, JSONException {
        boolean hevc = "hevc".equals(kind);
        String mime = hevc ? "video/hevc" : "video/avc";
        String name = hevc ? "c2.firefly.hevc.decoder" : "c2.firefly.h264.decoder";
        String path = "/product/etc/firefly-tv/" + (hevc ? "hevc" : "h264") + "-1080p.mp4";
        MediaExtractor extractor = new MediaExtractor();
        MediaCodec codec = null;
        try {
            extractor.setDataSource(path);
            int track = videoTrack(extractor, mime);
            extractor.selectTrack(track);
            MediaFormat format = extractor.getTrackFormat(track);
            format.setInteger(MediaFormat.KEY_COLOR_FORMAT,
                    MediaCodecInfo.CodecCapabilities.COLOR_FormatYUV420Flexible);
            codec = MediaCodec.createByCodecName(name);
            codec.configure(format, null, null, 0);
            codec.start();
            JSONObject result = decode(extractor, codec);
            result.put("component", codec.getName());
            result.put("sample", path);
            result.put("mime", mime);
            result.put("width", format.getInteger(MediaFormat.KEY_WIDTH));
            result.put("height", format.getInteger(MediaFormat.KEY_HEIGHT));
            result.put("hardwareAccelerated", codec.getCodecInfo().isHardwareAccelerated());
            return result;
        } finally {
            if (codec != null) {
                codec.release();
            }
            extractor.release();
        }
    }

    private static int videoTrack(MediaExtractor extractor, String mime) throws IOException {
        for (int index = 0; index < extractor.getTrackCount(); index++) {
            if (mime.equals(extractor.getTrackFormat(index).getString(MediaFormat.KEY_MIME))) {
                return index;
            }
        }
        throw new IOException("Sample has no " + mime + " track");
    }

    private static JSONObject decode(MediaExtractor extractor, MediaCodec codec)
            throws IOException, JSONException {
        MediaCodec.BufferInfo info = new MediaCodec.BufferInfo();
        long started = SystemClock.elapsedRealtime();
        boolean inputEnded = false;
        boolean outputEnded = false;
        int frames = 0;
        long bytes = 0;
        while (!outputEnded) {
            checkDeadline(started);
            if (!inputEnded) {
                inputEnded = queueInput(extractor, codec);
            }
            int output = codec.dequeueOutputBuffer(info, 10_000);
            if (output >= 0) {
                if (info.size > 0 && (info.flags & MediaCodec.BUFFER_FLAG_CODEC_CONFIG) == 0) {
                    frames++;
                    bytes += info.size;
                }
                outputEnded = (info.flags & MediaCodec.BUFFER_FLAG_END_OF_STREAM) != 0;
                codec.releaseOutputBuffer(output, false);
            }
        }
        if (frames != 300) {
            throw new IOException("Hardware component produced " + frames + " of 300 sample frames");
        }
        return new JSONObject().put("completed", true).put("frames", frames)
                .put("outputBytes", bytes)
                .put("elapsedMs", SystemClock.elapsedRealtime() - started);
    }

    private static boolean queueInput(MediaExtractor extractor, MediaCodec codec)
            throws IOException {
        int index = codec.dequeueInputBuffer(10_000);
        if (index < 0) {
            return false;
        }
        ByteBuffer input = codec.getInputBuffer(index);
        if (input == null) {
            throw new IOException("Hardware component returned no input buffer");
        }
        input.clear();
        int size = extractor.readSampleData(input, 0);
        if (size < 0) {
            codec.queueInputBuffer(index, 0, 0, 0, MediaCodec.BUFFER_FLAG_END_OF_STREAM);
            return true;
        }
        codec.queueInputBuffer(index, 0, size, extractor.getSampleTime(), 0);
        extractor.advance();
        return false;
    }

    private static void checkDeadline(long started) throws IOException {
        if (Thread.currentThread().isInterrupted()) {
            throw new InterruptedIOException("Decode check cancelled");
        }
        if (SystemClock.elapsedRealtime() - started > 45_000) {
            throw new IOException("Hardware decode check timed out after 45 seconds");
        }
    }
}
