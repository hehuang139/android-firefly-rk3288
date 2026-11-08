/* SPDX-License-Identifier: Apache-2.0 */
package org.firefly.tv;

import android.app.ActivityManager;
import android.app.ActivityTaskManager;
import android.app.Service;
import android.content.ComponentName;
import android.os.PowerManager;
import android.os.SystemClock;
import java.lang.reflect.Field;

/** Execute the real watchdog tick with deterministic task/time/service substitutes. */
public final class WatchTimeTrackerHostTest {
    private static int checks;
    private WatchTimeTrackerHostTest() { }

    private static void check(boolean value, String message) {
        checks++;
        if (!value) throw new AssertionError(message);
    }

    public static int run() {
        WatchTimeTracker.setInternalVideoActive(false);
        ActivityManager.stopped.clear();
        Service.started.clear();
        ActivityTaskManager.top = null;
        ActivityTaskManager.failure = false;
        PowerManager.interactive = true;
        SystemClock.now = 10_000;
        WatchTimeTracker service = new WatchTimeTracker();
        service.onCreate();
        ParentalPrefs prefs = new ParentalPrefs(service);
        check(ActivityManager.stopped.isEmpty(), "disabled watchdog does not stop applications");
        prefs.setPin("2468");
        prefs.allow("fixture.kodi", true);
        prefs.setEnabled(true);
        service.onStartCommand(null, 0, 1);
        int stopped = ActivityManager.stopped.size();
        check(stopped > 0, "entering protected mode stops stale background video once");
        service.onStartCommand(null, 0, 2);
        check(ActivityManager.stopped.size() == stopped, "repeated start does not force-stop again");

        top("org.firefly.tv", PuzzleActivity.class.getName());
        tick(service);
        check(prefs.dailyUsed() == 0 && Service.started.isEmpty(), "games neither consume time nor redirect");
        top("org.firefly.tv", ParentalActivity.class.getName());
        tick(service);
        check(prefs.dailyUsed() == 0 && Service.started.isEmpty(), "PIN-gated parent panel remains usable");
        top("fixture.kodi", "fixture.kodi.Player");
        tick(service);
        check(prefs.dailyUsed() == 5000, "allowed video reserves one five-second slice");
        service.onStartCommand(null, 0, 3);
        check(ActivityManager.stopped.size() == stopped, "starting monitor while video is visible keeps it playing");
        SystemClock.now += 1000;
        tick(service);
        check(prefs.dailyUsed() == 5000, "polling cannot charge the same reserved interval twice");

        top("org.firefly.tv", PuzzleActivity.class.getName());
        tick(service);
        check(ActivityManager.stopped.size() == stopped + 1, "leaving external video stops its background playback");
        SystemClock.now += 10_000;
        tick(service);
        check(prefs.dailyUsed() == 5000, "time in a game remains free");

        ActivityTaskManager.top = null;
        tick(service);
        int suspendedStops = ActivityManager.stopped.size();
        SystemClock.now += 20_000;
        tick(service);
        check(ActivityManager.stopped.size() == suspendedStops && Service.started.isEmpty(),
                "unknown foreground suspends once and does not launch a child-home loop");
        ActivityTaskManager.failure = true;
        tick(service);
        tick(service);
        check(Service.started.isEmpty(), "task lookup errors do not start an activity loop");
        ActivityTaskManager.failure = false;

        top("org.firefly.tv", LiveActivity.class.getName());
        WatchTimeTracker.setInternalVideoActive(true);
        tick(service);
        check(prefs.dailyUsed() == 10_000, "confirmed internal child video is metered");
        WatchTimeTracker.setInternalVideoActive(false);
        SystemClock.now += 6000;
        tick(service);
        check(prefs.dailyUsed() == 10_000 && lastStarted() == KidsActivity.class,
                "ordinary Live cannot claim the child-video exception or consume time");
        Service.started.clear();
        SystemClock.now += 3000;
        top("org.firefly.tv", PuzzleActivity.class.getName());
        tick(service);
        prefs.allow("org.firefly.tv", true);
        tick(service);
        check(prefs.dailyUsed() == 10_000 && Service.started.isEmpty(),
                "even an erroneous own-package allow entry cannot meter games");
        prefs.allow("org.firefly.tv", false);

        top("fixture.kodi", "fixture.kodi.Player");
        prefs.charge(15 * 60_000L);
        tick(service);
        check(lastStarted() == PuzzleActivity.class, "expired video is stopped and sent to the challenge");
        check(prefs.remaining() == 0, "timeout never replenishes the session");
        int redirects = Service.started.size();
        tick(service);
        check(Service.started.size() == redirects, "slow foreground transition does not flood activity launches");
        prefs.setEnabled(false);
        SystemClock.now += 10_000;
        top("fixture.other", "fixture.other.Screen");
        tick(service);
        check(Service.started.size() == redirects, "disabling protection leaves other apps alone");

        prefs.setEnabled(true);
        service.onStartCommand(null, 0, 4);
        top("org.firefly.tv", LiveActivity.class.getName());
        WatchTimeTracker.setInternalVideoActive(true);
        ActivityTaskManager.top = null;
        Service.started.clear();
        tick(service);
        check(lastStarted() == KidsActivity.class, "unknown internal playback leaves the player to release it");
        tick(service);
        check(Service.started.size() == 1, "internal suspension redirects only once");
        WatchTimeTracker.setInternalVideoActive(false);
        service.onDestroy();
        return checks;
    }

    private static void top(String pkg, String cls) {
        ActivityTaskManager.top = new ComponentName(pkg, cls);
    }

    private static Class<?> lastStarted() {
        return Service.started.isEmpty() ? null : Service.started.get(Service.started.size() - 1).target;
    }

    private static void tick(WatchTimeTracker service) {
        try {
            Field field = WatchTimeTracker.class.getDeclaredField("tick");
            field.setAccessible(true);
            ((Runnable) field.get(service)).run();
        } catch (ReflectiveOperationException error) {
            throw new AssertionError(error);
        }
    }
}
