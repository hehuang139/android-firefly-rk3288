/* SPDX-License-Identifier: Apache-2.0 */
package org.firefly.tv;

import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.util.Log;
import android.widget.Toast;

/** Resolves installed TV activities first, then the package's ordinary launcher. */
final class AppLaunch {
    private static final String TAG = "FireflyLaunch";
    static final String[] KODI = {"org.xbmc.kodi"};
    static final String[] YOUTUBE = {"app.smarttube.fdroid", "com.liskovsoft.smarttubetv.beta"};
    static final String[] NETWORK = {"com.github.metacubex.clash.meta"};
    static final String[] BILIBILI = {"com.xiaodianshi.tv.yst", "com.bilibili.tv", "dev.aaa1115910.bv"};
    static final String[] YOUKU = {"com.cibn.tv", "com.youku.tv"};
    static final String[] IQIYI = {"com.gitvdemo.video", "com.gitvvideo"};

    private AppLaunch() { }

    static Intent resolve(PackageManager manager, String... packages) {
        for (String name : packages) {
            Intent intent = manager.getLeanbackLaunchIntentForPackage(name);
            if (intent == null) {
                intent = manager.getLaunchIntentForPackage(name);
            }
            if (intent != null) {
                return intent;
            }
        }
        return null;
    }

    static boolean available(Activity activity, String... packages) {
        return resolve(activity.getPackageManager(), packages) != null;
    }

    static void open(Activity activity, String... packages) {
        Intent intent = resolve(activity.getPackageManager(), packages);
        if (intent == null) {
            Toast.makeText(activity, "应用尚未安装，请在应用列表中查看", Toast.LENGTH_LONG).show();
            return;
        }
        action(activity, intent);
    }

    static boolean action(Activity activity, Intent intent) {
        ParentalPrefs prefs = new ParentalPrefs(activity);
        if (prefs.enabled() && !allowed(activity, intent, prefs)) {
            Toast.makeText(activity, "请在儿童专区选择家长允许的应用", Toast.LENGTH_LONG).show();
            return false;
        }
        try {
            activity.startActivity(intent);
            return true;
        } catch (ActivityNotFoundException | SecurityException error) {
            Log.w(TAG, "Activity unavailable", error);
            Toast.makeText(activity, "此入口暂不可用", Toast.LENGTH_LONG).show();
            return false;
        }
    }

    private static boolean allowed(Activity activity, Intent intent, ParentalPrefs prefs) {
        android.content.ComponentName component = intent.resolveActivity(activity.getPackageManager());
        return component != null && prefs.allowedApps().contains(component.getPackageName())
                && prefs.remaining() > 0;
    }
}
