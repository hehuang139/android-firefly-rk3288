// SPDX-License-Identifier: Apache-2.0
package org.firefly.audio;

import java.io.IOException;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;

/** Only advertise the PCM format implemented by the Firefly audio HAL. */
public final class HdmiAudioCapabilities {
    private HdmiAudioCapabilities() {}

    public static boolean supportsPcm48Stereo16(byte[] edid) {
        final byte[] header = {0, -1, -1, -1, -1, -1, -1, 0};
        if (edid.length < 128) return false;
        for (int i = 0; i < header.length; i++) if (edid[i] != header[i]) return false;
        int blocks = 1 + (edid[126] & 255);
        if (edid.length != blocks * 128) return false;
        for (int block = 0; block < blocks; block++) {
            int checksum = 0;
            for (int i = 0; i < 128; i++) checksum += edid[block * 128 + i] & 255;
            if ((checksum & 255) != 0) return false;
        }
        boolean supported = false;
        for (int block = 1; block < blocks; block++) {
            int start = block * 128;
            if ((edid[start] & 255) != 2 || (edid[start + 1] & 255) < 3) continue;
            int end = edid[start + 2] & 255;
            // CTA offset 0 means no data blocks. Values 1..3 and 128+ are invalid.
            if (end != 0 && (end < 4 || end > 127)) return false;
            boolean basic = (edid[start + 3] & 64) != 0;
            boolean pcm = false;
            for (int pos = 4; end != 0 && pos < end;) {
                int tagLength = edid[start + pos] & 255;
                int length = tagLength & 31;
                if (pos + 1 + length > end) return false;
                if ((tagLength >> 5) == 1) {
                    if (length % 3 != 0) return false;
                    for (int sad = pos + 1; sad < pos + 1 + length; sad += 3) {
                        int codingChannels = edid[start + sad] & 255;
                        int rates = edid[start + sad + 1] & 255;
                        int bits = edid[start + sad + 2] & 255;
                        if (((codingChannels >> 3) & 15) == 1
                                && (codingChannels & 7) >= 1
                                && (rates & 4) != 0 && (bits & 1) != 0) pcm = true;
                    }
                }
                pos += 1 + length;
            }
            // CTA Basic Audio guarantees two-channel 16-bit LPCM at 48 kHz.
            supported |= basic || pcm;
        }
        return supported;
    }

    public static boolean isReady() throws IOException {
        boolean cardReady = false;
        for (int card = 0; card < 32; card++) {
            Path id = Paths.get("/proc/asound/card" + card + "/id");
            if (Files.isReadable(id) && "FireflyES8323".equals(Files.readString(id).trim())
                    && Files.exists(Paths.get("/dev/snd/pcmC" + card + "D1p"))) {
                cardReady = true;
                break;
            }
        }
        if (!cardReady) return false;
        try (DirectoryStream<Path> connectors = Files.newDirectoryStream(
                Paths.get("/sys/class/drm"), "card*-HDMI-A-*")) {
            for (Path connector : connectors) {
                try {
                    if ("connected".equals(Files.readString(connector.resolve("status")).trim())
                            && supportsPcm48Stereo16(Files.readAllBytes(connector.resolve("edid")))) {
                        return true;
                    }
                } catch (IOException unavailable) {
                    // A connector can disappear between listing and reading its capabilities.
                }
            }
        }
        return false;
    }
}
