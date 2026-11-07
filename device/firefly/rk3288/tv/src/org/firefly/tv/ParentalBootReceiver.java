/* SPDX-License-Identifier: Apache-2.0 */
package org.firefly.tv;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/** Restart enforcement after power loss, before children can launch a video. */
public final class ParentalBootReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context context, Intent intent) {
        if (Intent.ACTION_BOOT_COMPLETED.equals(intent.getAction())) {
            WatchTimeTracker.start(context);
        }
    }
}
