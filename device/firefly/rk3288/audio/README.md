# HDMI audio integration

The final source includes an HDMI external output port and a persistent
platform-signed route monitor. Both HAL and Java monitor validate current EDID support
for 48 kHz, PCM16, two channels before connecting HDMI. Analog ES8323 remains
the default attached fallback. Disconnecting the current HDMI route closes its
PCM and recreates the analog stream through audio policy; analog playback while
the HDMI cable is unplugged has not been measured.

This change was installed on the target board. The historical DELL P2017H
negative test correctly kept analog output, and its four-second 48 kHz
AudioTrack test completed 192,000 frames. Offline EDID/ELD and routing cases passed.
After correcting the external template address, HDMI playback on a 32V3H-H6A
was audibly confirmed for direct PCM1 left/right tones, Android AudioTrack
left/right tones, and video. A subsequent software reboot verified monitor
autostart, matching payload hashes, read-only vendor/system_ext, and another
192,000-frame AudioTrack run routed to HDMI, with PCM1 running and PCM0 closed.
The stereo listening confirmations preceded that reboot; its AudioTrack check
measured software progress and routing. A later physical unplug, five-second
wait, and reconnect during video restored picture and sound automatically
without another reboot. Post-reconnect checks found HDMI connected and PCM1
running with PCM0 closed. The monitor's intermediate disconnected state was
not captured, and analog playback while unplugged was not measured. Route-open
failure recovery, cold power cycling, and a clean full-image reflash remain
unverified.
See [HDMI validation](../../../../docs/validation/hdmi-audio.json).
SELinux remains permissive; this is not an enforcing-policy implementation.

The external HDMI template uses an empty address. Android clears the instance
address before matching an external-device template; using `firefly-hdmi` on the
template makes that lookup fail with `BAD_VALUE` before entering the HAL. The
monitor still identifies the concrete connected device as `firefly-hdmi`, and
AIDL Module copies that address to the allocated connection port. The analog
fallback keeps its fixed `firefly-es8323` address.

`tests/eld-parser-test.cpp` is an extracted C++ parser fixture and does not
replace compilation of the real HAL. `monitor/tests/CapabilitiesTest.java`
tests the Java capabilities implementation. The complete HAL and monitor APK
were separately compiled against the pinned Android platform. Build records
containing machine paths and executable binaries are deliberately excluded.
