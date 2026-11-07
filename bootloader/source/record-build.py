#!/usr/bin/env python3
"""Record inputs, inspect ARM symbols and check emitted legacy image CRCs."""
# SPDX-License-Identifier: MIT
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import zlib


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--image',required=True);a=p.parse_args()
    root=Path(__file__).resolve().parent;build=root/'build';text=(root/'uboot.config').read_text()
    required=['CONFIG_ENV_IS_NOWHERE=y','CONFIG_MISC_INIT_R=y','CONFIG_MISC=y','CONFIG_ROCKCHIP_EFUSE=y','CONFIG_HASH=y','CONFIG_SHA256=y','CONFIG_BOOTSTD_FULL=y','CONFIG_BOOTCOMMAND="setenv boot_targets mmc1; bootflow scan -lb"']
    for flag in required:
        assert flag in text.splitlines(),flag
    for flag in ['CONFIG_ENV_IS_IN_MMC=y','CONFIG_ENV_IS_IN_EXT4=y','CONFIG_ENV_IS_IN_SPI_FLASH=y','CONFIG_CMD_FUSE=y']:
        assert flag not in text.splitlines(),flag
    commands=[['arm-linux-gnueabihf-gcc','--version'],['arm-linux-gnueabihf-nm','build/u-boot'],['fdtget','build/u-boot.dtb','/efuse@ffb40000','compatible']]
    outputs=[]
    for cmd in commands:
        result=subprocess.run(['docker','run','--rm','--user',str(__import__('os').getuid())+':'+str(__import__('os').getgid()),'-v',str(root)+':/build','-w','/build',a.image,*cmd],check=True,text=True,capture_output=True);outputs.append(result.stdout)
    symbols=outputs[1]
    strong_line=next(l for l in symbols.splitlines() if l.endswith(' T misc_init_r'))
    for symbol in ['rockchip_cpuid_from_efuse','rockchip_cpuid_set','rockchip_setup_macaddr','fdt_root','fdt_fixup_ethernet']:
        assert any(l.endswith(' '+symbol) for l in symbols.splitlines()),symbol
    assert outputs[2].strip()=='rockchip,rk3288-efuse',outputs[2]
    image=(root.parent/'u-boot-dtb.img').read_bytes()
    magic,hcrc,timestamp,size,load,entry,dcrc=struct.unpack('>7I',image[:28])
    assert magic==0x27051956
    header=bytearray(image[:64]);header[4:8]=b'\0'*4
    assert zlib.crc32(header)==hcrc
    assert len(image)==size+64
    assert zlib.crc32(image[64:])==dcrc
    record={
        'upstream':'https://github.com/u-boot/u-boot','version':'v2024.01',
        'source_archive_url':'https://codeload.github.com/u-boot/u-boot/tar.gz/refs/tags/v2024.01',
        'source_archive_sha256':sha(root/'u-boot-v2024.01.tar.gz'),
        'source_date_epoch':1704672000,'defconfig':'firefly-rk3288_defconfig',
        'docker_image':a.image,
        'docker_image_id':subprocess.check_output(['docker','image','inspect','--format','{{.Id}}',a.image],text=True).strip(),
        'cross_compiler':outputs[0].splitlines()[0],
        'configuration_changes':required+['CONFIG_LOCALVERSION="-firefly-android-sd1"','CONFIG_CMD_FUSE is not set'],
        'identity':{'source':'RK3288 CPU ID, read-only eFuse offset7 length16','serial':'upstream Rockchip even/odd-byte CRC32 mixing','mac':'upstream SHA256 of hex CPU ID, local/unicast Ethernet address','failure':'nonfatal; no shared serial fallback; normal network random-MAC fallback remains available','environment':'RAM only; never saved to MMC'},
        'patches':[{'path':str(x.relative_to(root)),'sha256':sha(x)} for x in sorted((root/'patches').glob('*.patch'))],
        'config_sha256':sha(root/'uboot.config'),
        'rebuild_script_sha256':sha(root/'rebuild-u-boot.sh'),
        'checks':{'strong_board_misc_init_r':strong_line,'efuse_compatible':outputs[2].strip(),'legacy_header_crc':True,'legacy_payload_crc':True,'identity_fault_injection':json.loads((root/'identity-init-validation.json').read_text())},
        'artifacts':{}
    }
    for n,offset in [('idbloader.img',32768),('u-boot-dtb.img',8388608),('u-boot-rockchip.bin',32768)]:
        path=build/n;record['artifacts'][n]={'size_bytes':path.stat().st_size,'sha256':sha(path),'disk_offset_bytes':offset}
    (root/'uboot-manifest.json').write_text(json.dumps(record,indent=2)+'\n')
    (root/'identity-symbols.txt').write_text('\n'.join(l for l in symbols.splitlines() if any(l.endswith(' '+s) for s in ['misc_init_r','rockchip_cpuid_from_efuse','rockchip_cpuid_set','rockchip_setup_macaddr','fdt_root','fdt_fixup_ethernet']))+'\n')
    print('Verified strong board identity hook, read-only eFuse DT node and legacy header/payload CRCs')


if __name__=='__main__':main()
