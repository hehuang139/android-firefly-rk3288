# Original Firefly-RK3399 audio candidate

The AIDL audio service uses two independent ALSA cards: `FireflyRT5640` for the
3.5 mm analog output and `FireflyHDMI` for HDMI. Both use PCM device 0. Card
numbers are discovered by exact ID, never assumed to match another board.

The RT5640 route is based on the controls and DAPM graph in pinned Linux
6.18.60. DAC1 is set to 0 dB and the headphone volume path to -12 dB before
unmuting. Missing mixer controls reject the stream. Android applies the user's
volume in software. Physical left/right output and recovery remain untested.

The external HDMI port and platform-signed route monitor validate the current
sink's EDID/ELD for 48 kHz, PCM16, stereo. The HAL also checks the actual HDMI
PCM. The external template address remains empty, because Android removes the
instance address when matching templates; the monitor uses `firefly-hdmi` on
the connected instance. Analog uses fixed address `firefly-rt5640`.

The design retains the RK3288 fixes for routing and bounded PCM recovery, but
its old ES8323/PCM1 listening results are not RK3399 evidence. Build, direct
PCM, Android AudioTrack, video, reboot and HDMI hotplug are separate gates.
SELinux remains permissive in this userdebug bring-up candidate.
