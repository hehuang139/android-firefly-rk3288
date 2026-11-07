// SPDX-License-Identifier: Apache-2.0
package org.firefly.audio;
import android.app.Service;
import android.content.Intent;
import android.os.IBinder;

public final class HdmiAudioService extends Service {
    private Thread worker;
    @Override public void onCreate() {
        super.onCreate();
        worker = new Thread(new HdmiAudioMonitor(), "FireflyHdmiAudio");
        worker.start();
    }
    @Override public int onStartCommand(Intent intent, int flags, int startId) {
        return START_STICKY;
    }
    @Override public void onDestroy() {
        if (worker != null) worker.interrupt();
        super.onDestroy();
    }
    @Override public IBinder onBind(Intent intent) { return null; }
}
