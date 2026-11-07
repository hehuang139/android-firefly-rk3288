#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run production budget/PIN/puzzle logic on a JVM with a preferences test double.

This does not emulate Android task management, playback or background services.
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
public final class Context {
 public static final int MODE_PRIVATE=0;
 private final SharedPreferences prefs = new SharedPreferences();
 public Context createDeviceProtectedStorageContext() {return this;}
 public SharedPreferences getSharedPreferences(String name,int mode) {return prefs;}
}''',
    'android/util/Base64.java': '''package android.util;
public final class Base64 {
 public static final int NO_WRAP=2;
 public static byte[] decode(String s,int flags) {return java.util.Base64.getDecoder().decode(s);}
 public static String encodeToString(byte[] v,int flags) {
   return java.util.Base64.getEncoder().encodeToString(v);}
}'''
}
inputs = [sources / (name + '.java') for name in ['WatchBudget', 'ParentalPrefs', 'PuzzleRound']]
inputs.append(port / 'tests/ParentalHostTest.java')
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
    report = {'scope': 'JVM production budget/PIN/puzzle logic; SharedPreferences test double',
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
