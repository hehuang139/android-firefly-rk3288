// SPDX-License-Identifier: Apache-2.0
import java.util.Arrays;
import java.nio.file.Files;
import java.nio.file.Path;
import org.firefly.audio.HdmiAudioCapabilities;

public final class CapabilitiesTest {
    private static void checksum(byte[] edid, int start) {
        edid[start + 127] = 0;
        int sum = 0;
        for (int i = 0; i < 127; i++) sum += edid[start + i] & 255;
        edid[start + 127] = (byte) -sum;
    }
    private static byte[] fixture(boolean basic, int format, int rates, int bits) {
        byte[] edid = new byte[256];
        Arrays.fill(edid, 1, 7, (byte) 255);
        edid[126] = 1;
        edid[128] = 2; edid[129] = 3; edid[130] = 8;
        edid[131] = (byte) (basic ? 64 : 0);
        edid[132] = 0x23; edid[133] = (byte) ((format << 3) | 1);
        edid[134] = (byte) rates; edid[135] = (byte) bits;
        checksum(edid, 0); checksum(edid, 128);
        return edid;
    }
    private static void check(String name, boolean expected, byte[] edid) {
        boolean actual = HdmiAudioCapabilities.supportsPcm48Stereo16(edid);
        if (actual != expected) throw new AssertionError(name + ": " + actual);
        System.out.println("PASS " + name);
    }
    public static void main(String[] args) throws Exception {
        check("LPCM48 stereo16", true, fixture(false, 1, 4, 1));
        check("AC3 only", false, fixture(false, 2, 4, 1));
        check("44.1 kHz only", false, fixture(false, 1, 2, 1));
        check("24 bit only", false, fixture(false, 1, 4, 4));
        check("basic audio guarantee", true, fixture(true, 2, 0, 0));
        byte[] basic = fixture(true, 0, 0, 0); basic[130] = 0; checksum(basic, 128);
        check("basic audio without SAD", true, basic);
        byte[] invalid = fixture(false, 1, 4, 1); invalid[134] ^= 1;
        check("invalid checksum", false, invalid);
        check("truncated EDID", false, Arrays.copyOf(fixture(false, 1, 4, 1), 200));
        byte[] malformed = fixture(true, 1, 4, 1); malformed[130] = 5; checksum(malformed, 128);
        check("data block overrun", false, malformed);
        if (args.length == 1) check("actual DELL no-audio EDID", false, Files.readAllBytes(Path.of(args[0])));
    }
}
