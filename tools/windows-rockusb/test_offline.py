"""No test imports the legacy hardware modules or constructs a live USB transport."""
import contextlib
import copy
import hashlib
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest import mock
import rockusb_core as core
import readonly_probe as probe


class FakeDevice:
    def __init__(self, identity, data):
        self.identity = copy.deepcopy(identity)
        self.data = bytearray(data)
        self.writes, self.reads = [], []
        self.corrupt_immediate = self.corrupt_final = self.disconnect = False
        self.source_to_change = None

    def snapshot(self):
        result = copy.deepcopy(self.identity)
        if self.disconnect and self.writes:
            result["device_address"] += 1
        return result

    def read_lba(self, lba, count):
        self.reads.append((lba, count))
        start, end = lba * 512, (lba + count) * 512
        data = bytes(self.data[start:end])
        if self.corrupt_immediate and self.writes:
            return b"!" + data[1:]
        chunks = (len(self.data) + 131071) // 131072
        if self.corrupt_final and len(self.reads) > chunks:
            return b"!" + data[1:]
        return data

    def write_lba(self, lba, data):
        self.writes.append(lba)
        self.data[lba * 512:lba * 512 + len(data)] = data
        if self.source_to_change:
            with self.source_to_change.open("ab") as stream:
                stream.write(b"changed")


class WholeImageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="rk3399-offline-writer-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source, self.report = self.root / "synthetic.img", self.root / "report.jsonl"
        self.data = b"".join(bytes([50 + i]) * 131072 for i in range(3)) + b"Z" * 512
        self.source.write_bytes(self.data)
        self.sha = hashlib.sha256(self.data).hexdigest()
        self.identity = dict(vid=core.VID, pid=core.PID, unique=True, storage="emmc",
             sector_bytes=512, capacity_sectors=len(self.data) // 512 + 1024,
             device_address=7, descriptor_hex="mock-only", hub_port=3,
             physical_lba_verified=True, active_loader_verified=True,
             loader_sha256=core.LOADER_SHA256)
        self.device = FakeDevice(self.identity, bytes(len(self.data)))

    def run_core(self, execute=False, confirm=None, identity=None, sha=None):
        core.whole_image(self.device, self.source, sha or self.sha,
                         identity or self.identity, self.report,
                         execute=execute, confirm=confirm)

    def execute(self):
        self.run_core(True, core.confirmation(self.identity, self.sha))

    def records(self):
        return [json.loads(line) for line in self.report.read_text().splitlines()]

    def assert_failed(self, call):
        with self.assertRaises((ValueError, RuntimeError, IOError)):
            call()
        self.assertEqual(self.records()[-1]["stage"], "failed")
        self.assertNotIn("complete", [r["stage"] for r in self.records()])

    def test_default_is_read_only_even_when_image_differs(self):
        self.run_core()
        self.assertEqual(self.device.writes, [])
        self.assertEqual(self.records()[-1]["stage"], "audit_complete")
        self.assertEqual(self.records()[-1]["different_bytes"], len(self.data))

    def test_write_immediate_and_full_readback_include_short_final_chunk(self):
        self.execute()
        self.assertEqual(self.device.writes, [256, 512, 768, 0])
        self.assertEqual(len(self.device.reads), 8)
        self.assertEqual(self.device.reads[-1], (768, 1))
        result = self.records()[-1]
        self.assertEqual(result["physical_readback_sha256"], self.sha)
        self.assertEqual(result["verified_bytes"], len(self.data))
        self.assertFalse(result["unused_media_tail_verified"])

    def test_write_requires_image_and_device_confirmation(self):
        self.assert_failed(lambda: self.run_core(True))
        self.assertEqual(self.device.writes, [])

    def test_probe_identity_cannot_enable_writes(self):
        self.identity["physical_lba_verified"] = False
        self.device.identity = copy.deepcopy(self.identity)
        self.assert_failed(self.execute)
        self.assertEqual(self.device.writes, [])

    def test_local_loader_hash_does_not_prove_running_loader(self):
        self.identity["active_loader_verified"] = False
        self.device.identity = copy.deepcopy(self.identity)
        self.assert_failed(self.execute)
        self.assertEqual(self.device.writes, [])

    def test_wrong_soc_rejected(self):
        self.identity["pid"] = 0x320a
        self.assert_failed(self.execute)
        self.assertEqual(self.device.writes, [])

    def test_capacity_is_observed_and_not_old_fixed_geometry(self):
        self.identity["capacity_sectors"] = 2
        self.assert_failed(self.execute)
        self.assertEqual(self.device.writes, [])

    def test_source_hash_mismatch_rejected_before_write(self):
        self.assert_failed(lambda: self.run_core(True, "irrelevant", sha="0" * 64))
        self.assertEqual(self.device.writes, [])

    def test_immediate_mismatch_stops_without_retry(self):
        self.device.corrupt_immediate = True
        self.assert_failed(self.execute)
        self.assertEqual(len(self.device.writes), 1)

    def test_final_mismatch_never_reports_complete(self):
        self.device.corrupt_final = True
        self.assert_failed(self.execute)
        self.assertEqual(len(self.device.writes), 4)

    def test_disconnection_stops_without_reopen(self):
        self.device.disconnect = True
        self.assert_failed(self.execute)
        self.assertEqual(len(self.device.writes), 1)

    def test_source_mutation_stops_without_more_writes(self):
        self.device.source_to_change = self.source
        self.assert_failed(self.execute)
        self.assertEqual(len(self.device.writes), 1)

    def test_existing_report_is_not_overwritten(self):
        self.report.write_text("previous evidence")
        with self.assertRaises(FileExistsError):
            self.run_core()
        self.assertEqual(self.report.read_text(), "previous evidence")
        self.assertEqual(self.device.writes, [])


class ProtocolTests(unittest.TestCase):
    def test_cbw_byte_order_and_read_direction(self):
        data, tag = core.cbw(core.READ_LBA, tag=42, lba=0x12345, sectors=128, capacity=0x20000)
        self.assertEqual(len(data), 31)
        self.assertEqual(struct.unpack_from("<III", data), (0x43425355, 42, 65536))
        self.assertEqual(data[12:16], bytes([0x80, 0, 10, 0x14]))
        self.assertEqual(struct.unpack_from(">I", data, 17)[0], 0x12345)
        self.assertEqual(struct.unpack_from(">H", data, 22)[0], 128)

    def test_strict_csw_rejects_old_loader_residue_exception(self):
        core.check_csw(struct.pack("<IIIB", 0x53425355, 2, 0, 0), 2)
        for raw in (b"short", struct.pack("<IIIB", 0x53425355, 2, 0x0b000000, 0),
                    struct.pack("<IIIB", 0x53425355, 3, 0, 0),
                    struct.pack("<IIIB", 0x53425355, 2, 0, 1)):
            with self.assertRaises(IOError):
                core.check_csw(raw, 2)

    def test_boundaries_and_unsupported_commands(self):
        for lba, count, cap in ((0, 0, 1), (0, 257, 1000), (99, 2, 100),
                                (0xffffffff, 2, 0x200000000), (-1, 1, 100)):
            with self.assertRaises(ValueError):
                core.cbw(core.READ_LBA, lba=lba, sectors=count, capacity=cap)
        for operation in (0, 0xff, 0x17, 0x18, 0x25, 0x2a):
            with self.assertRaises(ValueError):
                core.cbw(operation)

    def test_windows_readonly_backend_rejects_write_before_hardware_access(self):
        transport = probe.WindowsReadOnly.__new__(probe.WindowsReadOnly)
        with self.assertRaises(ValueError):
            transport.read_command(core.WRITE_LBA)

    def test_default_cli_never_constructs_usb_transport(self):
        with mock.patch.object(probe, "check_local_loader", return_value={"mock": True}), \
             mock.patch.object(probe, "WindowsReadOnly", side_effect=AssertionError("USB forbidden")), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(probe.main([]), 0)
        self.assertFalse(json.loads(output.getvalue())["usb_opened"])

    def test_hub_descriptor_rejects_rk3288(self):
        data = bytearray(35)
        data[4:6] = b"\x12\x01"
        struct.pack_into("<HH", data, 12, core.VID, 0x320a)
        struct.pack_into("<I", data, 31, 1)
        with self.assertRaises(RuntimeError):
            probe.parse_hub_connection(data)
        struct.pack_into("<H", data, 14, core.PID)
        self.assertIn("descriptor_hex", probe.parse_hub_connection(data))


if __name__ == "__main__":
    unittest.main()
