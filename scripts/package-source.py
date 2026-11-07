#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Create a portable source tarball from the explicit project allowlist.

The source root is the parent of scripts/. Upstream archives are optional
downloads, not required repository inputs. Only regular files and directories
are accepted. Generated outputs, keys and application APKs are excluded. The
manifest describes payload files; it excludes its own JSON file.

Example:
  python3 scripts/package-source.py --output /path/outside/port/source.tar.gz

No build, mount, device access or image creation is performed.
"""

import argparse
from dataclasses import dataclass
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import stat
import sys
import tarfile


ARCHIVE_ROOT = "firefly-rk3288-android17-source"
MANIFEST_NAME = "SOURCE-MANIFEST.json"
FILES = ("README.md", "BUILD.md", "LICENSE", "THIRD_PARTY.md", ".gitignore", ".gitattributes", "build.sh")
DIRECTORIES = ("boot", "device", "docs", "graphics", "kernel", "bootloader",
               "scripts", "manifests", "licenses", "patches", "variants", "tools", "tests")
PREBUILTS = frozenset({
    "device/firefly/rk3288/prebuilts/zImage",
    "device/firefly/rk3288/prebuilts/rk3288-firefly-android.dtb",
    "bootloader/idbloader.img",
    "bootloader/u-boot-dtb.img",
    "variants/emmc/boot/rk3288-firefly-android.dtb",
    "variants/emmc/bootloader/idbloader.img",
    "variants/emmc/bootloader/u-boot-dtb.img",
})
DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
FILE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC


class PackagingError(Exception):
    pass


def absolute(path):
    # Do not resolve links: open_directory rejects each symbolic component.
    return Path(os.path.abspath(os.fspath(path)))


def open_directory(path):
    descriptor = os.open("/", DIRECTORY_FLAGS)
    try:
        for component in path.parts[1:]:
            child = os.open(component, DIRECTORY_FLAGS, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def check_unchanged(before, after, path):
    if identity(before) != identity(after):
        raise PackagingError("Source changed during packaging: " + str(path))


def excluded(relative, info, include_prebuilts):
    parts = relative.parts
    if any(part in (".git", "__pycache__") for part in parts):
        return True
    if any(part in ("prebuilts", "jni", "keys", "signing-keys") for part in parts):
        return True
    if relative.name in ("zImage", "Image", "uImage", "id_rsa", "id_ed25519"):
        return True
    if relative.suffix.lower() in (".pyc", ".pyo"):
        return True
    if relative.suffix.lower() in (".apk", ".pk8", ".pem", ".jks", ".keystore", ".log"):
        return True
    if "records" in parts or "downloads" in parts:
        return True
    if "prebuilts" in parts and relative.as_posix() not in PREBUILTS:
        return True
    if relative.suffix.lower() in (".img", ".dtb", ".so", ".o", ".a"):
        if relative.as_posix() not in PREBUILTS or not include_prebuilts:
            return True
    if parts[:3] == ("variants", "emmc", "out"):
        return True
    if parts[:3] == ("variants", "emmc", "records") and relative.suffix == ".log":
        return True
    # Both media use the original kernel. Never carry a second identical copy.
    if relative.as_posix() == "variants/emmc/boot/zImage":
        return True
    if not include_prebuilts and relative.as_posix() == "variants/emmc/records/uboot-spl.dtb":
        return True
    if not include_prebuilts and relative.as_posix() in PREBUILTS:
        return True
    if stat.S_ISDIR(info.st_mode):
        if parts[0] == "kernel" and (relative.name in ("build", "staging")
                                      or relative.name.startswith("linux-")):
            return True
        if parts[0] == "bootloader" and relative.name in ("build", "u-boot-2024.01"):
            return True
    return False


class HashingReader:
    """Hash the exact bytes handed to tarfile, with no pre-hashing pass."""

    def __init__(self, stream):
        self.stream = stream
        self.sha256 = hashlib.sha256()
        self.bytes = 0

    def read(self, size=-1):
        data = self.stream.read(size)
        self.sha256.update(data)
        self.bytes += len(data)
        return data


@dataclass
class Package:
    archive: tarfile.TarFile
    include_prebuilts: bool

    def __post_init__(self):
        self.manifest = []
        self.directories = 0
        self.prebuilts = set()

    def header(self, relative, info):
        if relative.is_absolute() or any(part in ("", ".", "..") for part in relative.parts):
            raise PackagingError("Invalid source archive path: " + str(relative))
        item = tarfile.TarInfo(ARCHIVE_ROOT + "/" + relative.as_posix())
        item.uid = item.gid = 0
        item.uname = item.gname = ""
        # Preserve ordinary permission bits, including each executable bit;
        # never copy setuid/setgid/sticky privilege bits to the package.
        item.mode = stat.S_IMODE(info.st_mode) & 0o777
        item.mtime = int(info.st_mtime)
        return item

    def add(self, parent_fd, name, relative, required_type=None):
        before = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if excluded(relative, before, self.include_prebuilts):
            return
        if stat.S_ISLNK(before.st_mode):
            raise PackagingError("Symbolic link is not allowed: " + str(relative))
        is_directory = stat.S_ISDIR(before.st_mode)
        if not is_directory and not stat.S_ISREG(before.st_mode):
            raise PackagingError("Only regular files/directories are allowed: " + str(relative))
        if required_type == "directory" and not is_directory:
            raise PackagingError("Required source directory is not a directory: " + str(relative))
        if required_type == "file" and is_directory:
            raise PackagingError("Required source file is not a file: " + str(relative))
        descriptor = os.open(name, DIRECTORY_FLAGS if is_directory else FILE_FLAGS,
                             dir_fd=parent_fd)
        try:
            check_unchanged(before, os.fstat(descriptor), relative)
            item = self.header(relative, before)
            if is_directory:
                item.type = tarfile.DIRTYPE
                item.size = 0
                self.archive.addfile(item)
                self.directories += 1
                with os.scandir(descriptor) as iterator:
                    names = sorted(entry.name for entry in iterator)
                for child in names:
                    self.add(descriptor, child, relative / child)
            else:
                item.type = tarfile.REGTYPE
                item.size = before.st_size
                # dup keeps ownership of descriptor for the final fstat.
                with os.fdopen(os.dup(descriptor), "rb") as stream:
                    reader = HashingReader(stream)
                    self.archive.addfile(item, reader)
                if reader.bytes != before.st_size:
                    raise PackagingError("Incomplete source read: " + str(relative))
                self.manifest.append({"path": relative.as_posix(), "size": reader.bytes,
                                      "sha256": reader.sha256.hexdigest()})
                if relative.as_posix() in PREBUILTS:
                    self.prebuilts.add(relative.as_posix())
            check_unchanged(before, os.fstat(descriptor), relative)
            check_unchanged(before, os.stat(name, dir_fd=parent_fd, follow_symlinks=False), relative)
        finally:
            os.close(descriptor)

    def finish(self):
        if self.include_prebuilts and self.prebuilts != PREBUILTS:
            raise PackagingError("Missing requested prebuilts: " + ", ".join(sorted(PREBUILTS - self.prebuilts)))
        record = {
            "format": 1,
            "archive_root": ARCHIVE_ROOT,
            "include_prebuilts": self.include_prebuilts,
            "manifest_scope": "Payload regular files only; paths relative to archive_root; excludes this manifest",
            "files": sorted(self.manifest, key=lambda entry: entry["path"]),
        }
        data = (json.dumps(record, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
        item = tarfile.TarInfo(ARCHIVE_ROOT + "/" + MANIFEST_NAME)
        item.uid = item.gid = 0
        item.uname = item.gname = ""
        item.mode, item.mtime, item.size = 0o644, 0, len(data)
        self.archive.addfile(item, io.BytesIO(data))
        return {"files": len(self.manifest), "directories": self.directories,
                "payload_bytes": sum(entry["size"] for entry in self.manifest)}


def package(output, include_prebuilts):
    if include_prebuilts:
        raise PackagingError("The public source profile excludes binaries; --include-prebuilts is unsupported")
    source = absolute(__file__).parents[1]
    if output == source or source in output.parents:
        raise PackagingError("Output must be outside the source root: " + str(source))
    source_fd = open_directory(source)
    parent_fd = None
    partial_created = False
    partial_name = output.name + ".partial"
    try:
        parent_fd = open_directory(output.parent)
        try:
            os.stat(output.name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise PackagingError("Output already exists: " + str(output))
        descriptor = os.open(partial_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                             os.O_NOFOLLOW | os.O_CLOEXEC, 0o644, dir_fd=parent_fd)
        partial_created = True
        with os.fdopen(descriptor, "wb") as stream:
            with gzip.GzipFile(filename="", mode="wb", fileobj=stream, mtime=0) as compressed:
                with tarfile.open(fileobj=compressed, mode="w|", format=tarfile.PAX_FORMAT) as archive:
                    root = tarfile.TarInfo(ARCHIVE_ROOT)
                    root.type, root.mode, root.mtime = tarfile.DIRTYPE, 0o755, 0
                    root.uid = root.gid = 0
                    root.uname = root.gname = ""
                    archive.addfile(root)
                    contents = Package(archive, include_prebuilts)
                    for name in FILES:
                        contents.add(source_fd, name, PurePosixPath(name), "file")
                    for name in DIRECTORIES:
                        contents.add(source_fd, name, PurePosixPath(name), "directory")
                    result = contents.finish()
            stream.flush()
            os.fsync(stream.fileno())
            completed = os.fstat(stream.fileno())
        # Ensure the temporary pathname still names our completed ordinary
        # file before using it as the source of the atomic publication.
        current = os.stat(partial_name, dir_fd=parent_fd, follow_symlinks=False)
        check_unchanged(completed, current, partial_name)
        # A hard link publishes the completed file atomically, and fails if
        # another process created output meanwhile. It never replaces a file.
        os.link(partial_name, output.name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd,
                follow_symlinks=False)
        os.unlink(partial_name, dir_fd=parent_fd)
        partial_created = False
        os.fsync(parent_fd)
        result.update(output=str(output), include_prebuilts=include_prebuilts,
                      manifest=ARCHIVE_ROOT + "/" + MANIFEST_NAME)
        return result
    finally:
        if partial_created:
            os.unlink(partial_name, dir_fd=parent_fd)
        if parent_fd is not None:
            os.close(parent_fd)
        os.close(source_fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, required=True,
                        help="New .tar.gz outside the source root; parent directory must already exist")
    parser.add_argument("--include-prebuilts", action="store_true",
                        help="Include the shared kernel, SD/eMMC DTBs and both media's loader binaries")
    args = parser.parse_args()
    output = absolute(args.output)
    if not output.name.endswith(".tar.gz"):
        parser.error("--output must end in .tar.gz")
    try:
        result = package(output, args.include_prebuilts)
    except (OSError, PackagingError, tarfile.TarError) as error:
        print("Source packaging failed: " + str(error), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
