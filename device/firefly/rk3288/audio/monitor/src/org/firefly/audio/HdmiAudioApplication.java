// SPDX-License-Identifier: Apache-2.0
package org.firefly.audio;
import android.app.Application;
import android.content.Intent;
public final class HdmiAudioApplication extends Application {
    @Override public void onCreate() {
        super.onCreate();
        startService(new Intent(this, HdmiAudioService.class));
    }
}
