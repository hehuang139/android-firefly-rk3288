#!/usr/bin/env python3
"""Write the literal boot command without sed replacement expansion of '&'."""
# SPDX-License-Identifier: MIT
import json
from pathlib import Path
import sys

path = Path(sys.argv[1])
lines = path.read_text().splitlines()
bootcmd = 'mmc dev 0 && mmc rescan && sysboot mmc 0:1 any ${scriptaddr} /extlinux/extlinux.conf'
assert sum(line.startswith('CONFIG_BOOTCOMMAND=') for line in lines) == 1
path.write_text('\n'.join('CONFIG_BOOTCOMMAND=' + json.dumps(bootcmd)
                          if line.startswith('CONFIG_BOOTCOMMAND=') else line for line in lines) + '\n')
