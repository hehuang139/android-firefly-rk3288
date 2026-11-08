#!/usr/bin/env python3
"""Build the pinned RK3399 H.264/VP9 Request backend with the AOSP ARM64 toolchain."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

REVISION = 'b57fbbe50c9b2656fad86a1a7eeabfd2b2a50935'
URL = 'https://github.com/Kwiboo/FFmpeg.git'
SNAPSHOT = 'FIREFLY-SNAPSHOT.json'


def run(args, cwd=None):
    subprocess.run([str(a) for a in args], cwd=cwd, check=True)


def verify_snapshot(source, patch):
    metadata = json.loads((source / SNAPSHOT).read_text())
    if metadata.get('backend_revision') != REVISION:
        raise SystemExit('Unexpected FFmpeg source snapshot revision')
    if metadata.get('patch_sha256') != hashlib.sha256(patch.read_bytes()).hexdigest():
        raise SystemExit('FFmpeg source snapshot uses a different Firefly patch')
    expected = metadata['files']
    actual = set()
    for file in source.rglob('*'):
        if file.is_symlink():
            raise SystemExit(f'Symlink in FFmpeg source snapshot: {file}')
        if file.is_file():
            name = file.relative_to(source).as_posix()
            if name == SNAPSHOT:
                continue
            actual.add(name)
            if name not in expected or hashlib.sha256(file.read_bytes()).hexdigest() != expected[name]:
                raise SystemExit(f'FFmpeg source snapshot checksum mismatch: {name}')
    if actual != set(expected):
        raise SystemExit('FFmpeg source snapshot is incomplete')


def main():
    media = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--aosp', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True, help='Isolated AOSP OUT_DIR containing ARM64 CRT objects and NDK sysroot')
    parser.add_argument('--source', type=Path,
                        help='Clean pinned Git checkout or verified extracted Firefly snapshot')
    parser.add_argument('--jobs', type=int, default=min(os.cpu_count() or 4, 8))
    args = parser.parse_args()
    aosp, work = args.aosp.resolve(), args.work.resolve()
    out = args.out.resolve()
    work.mkdir(parents=True, exist_ok=True)
    src, build, install, crt = [work / n for n in ('source', 'build', 'install', 'crt')]
    patch = media / 'patches/0001-android-ueventd-v4l2-request.patch'
    if not src.exists():
        if args.source and (args.source / SNAPSHOT).is_file():
            verify_snapshot(args.source.resolve(), patch)
            shutil.copytree(args.source.resolve(), src)
        elif args.source:
            run(['git', 'clone', '--no-hardlinks', args.source.resolve(), src])
        else:
            run(['git', 'init', src])
            run(['git', 'remote', 'add', 'origin', URL], src)
            run(['git', 'fetch', '--depth=1', 'origin', REVISION], src)
        if not (src / SNAPSHOT).is_file():
            run(['git', 'checkout', '--detach', REVISION], src)
            run(['git', 'apply', patch], src)
    if (src / SNAPSHOT).is_file():
        verify_snapshot(src, patch)
    else:
        revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=src, text=True).strip()
        if revision != REVISION:
            raise SystemExit(f'Unexpected FFmpeg revision {revision}')
        actual_diff = subprocess.check_output(
            ['git', '-c', 'core.abbrev=7', '-c', 'diff.context=3', 'diff',
             '--no-ext-diff', '--no-color', '--binary', 'HEAD'], cwd=src)
        if actual_diff != patch.read_bytes():
            raise SystemExit('FFmpeg worktree differs from the exact pinned Firefly patch')
    clang_candidates = sorted((aosp / 'prebuilts/clang/host/linux-x86').glob('clang-r*/bin/clang'))
    if not clang_candidates:
        raise SystemExit('AOSP clang compiler missing')
    compiler = clang_candidates[-1].parent
    sysroot = out / 'soong/ndk/sysroot'
    if not (sysroot / 'usr/include/stdlib.h').exists():
        raise SystemExit('Build the AOSP NDK sysroot first: m ndk_sysroot')
    crt.mkdir(exist_ok=True)
    for name in ('crtbegin_so', 'crtbegin_dynamic', 'crtend_so', 'crtend_android'):
        candidates = list((out / f'soong/.intermediates/bionic/libc/{name}').glob(
            f'android_vendor_arm64_armv8-a_*/{name}.o'))
        if not candidates:
            raise SystemExit(f'Build AOSP ARM64 {name} first (m {name})')
        shutil.copyfile(candidates[0], crt / f'{name}.o')
    target = '--target=aarch64-linux-android37'
    cflags = f'{target} -I{sysroot}/usr/include/aarch64-linux-android -I{aosp}/external/libdrm/include/drm'
    ldflags = f'{target} -B{crt} -L{sysroot}/usr/lib/aarch64-linux-android/37 -fuse-ld=lld'
    options = [f'--prefix={install}', '--target-os=android', '--arch=aarch64', '--cpu=cortex-a72',
               '--enable-cross-compile', f'--sysroot={sysroot}', f'--extra-cflags={cflags}',
               f'--extra-cxxflags={cflags}', f'--extra-ldflags={ldflags}', '--disable-autodetect',
               '--disable-everything', '--disable-programs', '--disable-doc', '--disable-network',
               '--disable-avdevice', '--disable-avfilter', '--disable-avformat', '--enable-swresample',
               '--enable-avcodec', '--enable-avutil', '--enable-swscale', '--enable-decoder=h264,vp9,ac3,mp2',
               '--enable-parser=h264,vp9,ac3,mpegaudio', '--enable-hwaccel=h264_v4l2request,vp9_v4l2request', '--enable-v4l2-request',
               '--enable-shared', '--disable-static', '--enable-pic']
    for flag, exe in [('cc', 'clang'), ('cxx', 'clang++'), ('ar', 'llvm-ar'), ('nm', 'llvm-nm'),
                      ('ranlib', 'llvm-ranlib'), ('strip', 'llvm-strip')]:
        options.append(f'--{flag}={compiler / exe}')
    build.mkdir(exist_ok=True)
    run([src / 'configure', *options], build)
    run(['make', f'-j{args.jobs}'], build)
    run(['make', 'install'], build)
    (media / 'prebuilts/arm64').mkdir(parents=True, exist_ok=True)
    for lib in ('avcodec', 'avutil', 'swscale', 'swresample'):
        shutil.copyfile(install / f'lib/lib{lib}.so', media / f'prebuilts/arm64/lib{lib}.so')
    shutil.copytree(install / 'include', media / 'include', dirs_exist_ok=True)
    manifest_path = media / 'source-manifest.json'
    manifest = json.loads(manifest_path.read_text())
    manifest['backend_revision'] = REVISION
    manifest['bitstream_zero_padding'] = 80
    manifest['target_arch'] = 'aarch64'
    manifest['hardware_decoders'] = ['h264', 'vp9']
    manifest['hardware_validation'] = 'pending original Firefly-RK3399 board'
    manifest['libraries'] = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted((media / 'prebuilts/arm64').glob('*.so'))
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
    print(f'Built {REVISION}; Android ARM64 libraries and headers installed in {media}')


if __name__ == '__main__':
    main()
