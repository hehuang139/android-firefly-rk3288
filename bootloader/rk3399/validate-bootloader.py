#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check build identity and on-disk placement; this does not certify booting."""
from pathlib import Path
import argparse,hashlib,json,struct,subprocess
p=argparse.ArgumentParser();p.add_argument('build_root',type=Path);a=p.parse_args();r=a.build_root.resolve();out=r/'uboot';assets=r/'assets'
config=(out/'.config').read_text().splitlines()
for option in ['CONFIG_ARM64=y','CONFIG_ROCKCHIP_RK3399=y','CONFIG_DEFAULT_DEVICE_TREE="rk3399-firefly"','CONFIG_TPL=y','CONFIG_SPL=y','CONFIG_CMD_BOOTI=y','CONFIG_ENV_IS_NOWHERE=y','# CONFIG_ENV_IS_IN_MMC is not set','CONFIG_BAUDRATE=1500000','CONFIG_BOOTSTD_FULL=y','CONFIG_CMD_BOOTFLOW_FULL=y','CONFIG_BOOTCOMMAND="bootflow scan -lbG mmc0"']:
 assert option in config,option
assert 'CONFIG_ROCKCHIP_EXTERNAL_TPL=y' not in config
assert 'CONFIG_VIDEO=y' not in config
fdt=lambda path,node,prop:subprocess.check_output(['fdtget',str(path),node,prop],text=True).strip()
assert fdt(out/'u-boot.dtb','/','compatible')=='firefly,firefly-rk3399 rockchip,rk3399'
assert fdt(out/'u-boot.dtb','/aliases','mmc1')=='/mmc@fe320000'
assert fdt(out/'u-boot.dtb','/aliases','mmc0')=='/mmc@fe330000'
assert fdt(out/'spl/u-boot-spl.dtb','/chosen','u-boot,spl-boot-order')=='/mmc@fe330000'
uboot=(out/'u-boot.bin').read_bytes();assert b'boot_targets=mmc0\0' in uboot
env={}
for key in ['bootcmd','boot_targets','kernel_addr_r','fdt_addr_r','ramdisk_addr_r','scriptaddr','fdtfile']:
 hits=[s.decode(errors='replace') for s in uboot.split(b'\0') if s.startswith((key+'=').encode())]
 assert len(hits)==1,(key,hits);env[key]=hits[0].split('=',1)[1]
assert env['bootcmd']=='bootflow scan -lbG mmc0'
assert env['kernel_addr_r']=='0x02000000'
idb=(assets/'idbloader.img').read_bytes();fit=(assets/'u-boot.itb').read_bytes();combined=(assets/'u-boot-rockchip.bin').read_bytes()
assert combined[:len(idb)]==idb
assert combined[0x7f8000:0x7f8000+len(fit)]==fit
assert len(idb)<0x3f8000 and len(fit)<0x800000
assert fit[:4]==bytes.fromhex('d00dfeed')
bl31=(assets/'bl31.elf').read_bytes();assert bl31[:6]==b'\x7fELF\x02\x01' and struct.unpack_from('<H',bl31,18)[0]==183
listing=(r/'fit-list.txt').read_text();assert 'ARM Trusted Firmware' in listing and 'rk3399-firefly' in listing
for part in ['tpl/u-boot-tpl.bin','spl/u-boot-spl.bin']:assert (out/part).stat().st_size>4096
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
report={'status':'OFFLINE_BUILD_VALIDATED_NOT_BOOTED','board':'original Firefly-RK3399 DDR3','uboot':'v2024.01','tf_a':'v2.10','source_patches':['SPL eMMC-only order','U-Boot eMMC-only boot_targets'],'ddr':'mainline rk3399-sdram-ddr3-1600 TPL','environment':'nowhere','console':'UART2 1500000 8N1','spl_boot_order':'/mmc@fe330000 only','default_environment':env,'bootrom_priority_changed':False,'placement_bytes':{'idbloader.img':32768,'u-boot.itb':8388608,'u-boot-rockchip.bin':32768},'assets':{p.name:{'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(assets.iterdir()) if p.is_file()},'config_sha256':sha(out/'.config'),'not_a_usb_ram_loader':True}
report['source_patches'].append('ARM64 zero-offset Image load address 0x02000000')
source=r/'src/u-boot-2024.01'
report['modified_source_sha256']={name:sha(source/name) for name in ['arch/arm/dts/rk3399-firefly-u-boot.dtsi','include/configs/rockchip-common.h','include/configs/rk3399_common.h']}
(r/'bootloader-manifest.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
