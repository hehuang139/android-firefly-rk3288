"""RK3399 Windows RockUSB probe; default is an offline loader check.

--probe permits only descriptor queries and documented storage READ commands.
No live-device write, reset, erase, RAM access, loader download or retry exists.
"""
import argparse
import ctypes as c
from ctypes import wintypes as w
import hashlib
import json
import os
from pathlib import Path
import re
import struct
from rockusb_core import (VID, PID, LOADER_SHA256, READ_LENGTHS, READ_FLASH_ID,
                         READ_CHIP_INFO, READ_FLASH_INFO, READ_STORAGE, READ_LBA,
                         cbw, check_csw, sha256_file)


def check_local_loader(directory):
    directory = Path(directory)
    manifest = json.loads((directory / "usb-loader-manifest.json").read_text("utf-8-sig"))
    item = manifest["artifact"]
    if (item["name"] != "rk3399_loader_v1.30.130.bin"
            or item["sha256"] != LOADER_SHA256 or item["bytes"] != 454990):
        raise ValueError("Loader manifest differs from pinned RK3399 artifact")
    loader = directory / item["name"]
    if loader.stat().st_size != item["bytes"] or sha256_file(loader) != LOADER_SHA256:
        raise ValueError("Local RK3399 loader bytes do not match manifest")
    return dict(path=str(loader.resolve()), bytes=item["bytes"], sha256=LOADER_SHA256,
                local_file_verified=True, active_loader_verified=False)


def parse_hub_connection(raw):
    if len(raw) < 35 or struct.unpack_from("<I", raw, 31)[0] != 1:
        raise RuntimeError("Selected hub port does not contain a connected device")
    descriptor = raw[4:22]
    if descriptor[:2] != b"\x12\x01" or struct.unpack_from("<HH", descriptor, 8) != (VID, PID):
        raise RuntimeError("Selected port is not VID 2207 PID 330c")
    return dict(descriptor_hex=descriptor.hex(),
                device_address=struct.unpack_from("<H", raw, 25)[0],
                configuration=raw[22], speed_code=raw[23],
                open_pipes=struct.unpack_from("<I", raw, 27)[0])


class WindowsReadOnly:
    """Lazy Win32 loading: importing this module never touches USB devices."""
    def __init__(self, hub_path, hub_port, event):
        if os.name != "nt":
            raise RuntimeError("Live read-only transport requires Windows")
        if not 1 <= hub_port <= 255:
            raise ValueError("Invalid USB hub port")
        self.event, self.hub_port = event, hub_port
        self.handles = []
        self.capacity = 0
        self.bad = c.c_void_p(-1).value

        class GUID(c.Structure):
            _fields_ = [("a", w.DWORD), ("b", w.WORD), ("d", w.WORD), ("e", c.c_ubyte * 8)]

        class Interface(c.Structure):
            _fields_ = [("size", w.DWORD), ("guid", GUID), ("flags", w.DWORD),
                        ("reserved", c.c_size_t)]

        self.Interface = Interface
        self.guid = GUID(0xa5dcbf10, 0x6530, 0x11d2,
                         (c.c_ubyte * 8)(0x90, 0x1f, 0, 0xc0, 0x4f, 0xb9, 0x51, 0xed))
        self.s = c.WinDLL("setupapi", use_last_error=True)
        self.k = c.WinDLL("kernel32", use_last_error=True)
        signatures = {
            "SetupDiGetClassDevsW": ([c.POINTER(GUID), w.LPCWSTR, w.HWND, w.DWORD], w.HANDLE),
            "SetupDiEnumDeviceInterfaces": ([w.HANDLE, c.c_void_p, c.POINTER(GUID),
                                              w.DWORD, c.POINTER(Interface)], w.BOOL),
            "SetupDiGetDeviceInterfaceDetailW": ([w.HANDLE, c.POINTER(Interface),
                c.c_void_p, w.DWORD, c.POINTER(w.DWORD), c.c_void_p], w.BOOL),
            "SetupDiDestroyDeviceInfoList": ([w.HANDLE], w.BOOL),
        }
        for name, (args, ret) in signatures.items():
            function = getattr(self.s, name)
            function.argtypes, function.restype = args, ret
        signatures = {
            "CreateFileW": ([w.LPCWSTR, w.DWORD, w.DWORD, c.c_void_p, w.DWORD,
                              w.DWORD, w.HANDLE], w.HANDLE),
            "ReadFile": ([w.HANDLE, c.c_void_p, w.DWORD, c.POINTER(w.DWORD), c.c_void_p], w.BOOL),
            "WriteFile": ([w.HANDLE, c.c_void_p, w.DWORD, c.POINTER(w.DWORD), c.c_void_p], w.BOOL),
            "DeviceIoControl": ([w.HANDLE, w.DWORD, c.c_void_p, w.DWORD, c.c_void_p,
                                  w.DWORD, c.POINTER(w.DWORD), c.c_void_p], w.BOOL),
            "CloseHandle": ([w.HANDLE], w.BOOL),
        }
        for name, (args, ret) in signatures.items():
            function = getattr(self.k, name)
            function.argtypes, function.restype = args, ret
        try:
            paths = self.paths()
            if len(paths) != 1 or not re.search(r"vid_2207&pid_330c(?=[&#])", paths[0], re.I):
                raise RuntimeError("Exactly one Rockchip interface, PID 330c, is required")
            self.path = paths[0]
            self.hub = self.open_file(hub_path, 0, 3)
            self.connection = self.hub_connection()
            # Retain the pipes for the session. Exclusive sharing rejects a
            # competing RKDevTool access rather than silently interleaving CBWs.
            self.output = self.open_file(self.path + "\\PIPE01", 0x40000000, 0)
            self.input = self.open_file(self.path + "\\PIPE00", 0x80000000, 0)
            self.guard()
            self.event("session", device_path=self.path, hub_path=hub_path,
                       hub_port=hub_port, **self.connection)
        except BaseException:
            self.close()
            raise

    def paths(self):
        devices = self.s.SetupDiGetClassDevsW(c.byref(self.guid), None, None, 0x12)
        if devices == self.bad:
            raise c.WinError(c.get_last_error())
        paths = []
        try:
            index = 0
            while True:
                item = self.Interface()
                item.size = c.sizeof(item)
                if not self.s.SetupDiEnumDeviceInterfaces(devices, None,
                        c.byref(self.guid), index, c.byref(item)):
                    if c.get_last_error() == 259:
                        return paths
                    raise c.WinError(c.get_last_error())
                needed = w.DWORD()
                self.s.SetupDiGetDeviceInterfaceDetailW(devices, c.byref(item),
                                                       None, 0, c.byref(needed), None)
                if needed.value < 8:
                    raise RuntimeError("Invalid device-interface detail length")
                detail = c.create_string_buffer(needed.value)
                struct.pack_into("<I", detail, 0, 8 if c.sizeof(c.c_void_p) == 8 else 6)
                if not self.s.SetupDiGetDeviceInterfaceDetailW(devices, c.byref(item),
                        detail, needed.value, c.byref(needed), None):
                    raise c.WinError(c.get_last_error())
                path = c.wstring_at(c.addressof(detail) + 4)
                if "vid_2207&" in path.lower():
                    paths.append(path)
                index += 1
        finally:
            self.s.SetupDiDestroyDeviceInfoList(devices)

    def open_file(self, path, access, sharing):
        handle = self.k.CreateFileW(path, access, sharing, None, 3, 0, None)
        if handle == self.bad:
            raise c.WinError(c.get_last_error())
        self.handles.append(handle)
        return handle

    def hub_connection(self):
        buffer = c.create_string_buffer(4096)
        struct.pack_into("<I", buffer, 0, self.hub_port)
        count = w.DWORD()
        if not self.k.DeviceIoControl(self.hub, 0x220448, buffer, len(buffer),
                                     buffer, len(buffer), c.byref(count), None):
            raise c.WinError(c.get_last_error())
        return parse_hub_connection(buffer.raw[:count.value])

    def guard(self):
        if self.paths() != [self.path]:
            raise RuntimeError("Interface changed or target no longer unique")
        now = self.hub_connection()
        for field in ("descriptor_hex", "device_address", "configuration", "speed_code"):
            if now[field] != self.connection[field]:
                raise RuntimeError("USB connection identity changed: " + field)

    def _write_cbw(self, data):
        count = w.DWORD()
        buffer = c.create_string_buffer(data, len(data))
        if not self.k.WriteFile(self.output, buffer, len(data), c.byref(count), None):
            raise c.WinError(c.get_last_error())
        if count.value != len(data):
            raise IOError("Short USB command transfer; no retry")

    def _read(self, maximum, minimum=None):
        count = w.DWORD()
        buffer = c.create_string_buffer(maximum)
        if not self.k.ReadFile(self.input, buffer, maximum, c.byref(count), None):
            raise c.WinError(c.get_last_error())
        minimum = maximum if minimum is None else minimum
        if not minimum <= count.value <= maximum:
            raise IOError("Unexpected USB read size " + str(count.value))
        return buffer.raw[:count.value]

    def read_command(self, opcode, *, lba=0, sectors=0):
        if opcode not in (*READ_LENGTHS, READ_LBA):
            raise ValueError("This Windows backend rejects every non-read opcode")
        self.guard()
        command, tag = cbw(opcode, lba=lba, sectors=sectors, capacity=self.capacity)
        self._write_cbw(command)
        size = sectors * 512 if opcode == READ_LBA else READ_LENGTHS[opcode]
        data = self._read(512, 11) if opcode == READ_FLASH_INFO else self._read(size)
        status = self._read(13)
        self.event("read_response", opcode=hex(opcode), lba=lba,
                   bytes=len(data), csw_hex=status.hex(),
                   prefix_hex=data[:64].hex(), sha256=hashlib.sha256(data).hexdigest())
        check_csw(status, tag)
        self.guard()
        return data

    def close(self):
        for handle in reversed(self.handles):
            self.k.CloseHandle(handle)
        self.handles.clear()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--loader-dir", type=Path, default=Path("USB-Loader"),
                        help="Directory containing the pinned loader and usb-loader-manifest.json")
    parser.add_argument("--probe", action="store_true", help="Explicitly enable hardware reads")
    parser.add_argument("--hub-path")
    parser.add_argument("--hub-port", type=int)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    loader = check_local_loader(args.loader_dir)
    if not args.probe:
        print(json.dumps(dict(stage="offline_plan", loader=loader, usb_opened=False,
                              live_write_cli_available=False), ensure_ascii=False, indent=2))
        return 0
    if not args.hub_path or not args.hub_port or not args.report:
        parser.error("--probe requires --hub-path, --hub-port and a new --report")
    device = None
    with args.report.open("x", encoding="utf-8") as report:
        def event(stage, **detail):
            line = json.dumps(dict(stage=stage, **detail), ensure_ascii=False)
            report.write(line + "\n")
            report.flush()
            print(line, flush=True)
        try:
            event("local_loader", **loader)
            device = WindowsReadOnly(args.hub_path, args.hub_port, event)
            chip = device.read_command(READ_CHIP_INFO)
            flash_id = device.read_command(READ_FLASH_ID)
            info = device.read_command(READ_FLASH_INFO)
            capacity = struct.unpack_from("<I", info)[0]
            if not 0 < capacity <= 0xffffffff:
                raise ValueError("Invalid reported storage capacity")
            device.capacity = capacity
            storage_bits = struct.unpack("<I", device.read_command(READ_STORAGE))[0]
            event("identity_reads", chip_info_hex=chip.hex(), flash_id_hex=flash_id.hex(),
                  flash_info_hex=info.hex(), capacity_sectors=capacity,
                  storage_bits=storage_bits, storage_is_emmc=flash_id[:4] == b"EMMC")
            if flash_id[:4] != b"EMMC" or storage_bits != 2:
                raise RuntimeError("eMMC identity is not unambiguous; no LBA samples taken")
            samples = sorted(set([0, 64, min(0x2000, capacity - 1),
                                  min(0x10000, capacity - 1), capacity // 4,
                                  capacity // 2, capacity * 3 // 4, capacity - 1]))
            for lba in samples:
                data = device.read_command(READ_LBA, lba=lba, sectors=min(128, capacity - lba))
                event("sample", lba=lba, bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
                      all_zero=not any(data), all_ff=data == b"\xff" * len(data),
                      all_cc=data == b"\xcc" * len(data))
            device.guard()
            event("probe_complete", media_written_bytes=0, active_loader_verified=False,
                  physical_lba_verified=False, live_write_cli_available=False,
                  reset_issued=False, automatic_retry=False)
            return 0
        except BaseException as error:
            event("failed", error=repr(error), media_written_bytes=0,
                  automatic_retry=False, reset_issued=False)
            raise
        finally:
            if device is not None:
                device.close()


if __name__ == "__main__":
    raise SystemExit(main())
