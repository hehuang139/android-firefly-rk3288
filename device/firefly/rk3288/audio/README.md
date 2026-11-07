# HDMI audio integration

The final source includes an HDMI external output port and a persistent
platform-signed route monitor. Both HAL and Java monitor validate ELD support
for 48 kHz, PCM16, two channels before connecting HDMI. Analog ES8323 remains
the default attached fallback. Disconnecting the current HDMI route closes its
PCM and recreates the analog stream through audio policy.

This change was installed on the target board. A display without HDMI audio
was correctly left on analog; a four-second 48 kHz AudioTrack write completed
192,000 frames. Offline ELD/routing cases passed. Software reboot, persistent monitor autostart and read-only vendor/system_ext
partitions were verified; see docs/validation/hdmi-audio.json. Actual sound on an
HDMI-capable television and physical HDMI unplug/replug were not validated.
SELinux remains permissive; this is not an enforcing-policy implementation.

`tests/eld-parser-test.cpp` is an extracted C++ parser fixture and does not
replace compilation of the real HAL. `monitor/tests/CapabilitiesTest.java`
tests the Java capabilities implementation. The complete HAL and monitor APK
were separately compiled against the pinned Android platform. Build records
containing machine paths and executable binaries are deliberately excluded.
