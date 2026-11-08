/* SPDX-License-Identifier: Apache-2.0 */
package org.firefly.tv;

import android.app.Activity;
import android.view.KeyEvent;

/** Explicit Escape handling, independent of Android's predictive Back dispatch. */
class TvActivity extends Activity {
    protected void handleBackAction() {
        finish();
    }

    @Override public boolean dispatchKeyEvent(KeyEvent event) {
        if (event.getKeyCode() == KeyEvent.KEYCODE_ESCAPE && event.hasNoModifiers()) {
            if (event.getAction() == KeyEvent.ACTION_UP && !event.isCanceled()) {
                handleBackAction();
            }
            return true;
        }
        return super.dispatchKeyEvent(event);
    }
}
