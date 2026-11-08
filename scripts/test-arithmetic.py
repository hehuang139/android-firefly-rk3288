#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exercise production arithmetic and local progress on a JVM, without device access."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

parser = argparse.ArgumentParser()
parser.add_argument('--jdk', type=Path, required=True)
parser.add_argument('--report', type=Path, required=True)
args = parser.parse_args()
port = Path(__file__).resolve().parents[1]
source = port / 'device/firefly/rk3288/tv/src/org/firefly/tv'
stubs = {
    'android/content/SharedPreferences.java': '''package android.content;
import java.util.*;
public final class SharedPreferences {
 private final Map<String,Object> values = new HashMap<>();
 public boolean failNextCommit;
 public int getInt(String key,int def) {return (Integer)values.getOrDefault(key,def);}
 public long getLong(String key,long def) {return (Long)values.getOrDefault(key,def);}
 public String getString(String key,String def) {return (String)values.getOrDefault(key,def);}
 @SuppressWarnings("unchecked") public Set<String> getStringSet(String key,Set<String> def) {
  return (Set<String>)values.getOrDefault(key,def);}
 public Editor edit() {return new Editor();}
 public final class Editor {
  private final Map<String,Object> pending = new HashMap<>();
  public Editor putInt(String k,int v) {pending.put(k,v);return this;}
  public Editor putLong(String k,long v) {pending.put(k,v);return this;}
  public Editor putString(String k,String v) {pending.put(k,v);return this;}
  public Editor putStringSet(String k,Set<String> v) {pending.put(k,new HashSet<>(v));return this;}
  public boolean commit() {
   if(failNextCommit) {failNextCommit=false;return false;}
   values.putAll(pending);return true;
  }
 }
}''',
    'android/content/Context.java': '''package android.content;
import java.util.*;
public final class Context {
 public static final int MODE_PRIVATE=0;
 private final Map<String,SharedPreferences> stores = new HashMap<>();
 public Context createDeviceProtectedStorageContext() {return this;}
 public synchronized SharedPreferences getSharedPreferences(String name,int mode) {
  return stores.computeIfAbsent(name,n->new SharedPreferences());
 }
}''',
}
inputs = [source / 'ArithmeticRound.java', source / 'KidsProgress.java', source / 'PuzzleInputGate.java',
          port / 'tests/ArithmeticHostTest.java']
suffix = '.exe' if os.name == 'nt' else ''
with tempfile.TemporaryDirectory() as directory:
    work = Path(directory)
    generated = []
    for relative, text in stubs.items():
        path = work / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
        generated.append(path)
    compile_result = subprocess.run([str(args.jdk / ('bin/javac' + suffix)), '--release', '17',
        '-encoding', 'UTF-8', '-d', str(work / 'classes'), *map(str, inputs + generated)],
        capture_output=True, text=True)
    run_result = None
    if compile_result.returncode == 0:
        run_result = subprocess.run([str(args.jdk / ('bin/java' + suffix)), '-ea', '-cp',
            str(work / 'classes'), 'org.firefly.tv.ArithmeticHostTest'], capture_output=True, text=True)
    report = {'scope': 'Production arithmetic question/session logic, picture-challenge input guard, and local progress, using a SharedPreferences test double. Android layout, lifecycle callbacks and physical remote interaction are not emulated.',
        'compile_exit': compile_result.returncode, 'compile_output': compile_result.stdout + compile_result.stderr,
        'run_exit': None if run_result is None else run_result.returncode,
        'run_output': '' if run_result is None else run_result.stdout + run_result.stderr,
        'passed': run_result is not None and run_result.returncode == 0,
        'inputs': {str(path.relative_to(port)): hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs}}
args.report.parent.mkdir(parents=True, exist_ok=True)
args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(report, ensure_ascii=True))
raise SystemExit(not report['passed'])
