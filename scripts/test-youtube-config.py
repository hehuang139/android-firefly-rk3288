#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Compile production AppLaunch with Android stubs and test product app selection."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import xml.etree.ElementTree as ET

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--jdk", type=Path, required=True)
parser.add_argument("--report", type=Path)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
source = root / "device/firefly/rk3399/tv"
config = ET.parse(source / "res/values/apps.xml").getroot()
assert [item.text for item in config.find("string-array[@name='config_youtube_packages']")] == ["com.google.android.youtube.tv"]
assert config.find("string[@name='config_youtube_title']").text == "YouTube"
stubs = {
"android/content/res/Resources.java": '''package android.content.res;
public class Resources { public String[] packages; public String title;
 public int getIdentifier(String n,String t,String p) {return n.endsWith("packages")?(packages==null?0:1):(title==null?0:2);}
 public String[] getStringArray(int id){return packages.clone();} public String getString(int id){return title;} }''',
"android/content/Context.java": '''package android.content;
public class Context { public final android.content.res.Resources resources=new android.content.res.Resources();
 public android.content.res.Resources getResources(){return resources;} public String getPackageName(){return "org.firefly.tv";} }''',
"android/content/ComponentName.java": '''package android.content;
public class ComponentName {private final String name; public ComponentName(String n){name=n;} public String getPackageName(){return name;} }''',
"android/content/Intent.java": '''package android.content;
public class Intent {public final String name; public Intent(String n){name=n;}
 public ComponentName resolveActivity(android.content.pm.PackageManager p){return new ComponentName(name);} }''',
"android/content/ActivityNotFoundException.java": '''package android.content;
public class ActivityNotFoundException extends RuntimeException { }''',
"android/content/pm/PackageManager.java": '''package android.content.pm;
public class PackageManager {public final java.util.Map<String,android.content.Intent> tv=new java.util.HashMap<>(), normal=new java.util.HashMap<>();
 public android.content.Intent getLeanbackLaunchIntentForPackage(String n){return tv.get(n);}
 public android.content.Intent getLaunchIntentForPackage(String n){return normal.get(n);} }''',
"android/app/Activity.java": '''package android.app;
public class Activity extends android.content.Context {public final android.content.pm.PackageManager pm=new android.content.pm.PackageManager();
 public android.content.Intent started; public android.content.pm.PackageManager getPackageManager(){return pm;}
 public void startActivity(android.content.Intent i){started=i;} }''',
"android/util/Log.java": '''package android.util;
public class Log {public static int w(String t,String m,Throwable e){return 0;} }''',
"android/widget/Toast.java": '''package android.widget;
public class Toast {public static final int LENGTH_LONG=1; public static Toast makeText(android.content.Context c,String t,int d){return new Toast();} public void show(){} }''',
"org/firefly/tv/ParentalPrefs.java": '''package org.firefly.tv;
class ParentalPrefs {static boolean locked=false; static java.util.Set<String> allowed=new java.util.HashSet<>();
 ParentalPrefs(android.content.Context c){} boolean enabled(){return locked;} java.util.Set<String> allowedApps(){return allowed;} long remaining(){return 100;} }''',
"org/firefly/tv/YouTubeSelectionTest.java": '''package org.firefly.tv;
public class YouTubeSelectionTest {public static void main(String[] args){
 android.app.Activity a=new android.app.Activity(); String official="com.google.android.youtube.tv";
 assert java.util.Arrays.equals(AppLaunch.youtubePackages(a),new String[]{official}); assert AppLaunch.youtubeTitle(a).equals("YouTube");
 a.pm.tv.put("app.smarttube.fdroid",new android.content.Intent("app.smarttube.fdroid"));
 a.pm.normal.put("com.google.android.youtube",new android.content.Intent("com.google.android.youtube"));
 assert AppLaunch.resolve(a.pm,AppLaunch.youtubePackages(a))==null;
 a.pm.tv.put(official,new android.content.Intent(official)); a.pm.normal.put(official,new android.content.Intent("wrong.phone.entry"));
 assert AppLaunch.resolve(a.pm,AppLaunch.youtubePackages(a)).name.equals(official);
 AppLaunch.open(a,AppLaunch.youtubePackages(a)); assert a.started.name.equals(official);
 a.started=null; ParentalPrefs.locked=true; AppLaunch.open(a,AppLaunch.youtubePackages(a)); assert a.started==null;
 ParentalPrefs.allowed.add(official); AppLaunch.open(a,AppLaunch.youtubePackages(a)); assert a.started.name.equals(official);
 a.resources.packages=new String[]{"fixture.custom"}; a.resources.title="Custom";
 assert AppLaunch.youtubePackages(a)[0].equals("fixture.custom"); assert AppLaunch.youtubeTitle(a).equals("Custom");
 a.resources.packages=new String[0]; assert AppLaunch.resolve(a.pm,AppLaunch.youtubePackages(a))==null;
 System.out.println("Official-only default, resource override, leanback priority and parental gating: passed"); } }'''
}
with tempfile.TemporaryDirectory(prefix="youtube-selection-") as temporary:
    work = Path(temporary)
    files = []
    for name, text in stubs.items():
        path = work / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        files.append(path)
    java = source / "src/org/firefly/tv/AppLaunch.java"
    compile = subprocess.run([str(args.jdk / "bin/javac"), "--release", "17", "-d", str(work / "classes"),
                              *map(str, files), str(java)], capture_output=True, text=True)
    execute = None if compile.returncode else subprocess.run([str(args.jdk / "bin/java"), "-ea", "-cp",
        str(work / "classes"), "org.firefly.tv.YouTubeSelectionTest"], capture_output=True, text=True)
    report = {"scope": "Production AppLaunch selection with Android test doubles; no official APK or board used",
              "passed": compile.returncode == 0 and execute is not None and execute.returncode == 0,
              "compile_output": compile.stdout + compile.stderr,
              "run_output": None if execute is None else execute.stdout + execute.stderr,
              "source_sha256": hashlib.sha256(java.read_bytes()).hexdigest()}
if args.report:
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report, indent=2))
raise SystemExit(not report["passed"])
