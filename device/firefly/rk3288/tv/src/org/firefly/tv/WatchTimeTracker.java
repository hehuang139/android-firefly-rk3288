/* SPDX-License-Identifier: Apache-2.0 */
package org.firefly.tv;

import android.app.ActivityManager;
import android.app.ActivityTaskManager;
import android.app.Service;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.os.PowerManager;
import android.os.SystemClock;
import android.util.Log;
import java.util.List;

/** System-UID watchdog enforces the budget across external apps and launcher changes. */
public final class WatchTimeTracker extends Service {
    private static final String TAG = "FireflyParent";
    private final Handler handler = new Handler(Looper.getMainLooper());
    private ParentalPrefs prefs;
    private long reservedUntil;
    private String previousVideo = "";
    private final Runnable tick = new Runnable() {
        @Override
        public void run() {
            try {
                enforce();
            } catch (RuntimeException error) {
                Log.e(TAG, "Cannot inspect foreground task; returning to child home", error);
                if (prefs.enabled()) {
                    stopAllowedApps();
                    show(KidsActivity.class);
                }
            } finally {
                handler.postDelayed(this, 1000);
            }
        }
    };

    static void start(Context context) {
        context.startService(new Intent(context, WatchTimeTracker.class));
    }

    @Override
    public void onCreate() {
        super.onCreate();
        prefs = new ParentalPrefs(this);
        if (prefs.enabled()) {
            // A restarted watchdog has no in-memory record of background playback.
            stopManagedVideoApps();
        }
        handler.post(tick);
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (prefs.enabled()) {
            stopManagedVideoApps();
        }
        return START_STICKY;
    }

    @Override
    public IBinder onBind(Intent intent) { return null; }

    @Override
    public void onDestroy() {
        handler.removeCallbacksAndMessages(null);
        super.onDestroy();
    }

    private void enforce() {
        if (!prefs.enabled()) {
            previousVideo = "";
            reservedUntil = 0;
            return;
        }
        ComponentName top = foreground();
        if (top == null) {
            stopAllowedApps();
            return;
        }
        String name = top.getPackageName();
        boolean externalVideo = prefs.allowedApps().contains(name)
                || top.getClassName().equals(LiveActivity.class.getName());
        stopBackgroundVideo(externalVideo ? name : "");
        if (!getSystemService(PowerManager.class).isInteractive()) {
            stopAllowedApps();
            return;
        }
        if (externalVideo) {
            watch(name);
        } else if (!getPackageName().equals(name)) {
            stopUnapprovedVideo(name);
            show(KidsActivity.class);
        } else if (!childScreen(top.getClassName())) {
            show(KidsActivity.class);
        }
    }

    private boolean childScreen(String name) {
        return name.equals(KidsActivity.class.getName())
                || name.equals(PuzzleActivity.class.getName())
                || name.equals(ParentalActivity.class.getName());
    }

    private void stopUnapprovedVideo(String name) {
        // Keep the configured tunnel alive while returning its UI to the child home.
        if (java.util.Arrays.asList(AppLaunch.NETWORK).contains(name)) {
            return;
        }
        try {
            android.content.pm.ApplicationInfo info = getPackageManager().getApplicationInfo(name, 0);
            if (android.os.UserHandle.getAppId(info.uid) >= android.os.Process.FIRST_APPLICATION_UID) {
                stopPackage(name);
            }
        } catch (android.content.pm.PackageManager.NameNotFoundException error) {
            Log.w(TAG, "Foreground application disappeared", error);
        }
    }

    private ComponentName foreground() {
        List<ActivityManager.RunningTaskInfo> tasks = ActivityTaskManager.getInstance().getTasks(1);
        return tasks.isEmpty() ? null : tasks.get(0).topActivity;
    }

    private void watch(String name) {
        previousVideo = name;
        if (SystemClock.elapsedRealtime() < reservedUntil) {
            return;
        }
        long left = prefs.remaining();
        if (left == 0) {
            prefs.setResumePackage(name);
            stopAllowedApps();
            show(PuzzleActivity.class);
            return;
        }
        // Reserve before use: killing/restarting this process cannot restore spent time.
        long slice = Math.min(5000, left);
        prefs.charge(slice);
        reservedUntil = SystemClock.elapsedRealtime() + slice;
    }

    private void stopBackgroundVideo(String current) {
        if (!previousVideo.isEmpty() && !previousVideo.equals(current)) {
            stopPackage(previousVideo);
            previousVideo = "";
        }
    }

    private void stopAllowedApps() {
        for (String name : prefs.allowedApps()) {
            stopPackage(name);
        }
        reservedUntil = 0;
        previousVideo = "";
    }

    private void stopManagedVideoApps() {
        java.util.Set<String> names = prefs.allowedApps();
        String[][] groups = {AppLaunch.KODI, AppLaunch.YOUTUBE, AppLaunch.BILIBILI,
                AppLaunch.IQIYI, AppLaunch.YOUKU};
        for (String[] group : groups) {
            java.util.Collections.addAll(names, group);
        }
        for (String name : names) {
            stopPackage(name);
        }
        reservedUntil = 0;
        previousVideo = "";
    }

    private void stopPackage(String name) {
        if (!getPackageName().equals(name)) {
            getSystemService(ActivityManager.class).forceStopPackage(name);
        }
    }

    private void show(Class<?> activity) {
        startActivity(new Intent(this, activity).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK
                | Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_SINGLE_TOP));
    }
}
