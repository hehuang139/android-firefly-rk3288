// SPDX-License-Identifier: Apache-2.0
package org.firefly.audio;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
public final class HdmiAudioBootReceiver extends BroadcastReceiver {
    @Override public void onReceive(Context context, Intent intent) {
        context.startService(new Intent(context, HdmiAudioService.class));
    }
}
