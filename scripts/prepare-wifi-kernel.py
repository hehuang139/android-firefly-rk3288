#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Export matching modules and compile the additive Wi-Fi DT without board access."""
import argparse,hashlib,json,re,shutil,struct,subprocess
from pathlib import Path
PORT=Path(__file__).resolve().parents[1]
CONFIG_SHA='96f53bfe2007da3beabcec566e16cdc3425cc065c4f043316a67b1482b5498eb'
DT_BASE_SHA='2021fedaf9241b18d8184191c24a740f05beaceac0aeffb80c41376e1c815c5b'
DT_WIFI_SHA='8a737a9b2ed1b4808837a3c739a05ed8ae62c378b5e242decb69d5394a48b7d1'
MODULES=['net/wireless/cfg80211.ko','drivers/net/wireless/broadcom/brcm80211/brcmutil/brcmutil.ko',
 'drivers/net/wireless/broadcom/brcm80211/brcmfmac/brcmfmac.ko',
 'drivers/net/wireless/broadcom/brcm80211/brcmfmac/wcc/brcmfmac-wcc.ko',
 'drivers/net/wireless/broadcom/brcm80211/brcmfmac/cyw/brcmfmac-cyw.ko',
 'drivers/net/wireless/broadcom/brcm80211/brcmfmac/bca/brcmfmac-bca.ko']
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def run(cmd):return subprocess.run(list(map(str,cmd)),check=True,capture_output=True,text=True).stdout.strip()
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--kernel-build',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args();build=args.kernel_build.resolve()
 if args.output.exists():p.error('Output exists; use a new directory')
 assert sha(build/'.config')==CONFIG_SHA,'Kernel configuration mismatch'
 release=(build/'include/config/kernel.release').read_text().strip();assert release=='6.18.60-firefly-tvbox',release
 # Module.symvers from this exact build contains core and all module exports.
 symbols={}
 for line in (build/'Module.symvers').read_text().splitlines():
  parts=line.split();symbols[parts[1]]=int(parts[0],16)
 records={}
 for relative in MODULES:
  source=build/relative;assert source.is_file(),source
  header=source.read_bytes()[:20];assert header[:6]==b'\x7fELF\x01\x01' and struct.unpack_from('<H',header,18)[0]==40
  vermagic=run(['modinfo','-F','vermagic',source]);assert vermagic.startswith(release+' '),vermagic
  imports=[]
  for line in run(['modprobe','--show-modversions',source]).splitlines():
   crc,symbol=line.split();assert symbol in symbols and int(crc,16)==symbols[symbol],symbol;imports.append(symbol)
  records[source.name]={'sha256':sha(source),'bytes':source.stat().st_size,'vermagic':vermagic,'import_crcs_checked':len(imports)}
 dtc=build/'scripts/dtc/dtc';assert dtc.is_file()
 args.output.mkdir(parents=True);(args.output/'modules').mkdir()
 base=PORT/'kernel/final/device-tree/rk3288-firefly-es8323-npll216.decompiled.dts';delta=PORT/'kernel/final/device-tree/sdio-original-board.delta.dtsi'
 candidate=args.output/'rk3288-firefly-wifi.dts';candidate.write_text(base.read_text()+delta.read_text())
 diagnostics={}
 for source,target,expected in [(base,args.output/'baseline.dtb',DT_BASE_SHA),(candidate,args.output/'rk3288-firefly-wifi.dtb',DT_WIFI_SHA)]:
  r=subprocess.run([str(dtc),'-I','dts','-O','dtb','-b','0','-o',str(target),str(source)],capture_output=True,text=True,check=True)
  assert sha(target)==expected,'DTC output differs; inspect before changing the accepted hash'
  diagnostics[target.name]=r.stderr
 for relative in MODULES:shutil.copyfile(build/relative,args.output/'modules'/Path(relative).name)
 report={'status':'OFFLINE_BUILD_CHECKS_PASSED','hardware_status':'software reboot and scan validated separately; this script performs offline checks only','kernel_release':release,'kernel_sha256':sha(build/'arch/arm/boot/zImage'),'config_sha256':CONFIG_SHA,'dtb_sha256':DT_WIFI_SHA,'modules':records,'dtc_diagnostics':diagnostics}
 (args.output/'wifi-kernel-report.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({k:v for k,v in report.items() if k!='dtc_diagnostics'}))
if __name__=='__main__':main()
