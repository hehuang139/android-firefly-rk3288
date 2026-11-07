#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Exercise graphics ELF resolution with isolated, actually linked ARM files."""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aosp", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    aosp = args.aosp.resolve()
    spec = importlib.util.spec_from_file_location("graphics_elf", Path(__file__).with_name("verify-graphics-elf.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    clang = aosp / "prebuilts/clang/host/linux-x86" / module.CLANG_VERSION / "bin/clang"
    readobj = clang.with_name("llvm-readobj")
    elf_parser = module.load_parser(aosp / "build/make/tools/check_elf_file.py")
    cases = []
    with tempfile.TemporaryDirectory(prefix="firefly-graphics-fixture-") as temporary:
        base = Path(temporary)
        product, apex = base / "product", base / "apex"
        for relative in ("system/bin", "system/lib", "vendor/lib/egl", "vendor/lib/hw"):
            (product / relative).mkdir(parents=True)
        (apex / "com.android.runtime/lib/bionic").mkdir(parents=True)
        config = module.parse_namespaces("""
[system]
namespace.sphal.isolated = true
namespace.sphal.search.paths = /vendor/${LIB}
namespace.sphal.search.paths += /vendor/${LIB}/egl
namespace.sphal.search.paths += /vendor/${LIB}/hw
namespace.sphal.permitted.paths = /vendor/${LIB}
namespace.sphal.links = default
namespace.sphal.link.default.shared_libs = libpublic.so:libbase.so
namespace.default.isolated = true
namespace.default.search.paths = /system/${LIB}
namespace.default.permitted.paths = /apex/com.android.runtime/${LIB}/bionic
[vendor]
namespace.default.isolated = true
namespace.default.search.paths = /vendor/${LIB}
""")
        serial = 0

        def build(relative, soname, source, libraries=(), version=None, extra=()):
            nonlocal serial
            serial += 1
            src = base / (str(serial) + ".c")
            src.write_text(source)
            output = product / relative
            output.parent.mkdir(parents=True, exist_ok=True)
            command = [str(clang), "--target=armv7a-linux-androideabi37", "-fuse-ld=lld", "-shared", "-nostdlib", "-fPIC",
                       "-Wl,-soname," + soname, str(src), "-o", str(output)]
            if version:
                script = base / (str(serial) + ".map")
                script.write_text(version)
                command.append("-Wl,--version-script=" + str(script))
            command.extend(str(product / library) for library in libraries)
            command.extend(extra)
            subprocess.run(command, capture_output=True, text=True, check=True)
            return output

        def check(relative, section="system", namespace="sphal"):
            checker = module.GraphicsChecker(module.ProductFiles(product, apex), config, elf_parser, readobj)
            return checker.check_root("fixture", section, namespace, "/" + relative, ("entry",))

        def passes(name, relative):
            assert check(relative)["passed"] is True
            cases.append({"case": name, "passed": True})

        def rejects(name, relative, substring):
            try:
                check(relative)
            except module.VerificationError as error:
                assert substring in str(error), str(error)
                cases.append({"case": name, "passed": True, "rejection": str(error)})
            else:
                raise AssertionError("Expected rejection: " + name)

        build("system/bin/linker", "ld-android.so", "int __loader_fixture(void) { return 0; }")
        provider = "vendor/lib/libversion.so"
        root = "vendor/lib/egl/libEGL_mesa.so"
        version_one = "V1 { global: dependency; local: *; };"
        build(provider, "libversion.so", "int dependency(void) { return 1; }", version=version_one)
        build(root, "libEGL.so", "extern int dependency(void); int entry(void) { return dependency(); }", [provider])
        passes("renamed Mesa root with original SONAME and matching versioned dependency", root)
        build(provider, "libversion.so", "int dependency(void) { return 2; }", version="V2 { global: dependency; local: *; };")
        rejects("wrong symbol version is rejected", root, "dependency@V1")
        build(provider, "libversion.so", "int dependency(void) { return 2; }")
        passes("Bionic accepts unversioned global when provider has no version definitions", root)
        build(provider, "libversion.so", "int dependency(void) { return 2; } int another(void) { return 3; }",
              version="V2 { global: another; };")
        passes("Bionic accepts global when requested version is absent among other definitions", root)
        build(provider, "libversion.so", "int dependency(void) { return 2; } int another(void) { return 3; }",
              version="V1 { global: another; };")
        rejects("requested version defined elsewhere in provider does not allow a global fallback", root, "dependency@V1")
        build(provider, "libversion.so", "int other(void) { return 2; }")
        rejects("missing non-weak symbol is rejected", root, "dependency@V1")
        # A same-named system file must not rescue a missing vendor dependency
        # when the namespace link does not export that filename.
        (product / provider).rename(product / "system/lib/libversion.so")
        rejects("unexported same-name system library cannot satisfy vendor DT_NEEDED", root, "Unresolved DT_NEEDED libversion.so")
        build(provider, "libversion.so", "int dependency(void) { return 1; }", version=version_one)
        weak = "vendor/lib/egl/libweak.so"
        build(weak, "libweak.so", "extern int optional(void) __attribute__((weak)); int entry(void) { return optional ? optional() : 0; }")
        passes("undefined weak symbol remains optional", weak)

        private, public = "system/lib/libprivate.so", "system/lib/libpublic.so"
        build(private, "libprivate.so", "int secret(void) { return 3; }")
        build(public, "libpublic.so", "extern int secret(void); int public_api(void) { return secret(); }", [private])
        cross = "vendor/lib/egl/libcross.so"
        build(cross, "libcross.so", "extern int public_api(void); int entry(void) { return public_api(); }", [public])
        passes("allowed LLNDK-style library resolves its private dependencies in its own namespace", cross)
        build(cross, "libcross.so", "extern int public_api(void), secret(void); int entry(void) { return public_api() + secret(); }", [public])
        rejects("private transitive system symbols do not leak into SP-HAL", cross, "Unresolved non-weak symbols")
        config["system"]["namespace.sphal.link.default.shared_libs"] += ":libprivate.so"
        rejects("namespace allowlist alone does not expose transitive symbols without a direct dependency", cross, "Unresolved non-weak symbols")
        build(cross, "libcross.so", "extern int public_api(void), secret(void); int entry(void) { return public_api() + secret(); }", [public, private])
        passes("explicit exported direct dependency makes its own symbols accessible", cross)

        # An installed absolute symlink must resolve in the extracted Android
        # root, including a real APEX payload; the host /apex is irrelevant.
        bionic = build("system/lib/libbase-payload.so", "libbase.so", "int base_api(void) { return 7; }")
        payload = apex / "com.android.runtime/lib/bionic/libbase.so"
        bionic.rename(payload)
        (product / "system/lib/libbase.so").symlink_to("/apex/com.android.runtime/lib/bionic/libbase.so")
        source = base / "apex-root.c"
        source.write_text("extern int base_api(void); int entry(void) { return base_api(); }")
        apex_consumer = product / "vendor/lib/egl/libapex-consumer.so"
        subprocess.run([str(clang), "--target=armv7a-linux-androideabi37", "-fuse-ld=lld", "-shared", "-nostdlib", "-fPIC", str(source), str(payload), "-o", str(apex_consumer)], capture_output=True, text=True, check=True)
        passes("installed absolute symlink selects extracted APEX payload", "vendor/lib/egl/libapex-consumer.so")
        payload.rename(payload.with_suffix(".absent"))
        rejects("missing extracted APEX payload cannot fall back to host or stubs", "vendor/lib/egl/libapex-consumer.so", "Unresolved DT_NEEDED libbase.so")

    report = {"scope": "isolated " + module.CLANG_VERSION + " ARM32 shared objects and namespace fixtures; no product output inspected",
              "result": "PASS", "graphics_verified": False, "cases_passed": len(cases), "cases": cases}
    if args.report:
        args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
