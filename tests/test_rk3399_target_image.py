#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Small independently constructed GPT fixtures; never real board images/devices."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import uuid
import zlib

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/prepare-rk3399-target.py'
SPEC = importlib.util.spec_from_file_location('target_image', SCRIPT)
tool = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(tool)
SIZE = 2 * 1024 * 1024
NAMES = ('boot', 'system', 'system_ext', 'product', 'vendor', 'metadata', 'userdata')
LAYOUT = tuple((name, (i + 1) * 65536, 65536) for i, name in enumerate(NAMES))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def fixture():
    """Independent fixture producer: does not call the image tool's GPT writer."""
    data = bytearray(SIZE)
    data[446:462] = struct.pack('<B3sB3sII', 0, b'\0\2\0', 0xEE, b'\xff\xff\xff', 1, SIZE // 512 - 1)
    data[510:512] = b'\x55\xaa'
    entries = bytearray(16384)
    records = []
    for i, (name, offset, length) in enumerate(LAYOUT):
        ident = uuid.UUID(int=i + 1)
        kind = uuid.UUID('ebd0a0a2-b9e5-4433-87c0-68b6b72699c7' if i == 0 else '0fc63daf-8483-4772-8e79-3d69d8477de4')
        entries[i * 128:(i + 1) * 128] = struct.pack('<16s16sQQQ72s', kind.bytes_le, ident.bytes_le,
            offset // 512, (offset + length) // 512 - 1, 0, name.encode('utf-16-le'))
        data[offset:offset + length] = bytes([i + 71]) * length
        records.append(dict(name=name, offset=offset, size=length, uuid=str(ident)))
    for here, partner, table in ((1, SIZE // 512 - 1, 2), (SIZE // 512 - 1, 1, SIZE // 512 - 33)):
        header = bytearray(struct.pack('<8sIIIIQQQQ16sQIII', b'EFI PART', 65536, 92, 0, 0,
            here, partner, 34, SIZE // 512 - 34, uuid.UUID(int=99).bytes_le, table, 128, 128, zlib.crc32(entries)))
        struct.pack_into('<I', header, 16, zlib.crc32(header))
        data[here * 512:here * 512 + 92] = header
        data[table * 512:table * 512 + 16384] = entries
    # Recognizable bootloader-area data must also survive.
    data[32768:32896] = b'loader-evidence!' * 8
    return bytes(data), records


class TargetImage(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.base, self.mf, self.vf, self.out = (self.root / s for s in ('base.img', 'base.json', 'verified.json', 'target.img'))
        self.original, parts = fixture()
        self.base.write_bytes(self.original)
        self.manifest = dict(format=1, board='firefly,firefly-rk3399', boot_medium='emmc', boot_device='fe330000.mmc',
            hardware_boot_verified=False, image_size=SIZE, image_sha256=sha(self.original), partitions=parts)
        checks = [dict(name=name, passed=True) for name in ('image-size', 'image-target', 'whole-image-sha256', 'inputs-remained-unchanged')]
        self.verified = dict(format=1, scope='original-firefly-rk3399-emmc-offline', result='PASS_OFFLINE_NOT_BOOTED',
            image_verified=True, image_sha256=sha(self.original), board_boot='pending', checks=checks,
            checks_executed=4, checks_passed=4, checks_failed=0)
        self.save_metadata()
        self.small = patch.multiple(tool, BASE_BYTES=SIZE, EXPECTED=LAYOUT)
        self.small.start()

    def tearDown(self):
        self.small.stop()
        self.temp.cleanup()

    def save_metadata(self):
        self.mf.write_text(json.dumps(self.manifest))
        self.vf.write_text(json.dumps(self.verified))

    def run_prepare(self, sectors=SIZE // 256):
        return tool.prepare(self.base, self.mf, self.vf, sectors, self.out)

    def assert_independent_gpt(self, data):
        sectors = len(data) // 512
        self.assertEqual(struct.unpack_from('<II', data, 454), (1, sectors - 1))
        copies = []
        for lba, other, table in ((1, sectors - 1, 2), (sectors - 1, 1, sectors - 33)):
            raw = bytearray(data[lba * 512:lba * 512 + 92])
            self.assertEqual(raw[:8], b'EFI PART')
            crc = struct.unpack_from('<I', raw, 16)[0]
            struct.pack_into('<I', raw, 16, 0)
            self.assertEqual(zlib.crc32(raw), crc)
            self.assertEqual(struct.unpack_from('<QQQQ', raw, 24), (lba, other, 34, sectors - 34))
            self.assertEqual(struct.unpack_from('<QII', raw, 72), (table, 128, 128))
            entries = data[table * 512:table * 512 + 16384]
            self.assertEqual(zlib.crc32(entries), struct.unpack_from('<I', raw, 88)[0])
            copies.append(entries)
        self.assertEqual(copies[0], copies[1])
        self.assertEqual(copies[0], self.original[1024:17408])

    def test_grows_gpt_only_and_binds_independent_evidence(self):
        result = self.run_prepare()
        written = self.out.read_bytes()
        self.assertEqual(len(written), SIZE * 2)
        self.assert_independent_gpt(written)
        self.assertEqual(written[1024:SIZE - 16896], self.original[1024:SIZE - 16896])
        self.assertEqual(written[SIZE - 16896:len(written) - 16896], bytes(SIZE))
        for part in result['partitions']:
            start, end = part['offset'], part['offset'] + part['size']
            self.assertEqual(written[start:end], self.original[start:end])
            self.assertEqual(part['sha256'], sha(self.original[start:end]))
        self.assertEqual(result['base_sha256'], sha(self.original))
        self.assertEqual(result['verification_sha256'], sha(self.vf.read_bytes()))
        self.assertEqual(result['base_manifest_sha256'], sha(self.mf.read_bytes()))
        self.assertEqual(result['target_sha256'], sha(written))
        self.assertEqual(json.loads(self.out.with_suffix('.img.json').read_text()), result)
        self.assertEqual(self.base.read_bytes(), self.original)

    def test_exact_capacity_preserves_entire_image(self):
        self.run_prepare(SIZE // 512)
        self.assertEqual(self.out.read_bytes(), self.original)

    def test_one_sector_growth_handles_overlapping_old_and_new_backup(self):
        self.run_prepare(SIZE // 512 + 1)
        written = self.out.read_bytes()
        self.assert_independent_gpt(written)
        self.assertEqual(written[SIZE - 16896:SIZE - 16384], bytes(512))

    def test_readback_rejects_a_bad_writer_before_publishing(self):
        real_writer = tool.target_header
        def damaged(*args):
            raw = bytearray(real_writer(*args))
            raw[16] ^= 1
            return bytes(raw)
        with patch.object(tool, 'target_header', side_effect=damaged):
            with self.assertRaisesRegex(ValueError, 'CRC'): self.run_prepare()
        self.assertFalse(self.out.exists())
        self.assertFalse(self.out.with_suffix('.img.json').exists())

    def test_rejects_small_huge_and_boolean_capacity_before_output(self):
        for sectors in (SIZE // 512 - 1, tool.MAX_TARGET_BYTES // 512 + 1, True):
            with self.subTest(sectors=sectors), self.assertRaises(ValueError):
                self.run_prepare(sectors)
        self.assertFalse(self.out.exists())
        self.assertFalse(self.out.with_suffix('.img.partial').exists())

    def test_rejects_mismatched_or_failed_verification(self):
        for key, bad in (('image_sha256', '0' * 64), ('result', 'FAIL'), ('image_verified', False), ('checks_failed', 1)):
            with self.subTest(key=key):
                original = self.verified[key]
                self.verified[key] = bad
                self.save_metadata()
                with self.assertRaises(ValueError): self.run_prepare()
                self.verified[key] = original
        self.assertFalse(self.out.exists())

    def test_rejects_changed_base_after_verified_report(self):
        altered = bytearray(self.original)
        altered[65536] ^= 1
        self.base.write_bytes(altered)
        with self.assertRaises(ValueError): self.run_prepare()

    def test_independent_reader_rejects_gpt_crc_even_with_matching_hashes(self):
        altered = bytearray(self.original)
        altered[528] ^= 1
        self.base.write_bytes(altered)
        self.manifest['image_sha256'] = self.verified['image_sha256'] = sha(altered)
        self.save_metadata()
        with self.assertRaisesRegex(ValueError, 'CRC'): self.run_prepare()

    def test_existing_image_and_sidecar_are_never_overwritten(self):
        for target in (self.out, self.out.with_suffix('.img.json')):
            target.write_bytes(b'keep')
            with self.assertRaises(ValueError): self.run_prepare()
            self.assertEqual(target.read_bytes(), b'keep')
            target.unlink()

    def test_device_paths_rejected_before_open(self):
        for value in ('/dev/mmcblk0', '\\\\.\\PhysicalDrive0', '\\\\?\\GLOBALROOT\\Device\\Harddisk0'):
            with self.subTest(value=value), self.assertRaises(ValueError): tool.safe_path(value)

    @unittest.skipUnless(os.name == 'posix', 'POSIX symlink fixture')
    def test_symlink_and_fifo_inputs_rejected(self):
        alias = self.root / 'alias.img'
        alias.symlink_to(self.base)
        with self.assertRaises(ValueError): tool.safe_path(alias)
        fifo = self.root / 'fifo.img'
        os.mkfifo(fifo)
        with self.assertRaises(ValueError): tool.open_regular(fifo)

    def test_decimal_capacity_rejects_rounded_and_hex_input(self):
        for value in ('29820MB', '1.5', '0x1800000', '-1'):
            with self.subTest(value=value), self.assertRaises(Exception): tool.decimal_sectors(value)
        self.assertEqual(tool.decimal_sectors('25165824'), 25165824)


if __name__ == '__main__':
    unittest.main()
