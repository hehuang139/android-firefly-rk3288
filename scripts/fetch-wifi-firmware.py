#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Fetch exact Wi-Fi firmware inputs; keep blobs/calibration outside source archives."""
import argparse,gzip,hashlib,json,os,subprocess,tarfile,tempfile,urllib.request
from pathlib import Path

PORT=Path(__file__).resolve().parents[1]
def sha(data):return hashlib.sha256(data).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--cache',type=Path,required=True)
 p.add_argument('--output',type=Path,default=PORT/'device/firefly/rk3288/wifi/prebuilts/firmware')
 choice=p.add_mutually_exclusive_group(required=True)
 choice.add_argument('--nvram-file',type=Path,help='Your module-specific NVRAM/calibration file; never publish it.')
 choice.add_argument('--fetch-unlicensed-nvram-template',action='store_true',help='Explicitly fetch the pinned AP6335 evaluation template; redistribution rights are not confirmed.')
 args=p.parse_args();manifest=json.loads((PORT/'device/firefly/rk3288/wifi/firmware-sources.json').read_text())
 if args.output.exists():p.error('Use a new firmware output directory; no overwrite is performed.')
 args.cache.mkdir(parents=True,exist_ok=True);fetched={};report={'files':{},'packages':manifest['packages'],'nvram':'local board calibration' if args.nvram_file else 'pinned template; redistribution rights unconfirmed'}
 def download(url,digest,limit):
  target=args.cache/digest
  if target.is_file() and sha(target.read_bytes())==digest:return target
  request=urllib.request.Request(url,headers={'User-Agent':'Firefly-RK3288-source-build/1'})
  with tempfile.NamedTemporaryFile(dir=args.cache,delete=False) as temporary:
   temp=Path(temporary.name)
   try:
    with urllib.request.urlopen(request,timeout=90) as response:
     size=0
     while True:
      data=response.read(1024*1024)
      if not data:break
      size+=len(data)
      if size>limit:raise ValueError('Download exceeds pinned size')
      temporary.write(data)
    temporary.close()
    if sha(temp.read_bytes())!=digest:raise ValueError('Downloaded SHA256 mismatch: '+url)
    os.replace(temp,target)
   finally:
    if temp.exists():temp.unlink()
  return target
 for name,package in manifest['packages'].items():fetched[name]=download(package['url'],package['sha256'],package['bytes'])
 with tempfile.TemporaryDirectory(prefix='firefly-wifi-') as directory:
  stage=Path(directory);records=[]
  licenses={
   'linux-firmware': [('usr/share/doc/linux-firmware/licenses/LICENCE.broadcom_bcm43xx.gz','licenses/LICENCE.broadcom_bcm43xx',True),('usr/share/doc/linux-firmware/licenses/LICENCE.cypress.gz','licenses/LICENCE.cypress',True),('usr/share/doc/linux-firmware/copyright','licenses/linux-firmware-copyright',False)],
   'wireless-regdb':[('usr/share/doc/wireless-regdb/copyright','licenses/wireless-regdb-copyright',False)]}
  for name,archive in fetched.items():
   tar=stage/(name+'.tar')
   with tar.open('wb') as stream:subprocess.run(['dpkg-deb','--fsys-tarfile',str(archive)],stdout=stream,check=True)
   requested=[(x['member'],x['destination'],False,x['sha256']) for x in manifest['files'] if x['package']==name]
   requested += [(a,b,c,None) for a,b,c in licenses[name]]
   with tarfile.open(tar) as package:
    members={m.name.lstrip('./'):m for m in package.getmembers()}
    for member,dest,decompress,expected in requested:
     item=members.get(member)
     if item is None or not item.isfile():raise ValueError('Expected regular package member missing: '+member)
     payload=package.extractfile(item).read()
     if decompress:payload=gzip.decompress(payload)
     if expected and sha(payload)!=expected:raise ValueError('Firmware payload hash mismatch: '+dest)
     target=stage/'output'/dest;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(payload)
     report['files'][dest]={'sha256':sha(payload),'bytes':len(payload),'source_package':name,'source_member':member}
  nvram=manifest['nvram_template']
  source=args.nvram_file if args.nvram_file else download(nvram['url'],nvram['sha256'],nvram['bytes'])
  payload=source.read_bytes()
  if not 100<=len(payload)<=65536 or b'\0' in payload:raise ValueError('Unexpected NVRAM format')
  if b'boardtype=' not in payload or b'boardrev=' not in payload:raise ValueError('NVRAM lacks board calibration metadata')
  # Preserve all RF, region and calibration values; do not invent a universal MAC.
  for chip in ['4335','4339']:
   name=f'brcm/brcmfmac{chip}-sdio.firefly,firefly-rk3288.txt';target=stage/'output'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(payload)
   report['files'][name]={'sha256':sha(payload),'bytes':len(payload),'source':'user-supplied-calibration' if args.nvram_file else 'pinned-local-evaluation-template'}
  args.output.parent.mkdir(parents=True,exist_ok=True)
  import shutil
  shutil.copytree(stage/'output',args.output)
 (args.output/'fetch-report.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({'output':str(args.output),'files':len(report['files']),'nvram':report['nvram']}))
if __name__=='__main__':main()
