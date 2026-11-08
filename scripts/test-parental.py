#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run production budget/PIN/puzzle logic on a JVM with a preferences test double.

Task inspection, service scheduling and playback are controlled test doubles;
this checks decisions and bookkeeping, not the Android runtime or real playback.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

parser = argparse.ArgumentParser()
parser.add_argument('--jdk', type=Path, required=True)
parser.add_argument('--report', type=Path, required=True)
args = parser.parse_args()
port = Path(__file__).resolve().parents[1]
sources = port / 'device/firefly/rk3288/tv/src/org/firefly/tv'
stubs = {
    'android/content/SharedPreferences.java': '''package android.content;
import java.util.*;
public final class SharedPreferences {
 private final Map<String,Object> values = new HashMap<>();
 public boolean contains(String key) {return values.containsKey(key);}
 public boolean getBoolean(String key, boolean def) {return (Boolean)values.getOrDefault(key,def);}
 public int getInt(String key, int def) {return (Integer)values.getOrDefault(key,def);}
 public long getLong(String key, long def) {return (Long)values.getOrDefault(key,def);}
 public String getString(String key, String def) {return (String)values.getOrDefault(key,def);}
 @SuppressWarnings("unchecked") public Set<String> getStringSet(String key, Set<String> def) {
   return (Set<String>) values.getOrDefault(key,def);}
 public Editor edit() {return new Editor();}
 public final class Editor {
   private final Map<String,Object> pending = new HashMap<>();
   public Editor putBoolean(String k,boolean v) {pending.put(k,v);return this;}
   public Editor putInt(String k,int v) {pending.put(k,v);return this;}
   public Editor putLong(String k,long v) {pending.put(k,v);return this;}
   public Editor putString(String k,String v) {pending.put(k,v);return this;}
   public Editor putStringSet(String k,Set<String> v) {pending.put(k,new HashSet<>(v));return this;}
   public boolean commit() {values.putAll(pending);return true;}
 }
}''',
    'android/content/Context.java': '''package android.content;
public class Context {
 public static final int MODE_PRIVATE=0;
 private final SharedPreferences prefs = new SharedPreferences();
 public Context createDeviceProtectedStorageContext() {return this;}
 public SharedPreferences getSharedPreferences(String name,int mode) {return prefs;}
 public String getPackageName() {return "org.firefly.tv";}
 public ComponentName startService(Intent intent) {return null;}
 public android.content.pm.PackageManager getPackageManager() {return new android.content.pm.PackageManager();}
 public <T> T getSystemService(Class<T> type) {
   if (type == android.app.ActivityManager.class) return type.cast(new android.app.ActivityManager());
   if (type == android.os.PowerManager.class) return type.cast(new android.os.PowerManager());
   throw new IllegalArgumentException(type.getName());
 }
}''',
    'android/util/Base64.java': '''package android.util;
public final class Base64 {
 public static final int NO_WRAP=2;
 public static byte[] decode(String s,int flags) {return java.util.Base64.getDecoder().decode(s);}
 public static String encodeToString(byte[] v,int flags) {
   return java.util.Base64.getEncoder().encodeToString(v);}
}''',
    'android/content/ComponentName.java': '''package android.content;
public final class ComponentName {
 private final String pkg, cls;
 public ComponentName(String pkg,String cls) {this.pkg=pkg;this.cls=cls;}
 public String getPackageName() {return pkg;}
 public String getClassName() {return cls;}
}''',
    'android/content/Intent.java': '''package android.content;
public final class Intent {
 public static final int FLAG_ACTIVITY_NEW_TASK=1, FLAG_ACTIVITY_CLEAR_TOP=2, FLAG_ACTIVITY_SINGLE_TOP=4;
 public final Class<?> target;
 public Intent(Context context,Class<?> target) {this.target=target;}
 public Intent addFlags(int flags) {return this;}
}''',
    'android/content/pm/ApplicationInfo.java': '''package android.content.pm;
public final class ApplicationInfo { public int uid=10001; }''',
    'android/content/pm/PackageManager.java': '''package android.content.pm;
public final class PackageManager {
 public ApplicationInfo getApplicationInfo(String name,int flags) throws NameNotFoundException {
   return new ApplicationInfo();
 }
 public static final class NameNotFoundException extends Exception { }
}''',
    'android/app/ActivityManager.java': '''package android.app;
public final class ActivityManager {
 public static final java.util.List<String> stopped=new java.util.ArrayList<>();
 public void forceStopPackage(String name) {stopped.add(name);}
 public static final class RunningTaskInfo {
   public android.content.ComponentName topActivity;
 }
}''',
    'android/app/ActivityTaskManager.java': '''package android.app;
public final class ActivityTaskManager {
 public static android.content.ComponentName top;
 public static boolean failure;
 public static ActivityTaskManager getInstance() {return new ActivityTaskManager();}
 public java.util.List<ActivityManager.RunningTaskInfo> getTasks(int count) {
   if (failure) throw new IllegalStateException("fixture task lookup failure");
   if (top==null) return java.util.Collections.emptyList();
   ActivityManager.RunningTaskInfo task=new ActivityManager.RunningTaskInfo();
   task.topActivity=top;
   return java.util.Collections.singletonList(task);
 }
}''',
    'android/app/Service.java': '''package android.app;
public class Service extends android.content.Context {
 public static final int START_STICKY=1;
 public static final java.util.List<android.content.Intent> started=new java.util.ArrayList<>();
 public void onCreate() { }
 public int onStartCommand(android.content.Intent intent,int flags,int startId) {return START_STICKY;}
 public android.os.IBinder onBind(android.content.Intent intent) {return null;}
 public void onDestroy() { }
 public void startActivity(android.content.Intent intent) {started.add(intent);}
}''',
    'android/os/Handler.java': '''package android.os;
public final class Handler {
 public Handler(Looper looper) { }
 public void post(Runnable action) { }
 public void postDelayed(Runnable action,long delay) { }
 public void removeCallbacksAndMessages(Object token) { }
}''',
    'android/os/IBinder.java': 'package android.os; public interface IBinder { }',
    'android/os/Looper.java': '''package android.os;
public final class Looper { public static Looper getMainLooper() {return new Looper();} }''',
    'android/os/PowerManager.java': '''package android.os;
public final class PowerManager {
 public static boolean interactive=true;
 public boolean isInteractive() {return interactive;}
}''',
    'android/os/SystemClock.java': '''package android.os;
public final class SystemClock {
 public static long now=10000;
 public static long elapsedRealtime() {return now;}
}''',
    'android/os/UserHandle.java': '''package android.os;
public final class UserHandle { public static int getAppId(int uid) {return uid;} }''',
    'android/os/Process.java': '''package android.os;
public final class Process { public static final int FIRST_APPLICATION_UID=10000; }''',
    'android/util/Log.java': '''package android.util;
public final class Log {
 public static int e(String tag,String text,Throwable error) {return 0;}
 public static int w(String tag,String text,Throwable error) {return 0;}
}''',
    'org/firefly/tv/ActivityFixtures.java': '''package org.firefly.tv;
final class KidsActivity { }
final class PuzzleActivity { }
final class ParentalActivity { }
final class LiveActivity { }
final class AppLaunch {
 static final String[] NETWORK={"fixture.tunnel"};
 static final String[] KODI={"fixture.kodi"}, YOUTUBE={"fixture.youtube"},
   BILIBILI={"fixture.bilibili"}, IQIYI={"fixture.iqiyi"}, YOUKU={"fixture.youku"};
}'''
}
inputs = [sources / (name + '.java') for name in ['WatchBudget', 'ParentalPrefs', 'PuzzleRound', 'WatchTimeTracker']]
inputs.append(port / 'tests/ParentalHostTest.java')
inputs.append(port / 'tests/WatchTimeTrackerHostTest.java')
with tempfile.TemporaryDirectory() as directory:
    work = Path(directory)
    generated = []
    for relative, contents in stubs.items():
        path = work / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents)
        generated.append(path)
    compile_result = subprocess.run([str(args.jdk / 'bin/javac'), '--release', '17', '-d',
        str(work / 'classes'), *map(str, inputs + generated)], capture_output=True, text=True)
    run_result = None
    if compile_result.returncode == 0:
        run_result = subprocess.run([str(args.jdk / 'bin/java'), '-ea', '-cp',
            str(work / 'classes'), 'org.firefly.tv.ParentalHostTest'], capture_output=True, text=True)
    report = {'scope': 'JVM production budget/PIN/puzzle/watchdog decisions; preferences, tasks and service test doubles',
              'compile_exit': compile_result.returncode,
              'compile_output': compile_result.stdout + compile_result.stderr,
              'run_exit': None if run_result is None else run_result.returncode,
              'run_output': '' if run_result is None else run_result.stdout + run_result.stderr,
              'passed': run_result is not None and run_result.returncode == 0,
              'inputs': {str(x.relative_to(port)): hashlib.sha256(x.read_bytes()).hexdigest()
                         for x in inputs}}
args.report.parent.mkdir(parents=True, exist_ok=True)
args.report.write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report))
raise SystemExit(not report['passed'])
