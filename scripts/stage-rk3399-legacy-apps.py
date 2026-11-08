#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Stage six already verified private APKs without modifying their signed bytes.

Input is the original product's apps directory with its validation/provenance
records, source archives and license notices. No network, APK rewriting or device
installation is performed. Existing signature evidence is bound by exact hashes.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import zipfile

APPS = {
    'com.github.metacubex.clash.meta': 'CMFA',
    'org.xbmc.kodi': 'Kodi',
    'com.xiaodianshi.tv.yst': 'BilibiliTV',
    'com.gitvdemo.video': 'IQiyiTV',
    'com.cibn.tv': 'YoukuTV',
    'dev.aaa1115910.bv': 'BV',
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dynamic_needed(payload):
    """Read the runtime program headers; protected ELF may omit section tables."""
    bits = payload[4]
    assert payload[5] == 1 and bits in (1, 2)
    phoff = struct.unpack_from('<I' if bits == 1 else '<Q', payload, 28 if bits == 1 else 32)[0]
    entsize, count = struct.unpack_from('<HH', payload, 42 if bits == 1 else 54)
    assert entsize >= (32 if bits == 1 else 56)
    loads, dynamic = [], None
    for index in range(count):
        offset = phoff + index * entsize
        assert offset + entsize <= len(payload)
        kind = struct.unpack_from('<I', payload, offset)[0]
        if bits == 1:
            fileoff, vaddr = struct.unpack_from('<II', payload, offset + 4)
            size = struct.unpack_from('<I', payload, offset + 16)[0]
        else:
            fileoff, vaddr = struct.unpack_from('<QQ', payload, offset + 8)
            size = struct.unpack_from('<Q', payload, offset + 32)[0]
        assert fileoff + size <= len(payload)
        if kind == 1:
            loads.append((vaddr, fileoff, size))
        elif kind == 2:
            dynamic = (fileoff, size)
    if dynamic is None:
        return []
    table, string_size, indices = None, None, []
    stride = 8 if bits == 1 else 16
    for offset in range(dynamic[0], dynamic[0] + dynamic[1], stride):
        tag, value = struct.unpack_from('<iI' if bits == 1 else '<qQ', payload, offset)
        if tag == 0:
            break
        if tag == 1:
            indices.append(value)
        elif tag == 5:
            table = value
        elif tag == 10:
            string_size = value
    if not indices:
        return []
    assert table is not None and string_size is not None
    offsets = [off + table - vaddr for vaddr, off, size in loads if vaddr <= table < vaddr + size]
    assert len(offsets) == 1
    assert offsets[0] + string_size <= len(payload)
    result = []
    for index in indices:
        assert index < string_size
        start = offsets[0] + index
        end = payload.index(b'\0', start, offsets[0] + string_size)
        name = payload[start:end].decode('ascii')
        assert re.fullmatch(r'[A-Za-z0-9_+.-]+', name), name
        result.append(name)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--stage', type=Path, required=True)
    parser.add_argument('--aapt2', type=Path, required=True)
    args = parser.parse_args()
    source, stage = args.source.resolve(), args.stage.resolve()
    if stage.exists():
        raise ValueError('Stage already exists; do not overwrite a reviewed stage')
    records = {}
    for name in ('preload-apk-validation.json', 'extra-apk-validation.json'):
        report = json.loads((source / 'records' / name).read_text())
        for entry in report['packages']:
            if entry['package'] in APPS:
                assert entry['passed'] and entry['signature_verified'], entry['package']
                records[entry['package']] = entry
    assert set(records) == set(APPS), 'Missing prior signature/source validation'
    stage.mkdir(parents=True)
    for folder in ('prebuilts', 'jni', 'records', 'sources', 'licenses'):
        (stage / folder).mkdir()
    bp = ['// Private APKs retained byte-for-byte; original signature evidence is hash-bound.', '']
    mk = ['# Generated ARM native sidecars, byte-for-byte from each signed APK.',
          'LOCAL_PATH := $(call my-dir)', '']
    output = {'passed': False, 'board_tested': False,
              'signature_verification': 'Prior apksigner/source evidence reused after full APK SHA256 match',
              'apk_bytes_changed': False, 'smarttube_included': False, 'apps': []}
    modules = []
    library_modules = set()
    for package, alias in APPS.items():
        prior = records[package]
        module = 'Rk3399Legacy' + alias
        filename = package + '_' + str(prior['version_code']) + '.apk'
        apk = source / 'prebuilts' / filename
        assert sha(apk) == prior['sha256'], 'Original APK differs: ' + package
        badging = subprocess.check_output([str(args.aapt2), 'dump', 'badging', str(apk)], text=True)
        declaration = next(x for x in badging.splitlines() if x.startswith('package:'))
        assert "name='" + package + "'" in declaration
        assert "versionCode='" + str(prior['version_code']) + "'" in declaration
        required = re.findall(r"^uses-library:'([^']+)'", badging, re.M)
        optional = re.findall(r"^uses-library-not-required:'([^']+)'", badging, re.M)
        library_modules.update(required)
        shutil.copy2(apk, stage / 'prebuilts' / filename)
        assert sha(stage / 'prebuilts' / filename) == prior['sha256']
        native, dependencies = [], []
        with zipfile.ZipFile(apk) as archive:
            assert archive.testzip() is None
            names = archive.namelist()
            assert len(names) == len(set(names))
            abis = {n.split('/')[1] for n in names if re.fullmatch(r'lib/[^/]+/[^/]+\.so', n)}
            selected = []
            if 'arm64-v8a' in abis:
                selected.append(('arm64-v8a', 'arm64', '64', 2, 183))
            if 'armeabi-v7a' in abis:
                selected.append(('armeabi-v7a', 'arm', '32', 1, 40))
            elif 'armeabi' in abis:
                selected.append(('armeabi', 'arm', '32', 1, 40))
            assert selected, 'No ARM ABI: ' + package
            for abi, isa, bits, elf_class, machine in selected:
                for member in sorted(n for n in names if re.fullmatch('lib/' + re.escape(abi) + r'/[^/]+\.so', n)):
                    name = member.rsplit('/', 1)[-1]
                    payload = archive.read(member)
                    directory = stage / 'jni' / module / isa
                    directory.mkdir(parents=True, exist_ok=True)
                    destination = directory / name
                    destination.write_bytes(payload)
                    digest = hashlib.sha256(payload).hexdigest()
                    assert sha(destination) == digest
                    is_elf = payload.startswith(b'\x7fELF')
                    needed = []
                    dynamic_warning = ''
                    if is_elf:
                        assert payload[4:7] == bytes([elf_class, 1, 1]), member
                        assert struct.unpack_from('<H', payload, 18)[0] == machine, member
                        needed = dynamic_needed(payload)
                        dynamic = subprocess.run(['readelf', '-d', '--wide', str(destination)],
                                                 capture_output=True, text=True)
                        dynamic_warning = dynamic.stderr.strip()
                        if dynamic.returncode == 0 and not dynamic_warning:
                            assert needed == re.findall(r'\(NEEDED\).*\[([^]]+)\]', dynamic.stdout)
                    else:
                        # The inherited official Youku package has SecurityGuard
                        # ZIP plugins named *.so; preserve plugin data unchanged.
                        assert package == 'com.cibn.tv' and payload.startswith(b'PK'), member
                    native_module = module + 'JNI' + bits + '_' + re.sub(r'[^A-Za-z0-9_]', '_', name)
                    assert native_module not in dependencies, 'Sanitized native module collision'
                    dependencies.append(native_module)
                    mk += ['include $(CLEAR_VARS)', 'LOCAL_MODULE := ' + native_module,
                           'LOCAL_MODULE_CLASS := SHARED_LIBRARIES', 'LOCAL_MODULE_SUFFIX := .so',
                           'LOCAL_MODULE_STEM := ' + name[:-3],
                           'LOCAL_SRC_FILES := jni/' + module + '/' + isa + '/' + name,
                           'LOCAL_PRODUCT_MODULE := true', 'LOCAL_MULTILIB := ' + bits,
                           'LOCAL_MODULE_PATH := $(TARGET_OUT_PRODUCT)/app/' + module + '/lib/' + isa,
                           'LOCAL_CHECK_ELF_FILES := false', 'LOCAL_STRIP_MODULE := false',
                           'LOCAL_SYSTEM_SHARED_LIBRARIES :=', 'include $(BUILD_PREBUILT)', '']
                    native.append({'member': member, 'isa': isa, 'bytes': len(payload),
                                   'sha256': digest, 'elf': is_elf, 'needed': needed,
                                   'readelf_section_warning': dynamic_warning,
                                   'needed_from_runtime_program_headers': is_elf,
                                   'stage_path': destination.relative_to(stage).as_posix()})
        modules.append(module)
        bp += ['android_app_import {', '    name: "' + module + '",',
               '    apk: "prebuilts/' + filename + '",', '    product_specific: true,',
               '    presigned: true,', '    preprocessed: true,',
               '    // Existing legacy exception: compressed JNI is installed as exact sidecars.',
               '    // This is not a claim that the preprocessed APK checker passes.',
               '    skip_preprocessed_apk_checks: true,', '    dex_preopt: { enabled: false },']
        for key, value in [('uses_libs', required), ('optional_uses_libs', optional)]:
            if value:
                bp.append('    ' + key + ': ' + json.dumps(value) + ',')
        bp += ['    required: ['] + ['        "' + name + '",' for name in dependencies] + ['    ],', '}', '']
        entry = dict(prior)
        entry.pop('jni', None)
        entry.update(module=module, native_sidecars=native, available_abis=sorted(abis),
                     selected_abis=[x[0] for x in selected], required_uses_libraries=required,
                     optional_uses_libraries=optional)
        output['apps'].append(entry)
        evidence = prior.get('evidence', package)
        for suffix in ('-signature.txt', '-badging.txt'):
            path = source / 'records' / (evidence + suffix)
            assert path.exists(), path
            shutil.copy2(path, stage / 'records' / path.name)
        page = prior.get('page_file')
        if page:
            shutil.copy2(source / 'records' / page, stage / 'records' / page)
        if prior.get('source_archive'):
            archive = source / 'sources' / prior['source_archive']
            assert sha(archive) == prior['source_archive_sha256']
            shutil.copy2(archive, stage / 'sources' / archive.name)
    source_records = json.loads((source / 'records/fdroid-corresponding-sources.json').read_text())
    source_records['sources'] = [x for x in source_records['sources'] if x['package'] in APPS]
    for entry in source_records['sources']:
        archive = source / 'sources' / entry['file']
        assert sha(archive) == entry['sha256']
        shutil.copy2(archive, stage / 'sources' / archive.name)
    (stage / 'records/fdroid-corresponding-sources.json').write_text(json.dumps(source_records, indent=2) + '\n')
    for path in (source / 'licenses').iterdir():
        if path.is_file() and 'smarttube' not in path.name.lower():
            shutil.copy2(path, stage / 'licenses' / path.name)
    # Carry the original download provenance, including the two-page Youku chain.
    extra_page = source / 'records/pd-youku-official-1080.html'
    if extra_page.exists():
        shutil.copy2(extra_page, stage / 'records' / extra_page.name)
    (stage / 'Android.bp').write_text('\n'.join(bp))
    (stage / 'Android.mk').write_text('\n'.join(mk))
    (stage / 'preloads.mk').write_text('# Private verified applications; official YouTube is selected separately.\nPRODUCT_PACKAGES += \\\n' + ' \\\n'.join('    ' + x for x in modules + sorted(library_modules)) + '\n')
    (stage / 'KNOWN-ISSUES.md').write_text(
        '# Existing application limitations\n\n'
        'These APKs and sidecars retain their original bytes and signatures. '
        'RK3399 runtime installation, login, playback and DRM remain untested.\n\n'
        'Kodi 21.3 ARM32 optional Vorbis CD encoder imports eleven unresolved oggpack_* symbols; '
        'the prior audit found the main playback library and other 83 native libraries passed. '
        'This is not a H264/HEVC playback-library failure.\n\n'
        'BV retains upstream region restrictions. Youku retains three SecurityGuard ZIP plugins '
        'named .so, plus its armeabi and target SDK 25 requirements.\n\n'
        'CMFA and BV now include both ARM64 and ARM32 libraries taken from the original universal APK. '
        'ELF architecture and DT_NEEDED were inspected; full symbol resolution against the new '
        'ARM64 product output must be checked after that output is built.\n\n'
        'Legacy preprocessed APK checks remain explicitly exempt because matching external JNI sidecars '
        'are installed. The checker is not claimed to pass. No such exemption is used for official YouTube.\n')
    output['passed'] = True
    output['full_rk3399_symbol_closure_verified'] = False
    output['file_hashes'] = {p.relative_to(stage).as_posix(): sha(p) for p in sorted(stage.rglob('*')) if p.is_file()}
    output['total_bytes_before_manifest'] = sum(p.stat().st_size for p in stage.rglob('*') if p.is_file())
    output['installed_apk_and_jni_bytes'] = sum(p.stat().st_size for d in ['prebuilts', 'jni'] for p in (stage / d).rglob('*') if p.is_file())
    (stage / 'manifest.json').write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'passed': True, 'stage': str(stage), 'apps': len(modules),
                      'modules': modules, 'installed_apk_and_jni_bytes': output['installed_apk_and_jni_bytes'],
                      'manifest_sha256': sha(stage / 'manifest.json')}))


if __name__ == '__main__':
    main()
