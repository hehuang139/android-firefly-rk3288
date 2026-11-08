#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Keep only the module families shipped in the original RK3399 product."""
import argparse
from pathlib import Path

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('config',type=Path)
a=p.parse_args()
keep={'CONFIG_CFG80211','CONFIG_BRCMUTIL','CONFIG_BRCMFMAC'}
lines=a.config.read_text().splitlines()
removed=[]
for i,line in enumerate(lines):
 if line.endswith('=m') and line.split('=',1)[0] not in keep:
  key=line.split('=',1)[0];removed.append(key);lines[i]='# '+key+' is not set'
a.config.write_text('\n'.join(lines)+'\n')
print(f'Disabled {len(removed)} optional module selections; required board drivers stay built in')
