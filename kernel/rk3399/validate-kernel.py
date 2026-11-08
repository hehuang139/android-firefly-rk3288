#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Validate the built ARM64 candidate; this is not a hardware boot test."""
import argparse,hashlib,json,subprocess,struct
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--config-only',action='store_true');p.add_argument('build_root',type=Path);a=p.parse_args()
root=a.build_root.resolve();build=root/'build';config=(build/'.config').read_text();required={
'ARM64':'y','ARM64_4K_PAGES':'y','COMPAT':'y','ARCH_ROCKCHIP':'y',
'ANDROID_BINDER_IPC':'y','ANDROID_BINDERFS':'y','MEMFD_CREATE':'y','SECCOMP':'y','SECURITY_SELINUX':'y',
'BPF_SYSCALL':'y','BPF_JIT':'y','CGROUP_BPF':'y','IP_NF_FILTER':'y','IP6_NF_FILTER':'y',
'DRM_ROCKCHIP':'y','DRM_PANFROST':'y','VIDEO_ROCKCHIP_VDEC':'y','VIDEO_HANTRO':'y',
'SND_SOC_RT5640':'y','SND_SOC_ROCKCHIP_I2S':'y','SND_SIMPLE_CARD':'y','SND_SOC_HDMI_CODEC':'y',
'TYPEC_FUSB302':'y','DWMAC_ROCKCHIP':'y','ROCKCHIP_THERMAL':'y','REGULATOR_FAN53555':'y',
'RFKILL':'y','IR_GPIO_CIR':'y','IR_NEC_DECODER':'y','IR_RC6_DECODER':'y','ROCKCHIP_SARADC':'y',
'I2C_RK3X':'y','PINCTRL_ROCKCHIP':'y','GPIO_ROCKCHIP':'y','LEDS_GPIO':'y',
'MFD_RK8XX_I2C':'y','REGULATOR_RK808':'y','REGULATOR_FIXED_VOLTAGE':'y','REGULATOR_PWM':'y','COMMON_CLK_RK808':'y',
'ROCKCHIP_PM_DOMAINS':'y','ROCKCHIP_IODOMAIN':'y','NVMEM_ROCKCHIP_EFUSE':'y','PWM_ROCKCHIP':'y',
'PHY_ROCKCHIP_INNO_USB2':'y','PHY_ROCKCHIP_TYPEC':'y','TYPEC_TCPM':'y','USB_ROLE_SWITCH':'y',
'USB_DWC3_OF_SIMPLE':'y','USB_XHCI_PLATFORM':'y','USB_EHCI_HCD':'y','USB_OHCI_HCD':'y','USB_HID':'y',
'MMC_DW_ROCKCHIP':'y','PWRSEQ_SIMPLE':'y','MMC_SDHCI_OF_ARASAN':'y','PHY_ROCKCHIP_EMMC':'y',
'ROCKCHIP_IOMMU':'y','ROCKCHIP_VOP':'y','ROCKCHIP_DW_HDMI':'y','SND_SOC_RL6231':'y','SND_SOC_ROCKCHIP_SPDIF':'y','SND_SOC_SPDIF':'y',
'STMMAC_PLATFORM':'y','REALTEK_PHY':'y','PCIE_ROCKCHIP_HOST':'y','PHY_ROCKCHIP_PCIE':'y','BACKLIGHT_PWM':'y','INV_MPU6050_I2C':'y',
'SERIAL_8250_DW':'y','SERIAL_8250_CONSOLE':'y','INPUT_EVDEV':'y','HID_GENERIC':'y','DEVTMPFS':'y',
'BACKLIGHT_CLASS_DEVICE':'y',
'USB_DWC3':'y','USB_DWC3_DUAL_ROLE':'y','USB_CONFIGFS_F_FS':'y','EXT4_FS':'y',
'CFG80211':'m','BRCMFMAC':'m','BRCMFMAC_SDIO':'y','MODVERSIONS':'y',
'LOCALVERSION':'"-firefly-rk3399-android17"'}
for key,value in required.items():assert f'CONFIG_{key}={value}' in config.splitlines(),key
module_selections={line.split('=',1)[0] for line in config.splitlines() if line.endswith('=m')}
assert module_selections=={'CONFIG_CFG80211','CONFIG_BRCMUTIL','CONFIG_BRCMFMAC'},module_selections
assert '# CONFIG_ARM64_64K_PAGES is not set' in config
print('Required ARM64 Android / board configuration passed')
if a.config_only:raise SystemExit(0)
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
run=lambda cmd:subprocess.check_output(list(map(str,cmd)),text=True).strip()
def elf_sections(data):
 off=struct.unpack_from('<Q',data,40)[0];size,count,strings=struct.unpack_from('<HHH',data,58)
 table=[struct.unpack_from('<IIQQQQIIQQ',data,off+i*size) for i in range(count)]
 shstr=table[strings];names=data[shstr[4]:shstr[4]+shstr[5]]
 return {names[s[0]:].split(b'\0',1)[0].decode():data[s[4]:s[4]+s[5]] for s in table}
dtb=build/'arch/arm64/boot/dts/rockchip/rk3399-firefly-android.dtb'
dtchecks={('/','compatible'):'firefly,firefly-rk3399 rockchip,rk3399',('/rt5640-sound','simple-audio-card,name'):'FireflyRT5640',('/rt5640-sound','simple-audio-card,pin-switches'):'Headphone Jack',('/hdmi-sound','simple-audio-card,name'):'FireflyHDMI',('/hdmi-sound','status'):'okay',('/aliases','mmc2'):'/mmc@fe330000'}
for (node,prop),value in dtchecks.items():assert run(['fdtget',dtb,node,prop])==value,(node,prop)
connector='/i2c@ff3d0000/typec-portc@22/connector'
assert run(['fdtget',dtb,connector,'data-role'])=='device'
assert run(['fdtget',dtb,connector,'power-role'])=='dual'
assert run(['fdtget',dtb,connector,'try-power-role'])=='sink'
usb='/usb@fe800000/usb@fe800000'
for prop,value in [('dr_mode','peripheral'),('maximum-speed','high-speed'),('phy-names','usb2-phy')]:
 assert run(['fdtget',dtb,usb,prop])==value,prop
assert run(['fdtget','-t','x',dtb,usb,'phys'])==run(['fdtget','-t','x',dtb,'/syscon@ff770000/usb2phy@e450/otg-port','phandle'])
image=build/'arch/arm64/boot/Image';data=image.read_bytes();assert data[56:60]==b'ARM\x64'
text_offset,image_size,image_flags=struct.unpack_from('<QQQ',data,8)
assert image_size>=len(data) and image_size>0
assert text_offset==0 and image_flags & 8
release=(build/'include/config/kernel.release').read_text().strip();assert release=='6.18.60-firefly-rk3399-android17'
modules={};symbols={s.split()[1]:int(s.split()[0],16) for s in (build/'Module.symvers').read_text().splitlines()}
for folder in ['net/wireless','drivers/net/wireless/broadcom/brcm80211']:
 for source in (build/folder).rglob('*.ko'):
  raw=source.read_bytes();h=raw[:20];assert h[:6]==b'\x7fELF\x02\x01' and struct.unpack_from('<H',h,18)[0]==183
  sections=elf_sections(raw);vermagic=next(x[len(b'vermagic='):].decode() for x in sections['.modinfo'].split(b'\0') if x.startswith(b'vermagic='));assert vermagic.startswith(release+' ')
  count=0
  versions=sections['__versions'];assert len(versions)%64==0
  for offset in range(0,len(versions),64):
   crc=struct.unpack_from('<Q',versions,offset)[0];sym=versions[offset+8:offset+64].split(b'\0',1)[0].decode();assert crc==symbols[sym],sym;count+=1
  dependencies=next((x[len(b'depends='):].decode().split(',') for x in sections['.modinfo'].split(b'\0') if x.startswith(b'depends=')),[])
  modules[source.name]={'path':str(source.relative_to(root)),'sha256':sha(source),'bytes':source.stat().st_size,'vermagic':vermagic,'import_crc_count':count,'depends':[x for x in dependencies if x]}
assert set(modules)=={'cfg80211.ko','brcmutil.ko','brcmfmac.ko','brcmfmac-wcc.ko','brcmfmac-cyw.ko','brcmfmac-bca.ko'}
available={Path(x).stem.replace('-','_') for x in (build/'modules.builtin').read_text().splitlines()}|{Path(x).stem.replace('-','_') for x in modules}
for module in modules.values():
 for dependency in module['depends']:assert dependency.replace('-','_') in available,dependency
report={'status':'OFFLINE_BUILD_VALIDATED_NOT_BOOTED','kernel':'6.18.60','release':release,'upstream_patches_applied':False,'config_sha256':sha(build/'.config'),'image_sha256':sha(image),'image_bytes':image.stat().st_size,'dtb_sha256':sha(dtb),'dtb_bytes':dtb.stat().st_size,'modules':modules,'sound_card_ids':['FireflyRT5640','FireflyHDMI'],'codec_scope':'mainline rkvdec H264 and VP9; no HEVC; no hardware playback validation'}
report['arm64_image_header']={'text_offset':text_offset,'image_size':image_size,'flags':image_flags,'memory_window_bytes':max(image_size,len(data))}
report['usb_c_data_role']='device'
report['usb_c_profile']='USB2 high-speed peripheral; u2phy0_otg only; enumeration not yet tested'
report['upstream_board_dts_sha256']=sha(root/'linux-6.18.60/arch/arm64/boot/dts/rockchip/rk3399-firefly.dts')
report['candidate_dts_sha256']=sha(root/'linux-6.18.60/arch/arm64/boot/dts/rockchip/rk3399-firefly-android.dts')
report['compiler']=run(['aarch64-linux-gnu-gcc','-dumpfullversion'])
(root/'kernel-manifest.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
