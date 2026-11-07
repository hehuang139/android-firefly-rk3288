#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Verify the actual TV kernel, media/remote drivers and isolated TF/eMMC DTBs."""
import argparse
import hashlib
import json
import re
import struct
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--root', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
checks = []


def check(name, condition, evidence):
    checks.append({'name': name, 'passed': bool(condition), 'evidence': evidence})


def config(path):
    values = {}
    for line in path.read_text().splitlines():
        found = re.match(r'(CONFIG_\w+)=(.*)', line)
        if found:
            values[found[1]] = found[2]
        found = re.match(r'# (CONFIG_\w+) is not set', line)
        if found:
            values[found[1]] = 'n'
    return values


def read_fdt(path):
    data = path.read_bytes()
    magic, size, cursor, off_strings = struct.unpack_from('>4I', data)
    assert magic == 0xD00DFEED and size == len(data)
    strings = data[off_strings:]
    stack, nodes = [], {}
    while True:
        token = struct.unpack_from('>I', data, cursor)[0]
        cursor += 4
        if token == 1:
            stop = data.index(0, cursor)
            stack.append(data[cursor:stop].decode())
            cursor = (stop + 4) & ~3
            nodes['/' + '/'.join(stack[1:])] = {}
        elif token == 2:
            stack.pop()
        elif token == 3:
            length, offset = struct.unpack_from('>2I', data, cursor)
            cursor += 8
            stop = strings.index(0, offset)
            name = strings[offset:stop].decode()
            nodes['/' + '/'.join(stack[1:])][name] = data[cursor:cursor + length]
            cursor = (cursor + length + 3) & ~3
        elif token == 4:
            continue
        elif token == 9:
            return nodes
        else:
            raise ValueError(f'Invalid FDT token {token}')


root = args.root.resolve()
build = root / 'build'
actual = config(build / '.config')
requested = config(root / 'firefly-tvbox.config')
mismatches = {key: {'requested': value, 'actual': actual.get(key, 'n')}
              for key, value in requested.items() if actual.get(key, 'n') != value}
check('requested_config', not mismatches, mismatches)
for key in ['RC_CORE', 'RC_MAP', 'RC_DECODERS', 'RC_DEVICES', 'LIRC', 'IR_GPIO_CIR',
            'IR_NEC_DECODER', 'IR_RC5_DECODER', 'IR_RC6_DECODER', 'IR_SONY_DECODER',
            'CEC_CORE', 'MEDIA_CEC_RC', 'DRM_DW_HDMI_CEC', 'VIDEO_DEV',
            'MEDIA_CONTROLLER', 'V4L2_MEM2MEM_DEV', 'VIDEO_HANTRO',
            'VIDEO_HANTRO_ROCKCHIP', 'SND_SOC_ROCKCHIP_I2S', 'SND_SIMPLE_CARD',
            'DRM_DW_HDMI_I2S_AUDIO', 'SND_SOC_HDMI_CODEC', 'USB_HID', 'INPUT_EVDEV',
            'MMC_DW_ROCKCHIP', 'ANDROID_BINDER_IPC', 'ANDROID_BINDERFS',
            'VIDEO_ROCKCHIP_VDEC', 'ZRAM', 'ZRAM_BACKEND_LZ4',
            'SYSCON_REBOOT_MODE', 'REBOOT_MODE']:
    value = actual.get('CONFIG_' + key, 'n')
    check('builtin_' + key, value == 'y', value)
check('release', (build / 'include/config/kernel.release').read_text().strip() ==
      '6.18.60-firefly-tvbox', (build / 'include/config/kernel.release').read_text().strip())
symbols = (build / 'System.map').read_text()
for name in ['hantro_probe', 'gpio_ir_recv_probe', 'init_rc_map_firefly_rk3288',
             'dw_hdmi_cec_probe', 'media_request_alloc', 'rc_keydown',
             'rkvdec_hevc_fmt_ops', 'rk3288_hevc_variant']:
    check('symbol_' + name, re.search(r'\b' + name + r'\b', symbols) is not None, name)
check('binder64_compile', (root / 'binder64-abi-check.o').stat().st_size > 0,
      (root / 'binder64-abi-check.o').stat().st_size)
zimage = build / 'arch/arm/boot/zImage'
check('zimage_header', struct.unpack_from('<I', zimage.read_bytes(), 0x24)[0] == 0x016F2818,
      zimage.stat().st_size)
dtb = build / 'arch/arm/boot/dts/rockchip/rk3288-firefly-tvbox.dtb'
emmc_dtb = build / 'arch/arm/boot/dts/rockchip/rk3288-firefly-tvbox-emmc.dtb'
nodes = read_fdt(dtb)


def prop(path, name):
    return nodes[path].get(name, b'').rstrip(b'\0').decode()


check('original_board', nodes['/']['compatible'] ==
      b'firefly,firefly-rk3288\0rockchip,rk3288\0', prop('/', 'model'))
for path in ['/mmc@ff0c0000', '/hdmi@ff980000', '/i2s@ff890000',
             '/ir-receiver', '/usb@ff580000']:
    check('enabled_' + path, prop(path, 'status') == 'okay', prop(path, 'status'))
check('hdmi_card', prop('/hdmi-sound', 'simple-audio-card,name') == 'HDMI',
      prop('/hdmi-sound', 'simple-audio-card,name'))
check('ir_map', prop('/ir-receiver', 'linux,rc-map-name') == 'rc-firefly-rk3288',
      prop('/ir-receiver', 'linux,rc-map-name'))
ir_gpio = struct.unpack('>3I', nodes['/ir-receiver']['gpios'])
check('original_ir_gpio7_a0', ir_gpio[1:] == (0, 1) and
      nodes['/pinctrl/gpio@ff7e0000']['phandle'] == struct.pack('>I', ir_gpio[0]), list(ir_gpio))
check('ir_wakeup_source', 'wakeup-source' in nodes['/ir-receiver'],
      'GPIO wakeup requested; board suspend wake requires the board test')
check('vpu_node', prop('/video-codec@ff9a0000', 'compatible') == 'rockchip,rk3288-vpu' and
      prop('/video-codec@ff9a0000', 'status') in ('', 'okay'),
      prop('/video-codec@ff9a0000', 'compatible'))
check('hevc_node', prop('/video-codec@ff9c0000', 'compatible') == 'rockchip,rk3288-hevc' and
      prop('/video-codec@ff9c0000', 'status') == 'okay',
      prop('/video-codec@ff9c0000', 'compatible'))
check('hevc_mmu', prop('/iommu@ff9c0440', 'status') == 'okay',
      prop('/iommu@ff9c0440', 'status'))
check('hevc_irq12', struct.unpack('>3I', nodes['/video-codec@ff9c0000']['interrupts']) ==
      (0, 12, 4), list(struct.unpack('>3I', nodes['/video-codec@ff9c0000']['interrupts'])))
reboot = '/power-management@ff730000/reboot-mode'
check('fastboot_reboot', nodes[reboot]['mode-bootloader'] == struct.pack('>I', 0x5242c309),
      'RK3288 PMU sys_reg3 -> U-Boot Fastboot')
check('sd_disables_emmc', prop('/mmc@ff0f0000', 'status') == 'disabled',
      prop('/mmc@ff0f0000', 'status'))
check('sd_50mhz', nodes['/mmc@ff0c0000']['max-frequency'] == struct.pack('>I', 50000000),
      list(struct.unpack('>I', nodes['/mmc@ff0c0000']['max-frequency'])))
emmc_nodes = read_fdt(emmc_dtb)
check('emmc_enables_emmc', emmc_nodes['/mmc@ff0f0000']['status'] == b'okay\0',
      emmc_nodes['/mmc@ff0f0000']['status'].rstrip(b'\0').decode())
check('emmc_disables_sd', emmc_nodes['/mmc@ff0c0000']['status'] == b'disabled\0',
      emmc_nodes['/mmc@ff0c0000']['status'].rstrip(b'\0').decode())
check('emmc_50mhz', emmc_nodes['/mmc@ff0f0000']['max-frequency'] == struct.pack('>I', 50000000),
      list(struct.unpack('>I', emmc_nodes['/mmc@ff0f0000']['max-frequency'])))
sd_common, emmc_common = {}, {}
for source, target in ((nodes, sd_common), (emmc_nodes, emmc_common)):
    for path, properties in source.items():
        target[path] = {name: value.hex() for name, value in properties.items()
                        if not (path in ('/mmc@ff0f0000', '/mmc@ff0c0000') and name == 'status')}
check('boot_variants_only_change_mmc_status', sd_common == emmc_common,
      'All non-status properties and all other nodes are identical')
artifacts = {}
for path in [zimage, dtb, emmc_dtb, build / '.config', build / 'System.map']:
    artifacts[str(path.relative_to(root))] = {
        'size': path.stat().st_size, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
result = {'passed': sum(c['passed'] for c in checks),
          'failed': sum(not c['passed'] for c in checks),
          'checks': checks, 'artifacts': artifacts,
          'validation': 'Cross-compile, config, symbols, Binder64 ABI and flattened device tree'}
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps({'passed': result['passed'], 'failed': result['failed'],
                  'output': str(args.output)}))
raise SystemExit(bool(result['failed']))
