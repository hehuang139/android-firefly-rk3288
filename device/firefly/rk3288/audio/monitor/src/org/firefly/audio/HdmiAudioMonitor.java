// SPDX-License-Identifier: Apache-2.0
package org.firefly.audio;

import android.media.AudioDeviceAttributes;
import android.media.AudioSystem;
import android.media.IAudioService;
import android.os.IBinder;
import android.os.ServiceManager;
import android.os.SystemClock;
import android.util.Log;

/** Board-specific hotplug bridge: report a real HDMI device through AudioService. */
public final class HdmiAudioMonitor implements Runnable {
    private static final String TAG = "FireflyHdmiAudio";
    private static final String ADDRESS = "firefly-hdmi";
    private static final AudioDeviceAttributes DEVICE = new AudioDeviceAttributes(
            AudioSystem.DEVICE_OUT_HDMI, ADDRESS, "Firefly HDMI");
    private long lastAttempt = -30000;
    private Boolean previousDesired;
    private int stableSamples;

    private void tick(boolean checkOnly) throws Exception {
        boolean desired = HdmiAudioCapabilities.isReady();
        int actual = AudioSystem.getDeviceConnectionState(AudioSystem.DEVICE_OUT_HDMI, ADDRESS);
        if (checkOnly) {
            System.out.println("HDMI_PCM48_STEREO16=" + desired + " POLICY_CONNECTED="
                    + (actual == AudioSystem.DEVICE_STATE_AVAILABLE));
            return;
        }
        if (previousDesired == null || previousDesired != desired) {
            previousDesired = desired;
            stableSamples = 1;
            Log.i(TAG, "HDMI PCM48/stereo/16 capability=" + desired);
            return;
        }
        stableSamples++;
        int wanted = desired ? AudioSystem.DEVICE_STATE_AVAILABLE
                             : AudioSystem.DEVICE_STATE_UNAVAILABLE;
        if (actual == wanted || stableSamples < 2) return;
        long now = SystemClock.elapsedRealtime();
        if (now - lastAttempt < 10000) return;
        IBinder binder = ServiceManager.getService("audio");
        if (binder == null || !binder.isBinderAlive()) return;
        IAudioService audio = IAudioService.Stub.asInterface(binder);
        lastAttempt = now;
        if (desired) {
            // The Java inventory can survive a native audioserver/HAL restart.
            // An ordered disconnect/connect reconciles that stale inventory.
            audio.setWiredDeviceConnectionState(DEVICE, AudioSystem.DEVICE_STATE_UNAVAILABLE, TAG);
        }
        audio.setWiredDeviceConnectionState(DEVICE, wanted, TAG);
        Log.i(TAG, "Requested HDMI connection=" + desired);
    }

    @Override public void run() {
        while (!Thread.currentThread().isInterrupted()) {
            try {
                tick(false);
                Thread.sleep(2000);
            } catch (InterruptedException stopped) {
                Thread.currentThread().interrupt();
            } catch (Exception unavailable) {
                Log.w(TAG, "Audio service or capabilities unavailable; retrying", unavailable);
                try { Thread.sleep(5000); }
                catch (InterruptedException stopped) { Thread.currentThread().interrupt(); }
            }
        }
    }

    public static void main(String[] args) throws Exception {
        HdmiAudioMonitor monitor = new HdmiAudioMonitor();
        if (args.length == 1 && "--check".equals(args[0])) monitor.tick(true);
        else monitor.run();
    }
}
