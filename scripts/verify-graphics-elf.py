#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Check the final RK3288 graphics ELF files against their linker namespaces.

Uses installed product files and freshly extracted installed APEX packages. No
Soong intermediates or link-time stub libraries participate in resolution.
"""
import argparse
from collections import deque
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import struct
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET


CHECKER_SHA256 = "3a56973b719aa01dec2c8b5f9a690535ac8f6ae9e9cd2d7364ea72f492a26bc9"
CLANG_VERSION = "clang-r584948b"
ROOTS = (
    ("egl", "system", "sphal", "/vendor/lib/egl/libEGL_mesa.so", ("eglGetProcAddress", "eglInitialize")),
    ("gles1", "system", "sphal", "/vendor/lib/egl/libGLESv1_CM_mesa.so", ("glGetString", "glClear")),
    ("gles2", "system", "sphal", "/vendor/lib/egl/libGLESv2_mesa.so", ("glGetString", "glClear")),
    ("gallium", "system", "sphal", "/vendor/lib/libgallium_dri.so", ()),
    ("gralloc", "system", "sphal", "/vendor/lib/libminigbm_gralloc.so", ()),
    ("mapper", "system", "sphal", "/vendor/lib/hw/mapper.minigbm.so", ("AIMapper_loadIMapper", "ANDROID_HAL_MAPPER_VERSION")),
    ("allocator", "vendor", "default", "/vendor/bin/hw/android.hardware.graphics.allocator-service.minigbm", ()),
    ("composer", "vendor", "default", "/vendor/bin/hw/android.hardware.composer.hwc3-service.drm", ()),
)
PARTITIONS = ("system", "system_ext", "product", "vendor", "odm")


class VerificationError(Exception):
    def __init__(self, message, report=None):
        super().__init__(message)
        self.report = report


def sha256(path):
    before = identity(path)
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            result.update(block)
    require(identity(path) == before, "Input changed while hashing: " + str(path))
    return result.hexdigest()


def identity(path):
    info = path.stat()
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def run(args):
    result = subprocess.run([str(arg) for arg in args], capture_output=True, text=True, timeout=900)
    if result.returncode:
        raise VerificationError("Command failed: " + str(args[0]) + "\n" + (result.stdout + result.stderr)[-5000:])
    return result.stdout


def require(condition, message):
    if not condition:
        raise VerificationError(message)


def requirements(aosp, product):
    host = aosp / "out/host/linux-x86/bin"
    return {
        "product_out": str(product),
        "graphics_roots": [item[3] for item in ROOTS],
        "installed_runtime_linker": "/system/bin/linker (including its installed symlink target)",
        "installed_partition_inputs": ["system", "system_ext", "product", "vendor"],
        "namespace_inputs": ["system/etc/linker.config.pb", "system/etc/llndk.libraries.txt", "system/etc/sanitizer.libraries.txt", "partition etc/linker.config.pb and public.libraries.txt when installed"],
        "apex_inputs": "All installed *.apex/*.capex in system, system_ext, product, vendor and odm /apex; each is freshly extracted and hashed.",
        "tools": {
            "llvm_readobj": str(aosp / "prebuilts/clang/host/linux-x86" / CLANG_VERSION / "bin/llvm-readobj"),
            "aosp_elf_parser": str(aosp / "build/make/tools/check_elf_file.py"),
            "linkerconfig": str(host / "linkerconfig"),
            "deapexer": str(host / "deapexer"),
            "debugfs": str(host / "debugfs_static"),
            "fsckerofs": str(host / "fsck.erofs"),
        },
    }


def check_tools(aosp, product):
    required = requirements(aosp, product)
    tools = {key: Path(value) for key, value in required["tools"].items()}
    missing = [str(path) for path in tools.values() if not path.is_file()]
    require(not missing, "Missing verification tools/files: " + ", ".join(missing))
    require(sha256(tools["aosp_elf_parser"]) == CHECKER_SHA256,
            "ELF parser differs from android-17.0.0_r1 check_elf_file.py")
    for key in ("llvm_readobj", "linkerconfig", "deapexer", "debugfs", "fsckerofs"):
        require(os.access(tools[key], os.X_OK), "Tool is not executable: " + str(tools[key]))
    run([tools["llvm_readobj"], "--version"])
    run([tools["linkerconfig"], "--help"])
    run([tools["deapexer"], "--help"])
    return tools


def load_parser(path):
    spec = importlib.util.spec_from_file_location("firefly_aosp_elf_parser", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.ELFParser


def build_runtime_root(product, scratch, tools, report):
    """Give host linkerconfig real partition directories, never host realpaths."""
    root = scratch / "runtime-root"
    root.mkdir()
    for partition in PARTITIONS:
        dest = root / partition
        dest.mkdir()
        source = product / partition
        if source.is_dir():
            for basename in ("etc", "bin", "lib"):
                if (source / basename).exists():
                    (dest / basename).symlink_to(source / basename, target_is_directory=True)
    apex_root = root / "apex"
    apex_root.mkdir()
    xml = ET.Element("apex-info-list")
    archives = []
    for partition in PARTITIONS:
        directory = product / partition / "apex"
        if directory.is_dir():
            flattened = [path for path in directory.iterdir() if path.is_dir()]
            require(not flattened, "Expected packaged APEX for this product; found flattened APEX: " + str(flattened))
            archives.extend((partition, path) for path in sorted(directory.iterdir()) if path.suffix in (".apex", ".capex"))
    report["apex_packages"] = []
    for partition, archive in archives:
        archive_sha = sha256(archive)
        manifest = json.loads(run([tools["deapexer"], "info", archive]))
        name = manifest.get("name", "")
        require(re.fullmatch(r"[A-Za-z0-9_.-]+", name) is not None, "Invalid APEX name: " + name)
        require(not manifest.get("provideSharedApexLibs", False), "Shared-library APEX layout needs explicit support: " + name)
        dest = apex_root / name
        require(not dest.exists(), "Duplicate installed APEX module: " + name)
        print("Extracting installed APEX " + name, file=sys.stderr, flush=True)
        run([tools["deapexer"], "--debugfs_path", tools["debugfs"], "--fsckerofs_path", tools["fsckerofs"], "extract", archive, dest])
        require((dest / "apex_manifest.pb").is_file(), "Extracted APEX has no manifest: " + name)
        require(sha256(archive) == archive_sha, "Installed APEX changed during extraction: " + str(archive))
        report["apex_packages"].append({"name": name, "archive": str(archive.relative_to(product)), "sha256": archive_sha, "manifest_sha256": sha256(dest / "apex_manifest.pb")})
        ET.SubElement(xml, "apex-info", moduleName=name, partition=partition.upper(),
                      modulePath="/" + str(archive.relative_to(product)), isActive="true",
                      isFactory="true", versionCode=str(manifest.get("version", 0)))
    ET.ElementTree(xml).write(apex_root / "apex-info-list.xml", encoding="utf-8", xml_declaration=True)
    return root, apex_root


def properties(product):
    result = {}
    for partition in PARTITIONS:
        for basename in ("build.prop", "etc/build.prop"):
            path = product / partition / basename
            if path.is_file():
                for line in path.read_text().splitlines():
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        result[key] = value
    return result


def generate_namespaces(product, root, scratch, tools, report):
    props = properties(product)
    require(props.get("ro.treble.enabled") == "true", "Expected the RK3288 Treble product property")
    (scratch / "linkerconfig").mkdir()
    # Match init's GenerateLinkerConfiguration: global namespace generation
    # does not use --strict. Platform requireLibs includes both release/debug
    # ART providers even when only the release APEX is installed. Strict is
    # used by init only for a targeted --apex update. Actual ELF dependencies
    # and symbols below remain mandatory in the generated runtime namespaces.
    args = [tools["linkerconfig"], "--root", root, "--target", scratch / "linkerconfig", "--treblelize"]
    for key, option in (("ro.vndk.version", "--vndk"), ("ro.product.vndk.version", "--product_vndk")):
        if props.get(key):
            args.extend([option, props[key]])
    run(args)
    path = scratch / "linkerconfig/ld.config.txt"
    require(path.is_file(), "Host linkerconfig did not generate ld.config.txt")
    text = path.read_text()
    require(str(product) not in text and str(scratch) not in text, "Generated namespaces contain host paths")
    report["linker_config"] = {"sha256": sha256(path), "generator_sha256": sha256(tools["linkerconfig"]),
                               "generation_mode": "init global runtime configuration; no --strict or --apex",
                               "properties": {key: props.get(key) for key in ("ro.treble.enabled", "ro.vndk.version", "ro.product.vndk.version")}}
    return parse_namespaces(text)


def parse_namespaces(text):
    sections, current = {}, None
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if line.startswith("[") and line.endswith("]"):
            current = sections.setdefault(line[1:-1], {})
        elif current is not None and line:
            match = re.fullmatch(r"([^\s=]+)\s*(\+?=)\s*(.*)", line)
            require(match is not None, "Cannot parse linker configuration: " + line)
            key, operation, value = match.groups()
            if operation == "=":
                current[key] = value
            else:
                require(key in current, "Namespace += without prior value: " + key)
                current[key] += ("," if key.endswith(".links") or key == "additional.namespaces" else ":") + value
    require("system" in sections and "vendor" in sections, "Generated configuration lacks system/vendor sections")
    require("namespace.sphal.search.paths" in sections["system"], "System section lacks SP-HAL namespace")
    return sections


class ProductFiles:
    """Resolve Android symlinks in virtual paths rather than on the host."""
    def __init__(self, product, apex_root):
        self.product, self.apex_root = product, apex_root

    def physical(self, virtual):
        parts = PurePosixPath(virtual).parts
        require(len(parts) >= 2 and parts[0] == "/", "Expected absolute Android path: " + virtual)
        if parts[1] == "apex":
            return self.apex_root.joinpath(*parts[2:])
        require(parts[1] in PARTITIONS, "Dependency escapes installed partitions: " + virtual)
        return self.product.joinpath(*parts[1:])

    def resolve(self, virtual):
        queue, current, followed = deque(PurePosixPath(virtual).parts[1:]), [], 0
        while queue:
            part = queue.popleft()
            if part in ("", "."):
                continue
            if part == "..":
                require(bool(current), "Symlink escapes Android root: " + virtual)
                current.pop()
                continue
            candidate = "/" + "/".join(current + [part])
            path = self.physical(candidate)
            try:
                mode = path.lstat().st_mode
            except FileNotFoundError:
                return None
            if stat.S_ISLNK(mode):
                target = os.readlink(path)
                if target.startswith("/"):
                    current = []
                queue.extendleft(reversed(PurePosixPath(target).parts[1:] if target.startswith("/") else PurePosixPath(target).parts))
                followed += 1
                require(followed <= 40, "Symlink loop: " + virtual)
            else:
                current.append(part)
        canonical = "/" + "/".join(current)
        path = self.physical(canonical)
        return (canonical, path) if path.is_file() else None


class GraphicsChecker:
    def __init__(self, files, sections, parser, readobj):
        self.files, self.sections, self.parser, self.readobj = files, sections, parser, readobj
        self.cache = {}
        self.linker = self.elf("/system/bin/linker")
        require(self.linker["elf"].dt_soname == "ld-android.so", "Runtime linker must provide ld-android.so")

    def elf(self, virtual):
        found = self.files.resolve(virtual)
        require(found is not None, "Missing installed ELF: " + virtual)
        canonical, path = found
        if canonical not in self.cache:
            before = identity(path)
            with path.open("rb") as stream:
                header = stream.read(52)
            require(len(header) == 52 and header[:7] == b"\x7fELF\x01\x01\x01", "Expected little-endian ELF32: " + canonical)
            values = struct.unpack("<16sHHIIIIIHHHHHH", header)
            require(values[1] in (2, 3) and values[2] == 40 and values[3] == 1 and values[7] >> 24 == 5, "Expected ARM EABI5 executable/shared object: " + canonical)
            require(not values[7] & 0x400, "Hard-float ARM ABI is incompatible with Android: " + canonical)
            phoff, phsize, phcount = values[5], values[9], values[10]
            require(values[8] == 52 and phsize == 32 and phcount > 0 and phoff + phsize * phcount <= path.stat().st_size,
                    "Invalid ELF program-header range: " + canonical)
            with path.open("rb") as stream:
                for index in range(phcount):
                    stream.seek(phoff + index * phsize)
                    kind, offset, _, _, size, memory, _, _ = struct.unpack("<8I", stream.read(phsize))
                    if kind in (1, 3):
                        require(offset + size <= path.stat().st_size and (kind != 1 or size <= memory), "Invalid ELF load/interpreter segment: " + canonical)
                    if kind == 3:
                        stream.seek(offset)
                        require(stream.read(size).rstrip(b"\0") == b"/system/bin/linker", "Wrong Android ARM32 interpreter: " + canonical)
            text = run([self.readobj, "--program-headers", "--dynamic-table", "--dyn-symbols", "--version-info", path])
            require("DynamicSection [" in text and "DynamicSymbols [" in text, "Missing dynamic ELF tables: " + canonical)
            require(not re.search(r"^\s+0x[0-9a-fA-F]+\s+(?:TEXTREL\b|FLAGS\s+.*\bTEXTREL\b)", text, re.M), "Text relocations in " + canonical)
            parsed = self.parser._parse_llvm_readobj(str(path), self.parser._read_elf_header(str(path)), text.splitlines())
            definitions = text.partition("VersionDefinitions [\n")[2].partition("\nVersionRequirements [")[0]
            require("VersionDefinitions [\n" in text and "VersionRequirements [" in text,
                    "Missing ELF version metadata: " + canonical)
            version_definitions = set(re.findall(r"^    Name: (.+)$", definitions, re.M))
            runpaths = re.findall(r"^\s+0x[0-9a-fA-F]+\s+RUNPATH\s+.*\[(.*)\]$", text, re.M)
            self.cache[canonical] = {"path": canonical, "physical": path, "elf": parsed, "version_definitions": version_definitions,
                                     "runpath": runpaths[0].split(":") if runpaths else [], "sha256": sha256(path), "identity": before}
            require(identity(path) == before, "Installed ELF changed during inspection: " + canonical)
        return self.cache[canonical]

    def value(self, section, ns, key):
        return self.sections[section].get("namespace." + ns + "." + key, "")

    def paths(self, section, ns, key):
        result = []
        for path in self.value(section, ns, key).split(":"):
            if path:
                path = path.replace("${LIB}", "lib")
                require("$" not in path and path.startswith("/"), "Unsupported namespace path: " + path)
                result.append(path.rstrip("/"))
        return result

    def allowed(self, section, ns, canonical):
        if self.value(section, ns, "isolated") != "true":
            return True
        if str(PurePosixPath(canonical).parent) in self.paths(section, ns, "search.paths"):
            return True
        return any(canonical == path or canonical.startswith(path + "/") for path in self.paths(section, ns, "permitted.paths"))

    def link_allows(self, section, ns, target, soname):
        prefix = "link." + target + "."
        return self.value(section, ns, prefix + "allow_all_shared_libs") == "true" or soname in self.value(section, ns, prefix + "shared_libs").split(":")

    def links(self, section, ns):
        return [name for name in self.value(section, ns, "links").split(",") if name]

    @staticmethod
    def provides_symbol(provider, symbol, version):
        exported = provider["elf"].exported.get(symbol, set())
        if not version:
            return bool(exported)
        # Bionic find_verdef_version_index returns VER_NDX_GLOBAL when this
        # DSO has no matching version definition. check_symbol_version then
        # accepts only its unversioned global definition. A DSO that defines
        # the requested version must provide the symbol at that exact version.
        if version in provider["version_definitions"]:
            return version in exported
        return "" in exported

    def resolve(self, section, ns, needed, parent):
        require("/" not in needed, "Unexpected path in DT_NEEDED: " + needed + " required by " + parent["path"])
        if needed == "ld-android.so":
            return ns, self.linker
        def local(target, runpath=False):
            directories = self.paths(section, target, "search.paths")
            if runpath:
                origin = str(PurePosixPath(parent["path"]).parent)
                extra = [path.replace("${ORIGIN}", origin).replace("$ORIGIN", origin) for path in parent["runpath"] if path]
                require(all(path.startswith("/") and "$" not in path for path in extra), "Unsupported DT_RUNPATH in " + parent["path"])
                directories = extra + directories
            allowed_libs = self.value(section, target, "allowed_libs").split(":")
            if allowed_libs != [""] and needed not in allowed_libs:
                return None
            for directory in directories:
                candidate = directory + "/" + needed
                found = self.files.resolve(candidate)
                if found is not None and self.allowed(section, target, found[0]):
                    item = self.elf(candidate)
                    return target, item
            return None
        found = local(ns, True)
        if found:
            return found
        for target in self.links(section, ns):
            if self.link_allows(section, ns, target, needed):
                found = local(target)
                if found:
                    return found
        raise VerificationError("Unresolved DT_NEEDED " + needed + " from " + parent["path"] + " in " + section + "/" + ns)

    def check_root(self, name, section, namespace, virtual, required_exports):
        root = self.elf(virtual)
        require(self.allowed(section, namespace, root["path"]), "Root is outside namespace: " + virtual)
        missing_exports = sorted(set(required_exports) - root["elf"].exported.keys())
        require(not missing_exports, "Missing graphics entry points in " + virtual + ": " + ", ".join(missing_exports))
        first = (namespace, root["path"])
        nodes, edges, parents, queue, groups = {first: root}, {}, {}, deque([first]), [first]
        while queue:
            key = queue.popleft()
            ns, _ = key
            item = nodes[key]
            edges[key] = []
            for needed in item["elf"].dt_needed:
                child_ns, child = self.resolve(section, ns, needed, item)
                child_key = (child_ns, child["path"])
                edges[key].append(child_key)
                parents.setdefault(child_key, set()).add(key)
                if child_key not in nodes:
                    nodes[child_key] = child
                    queue.append(child_key)
                if ns != child_ns and child_key not in groups:
                    groups.append(child_key)
        checked, imports_checked, version_fallbacks = set(), 0, []
        for group in groups:
            ns = group[0]
            scope, visited, pending = [], set(), deque([group])
            while pending:
                key = pending.popleft()
                if key in visited:
                    continue
                visited.add(key)
                item = nodes[key]
                # Mirror linker_namespaces.cpp is_accessible(soinfo*): symbols
                # are visible from members and their immediate dependencies.
                # A name in a namespace link allows loading, but does not make
                # every transitive library with that name a symbol provider.
                accessible = key[0] == ns or any(parent[0] == ns for parent in parents.get(key, ()))
                if accessible:
                    scope.append(key)
                    pending.extend(edges[key])
            providers = [self.linker] + [nodes[key] for key in scope]
            for key in scope:
                if key[0] != ns or key in checked:
                    continue
                item, missing = nodes[key], []
                for symbol, versions in item["elf"].imported.items():
                    for version in versions:
                        imports_checked += 1
                        provider = next((candidate for candidate in providers
                                         if self.provides_symbol(candidate, symbol, version)), None)
                        if provider is None:
                            missing.append(symbol + ("@" + version if version else ""))
                        elif version and version not in provider["version_definitions"]:
                            version_fallbacks.append({"consumer": item["path"], "symbol": symbol,
                                                      "requested_version": version, "provider": provider["path"],
                                                      "match": "Bionic unversioned global; requested verdef absent in provider"})
                require(not missing, "Unresolved non-weak symbols in " + item["path"] + " (" + section + "/" + ns + "): " + ", ".join(sorted(missing)[:30]))
                checked.add(key)
        require(len(checked) == len(nodes), "Some ELF namespace groups were not checked")
        return {"name": name, "root": virtual, "canonical_root": root["path"], "section": section, "namespace": namespace,
                "elf_count": len(nodes), "nonweak_symbol_versions_checked": imports_checked,
                "unversioned_global_matches": version_fallbacks,
                "required_exports": list(required_exports),
                "dependencies": [{"namespace": key[0], "path": key[1], "soname": item["elf"].dt_soname,
                                  "sha256": item["sha256"], "needed": list(item["elf"].dt_needed),
                                  "version_definitions": sorted(item["version_definitions"])} for key, item in nodes.items()],
                "passed": True}


def verify_graphics_elf(product_out, aosp, scratch_dir):
    product, aosp, scratch = Path(product_out).resolve(), Path(aosp).resolve(), Path(scratch_dir).resolve()
    report = {"format": 1, "scope": "final installed ARM32 graphics ELF namespace and symbol dependency audit",
              "started_utc": datetime.now(timezone.utc).isoformat(), "passed": False, "graphics_verified": False,
              "requirements": requirements(aosp, product), "roots": []}
    try:
        require(scratch.is_dir() and not any(scratch.iterdir()), "Verification scratch directory must be empty")
        tools = check_tools(aosp, product)
        report["tools"] = {key: {"path": str(path), "sha256": sha256(path)} for key, path in tools.items()}
        for partition in ("system", "system_ext", "product", "vendor"):
            require((product / partition).is_dir(), "Missing final partition directory: " + partition)
        for basename in ("linker.config.pb", "llndk.libraries.txt", "sanitizer.libraries.txt"):
            require((product / "system/etc" / basename).is_file(), "Missing final system namespace input: " + basename)
        metadata = {}
        for partition in PARTITIONS:
            for relative in ("build.prop", "etc/build.prop", "etc/linker.config.pb", "etc/llndk.libraries.txt", "etc/sanitizer.libraries.txt", "etc/public.libraries.txt"):
                path = product / partition / relative
                if path.is_file():
                    metadata[str(path.relative_to(product))] = {"sha256": sha256(path), "identity": identity(path)}
        report["namespace_input_files"] = {key: {"sha256": value["sha256"]} for key, value in metadata.items()}
        root, apex_root = build_runtime_root(product, scratch, tools, report)
        sections = generate_namespaces(product, root, scratch, tools, report)
        checker = GraphicsChecker(ProductFiles(product, apex_root), sections, load_parser(tools["aosp_elf_parser"]), tools["llvm_readobj"])
        report["runtime_linker"] = {"path": checker.linker["path"], "sha256": checker.linker["sha256"]}
        for args in ROOTS:
            print("Checking graphics ELF " + args[0], file=sys.stderr, flush=True)
            report["roots"].append(checker.check_root(*args))
        for item in checker.cache.values():
            require(identity(item["physical"]) == item["identity"], "Installed ELF changed during the audit: " + item["path"])
        for relative, value in metadata.items():
            require(identity(product / relative) == value["identity"], "Namespace input changed during the audit: " + relative)
        report.update(passed=True, graphics_verified=True, result="PASS", unique_elf_files=len(checker.cache))
    except (OSError, ValueError, subprocess.SubprocessError, VerificationError) as error:
        report.update(result="FAIL", error=str(error))
        raise VerificationError(str(error), report) from error
    finally:
        report["finished_utc"] = datetime.now(timezone.utc).isoformat()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aosp", type=Path, required=True)
    parser.add_argument("--product-out", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--work-dir", type=Path, help="Existing empty directory; preserves extracted payload and generated configuration")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--requirements", action="store_true", help="Print required final paths without claiming verification")
    modes.add_argument("--check-tools", action="store_true", help="Check host tools and fixed AOSP ELF parser only")
    args = parser.parse_args()
    aosp = args.aosp.resolve()
    product = (args.product_out or aosp / "out/target/product/rk3288").resolve()
    code = 0
    try:
        if args.requirements:
            report = {"result": "REQUIREMENTS", "graphics_verified": False, **requirements(aosp, product)}
        elif args.check_tools:
            tools = check_tools(aosp, product)
            report = {"result": "TOOLS_READY", "graphics_verified": False, "tools": {key: str(value) for key, value in tools.items()}}
        elif args.work_dir:
            report = verify_graphics_elf(product, aosp, args.work_dir)
        else:
            with tempfile.TemporaryDirectory(prefix="firefly-graphics-elf-") as temporary:
                report = verify_graphics_elf(product, aosp, Path(temporary))
    except VerificationError as error:
        report = error.report or {"result": "FAIL", "graphics_verified": False, "error": str(error)}
        code = 1
    text = json.dumps(report, indent=2) + "\n"
    if args.report:
        args.report.write_text(text)
    print(text, end="")
    return code


if __name__ == "__main__":
    sys.exit(main())
