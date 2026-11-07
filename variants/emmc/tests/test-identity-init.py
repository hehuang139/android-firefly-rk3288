#!/usr/bin/env python3
"""Run actual patched init + upstream serial/MAC functions with read-failure injection."""
# SPDX-License-Identifier: MIT
import argparse
import binascii
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile


def function(source, name):
    match = re.search(r'int ' + re.escape(name) + r'\([^\n]*(?:\n[^\{]*)?\)\n\{.*?^\}', source, re.M | re.S)
    if not match:
        raise RuntimeError('Cannot find source function ' + name)
    return match.group(0)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--image')
    p.add_argument('--inside', action='store_true')
    args = p.parse_args()
    root = Path(__file__).resolve().parents[1]
    if not args.inside:
        subprocess.run(['docker', 'run', '--rm', '--user', str(__import__('os').getuid()) + ':' + str(__import__('os').getgid()), '-v', str(root) + ':/build', '-w', '/build', args.image or 'firefly-rk3288-uboot-builder:local', 'python3', 'tests/test-identity-init.py', '--inside'], check=True)
        return
    board = (root / 'out/source/u-boot-2024.01/board/firefly/firefly-rk3288/firefly-rk3288.c').read_text()
    misc = (root / 'out/source/u-boot-2024.01/arch/arm/mach-rockchip/misc.c').read_text()
    actual = function(misc, 'rockchip_cpuid_set').replace('int rockchip_cpuid_set(', 'int real_rockchip_cpuid_set(')
    actual += '\n' + function(misc, 'rockchip_setup_macaddr').replace('int rockchip_setup_macaddr(', 'int real_rockchip_setup_macaddr(')
    init = function(board, 'misc_init_r')
    cpuid = bytes(range(16))
    crc = lambda c, b: binascii.crc32(b, c ^ 0xffffffff) ^ 0xffffffff
    lo = crc(0, cpuid[1::2]); hi = crc(lo, cpuid[0::2])
    serial = f'{(hi << 32) | lo:016x}'
    mac = bytearray(hashlib.sha256(cpuid.hex().encode()).digest()[:6]); mac[0] = (mac[0] & 0xfe) | 2
    expected_mac = ':'.join(f'{b:02x}' for b in mac)
    prefix = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <openssl/sha.h>
typedef unsigned char u8;
typedef uint32_t u32;
typedef unsigned long long u64;
#define CONFIG_IS_ENABLED(x) 1
#define SHA256_SUM_LEN 32
#define debug(...) do {} while (0)
static char cpuid_env[33], serial_env[17], mac_env[18], mac1_env[18];
static int mode, salt, read_calls, set_calls, mac_calls, fail_serial, fail_mac;
static const char *env_get(const char *key) {
 char *p = !strcmp(key,"cpuid#") ? cpuid_env : !strcmp(key,"serial#") ? serial_env : !strcmp(key,"ethaddr") ? mac_env : mac1_env;
 return *p ? p : NULL;
}
static int env_set(const char *key, const char *value) {
 char *p = !strcmp(key,"cpuid#") ? cpuid_env : serial_env;
 strcpy(p,value); return 0;
}
static u32 crc32_no_comp(u32 crc, const u8 *p, unsigned int n) {
 while(n--) {crc ^= *p++; for(int i=0;i<8;i++) crc=(crc>>1) ^ ((0-(crc&1)) & 0xedb88320U);}
 return crc;
}
static int hash_block(const char *algo, void *data, unsigned int length, u8 *out, int *size) {
 assert(!strcmp(algo,"sha256") && *size==32); SHA256(data,length,out); return 0;
}
static int eth_env_set_enetaddr(const char *key, const u8 *m) {
 char *p = !strcmp(key,"ethaddr") ? mac_env : mac1_env;
 sprintf(p,"%02x:%02x:%02x:%02x:%02x:%02x",m[0],m[1],m[2],m[3],m[4],m[5]); return 0;
}
static int rockchip_cpuid_from_efuse(u32 off, u32 len, u8 *id) {
 assert(off==7 && len==16); read_calls++;
 if(mode==0) return -5;
 for(unsigned int i=0;i<len;i++) id[i] = mode==1 ? 0 : mode==2 ? 0xff : (u8)(i+salt);
 return 0;
}
'''
    wrappers = r'''
static int rockchip_cpuid_set(const u8 *p, u32 n) {set_calls++; return fail_serial ? -12 : real_rockchip_cpuid_set(p,n);}
static int rockchip_setup_macaddr(void) {mac_calls++; return fail_mac ? -12 : real_rockchip_setup_macaddr();}
static void reset(void) {
 memset(cpuid_env,0,sizeof(cpuid_env)); memset(serial_env,0,sizeof(serial_env));
 memset(mac_env,0,sizeof(mac_env)); memset(mac1_env,0,sizeof(mac1_env));
 read_calls=set_calls=mac_calls=fail_serial=fail_mac=salt=0;
}
'''
    test = r'''
int main(void) {
 for(mode=0;mode<3;mode++) {
  reset(); assert(misc_init_r()==0); assert(read_calls==1 && !set_calls && !mac_calls);
  assert(!*serial_env && !*mac_env);
 }
 reset(); mode=3; assert(misc_init_r()==0); assert(set_calls==1 && mac_calls==1);
 assert(!strcmp(serial_env,"SERIAL")); assert(!strcmp(mac_env,"MAC"));
 char first_serial[17], first_mac[18]; strcpy(first_serial,serial_env); strcpy(first_mac,mac_env);
 reset(); assert(misc_init_r()==0); assert(!strcmp(first_serial,serial_env) && !strcmp(first_mac,mac_env));
 reset(); salt=32; assert(misc_init_r()==0); assert(strcmp(first_serial,serial_env) && strcmp(first_mac,mac_env));
 reset(); fail_serial=1; assert(misc_init_r()==0); assert(!*serial_env && !mac_calls);
 reset(); fail_mac=1; assert(misc_init_r()==0); assert(*serial_env && !*mac_env);
 reset(); strcpy(mac_env,"02:11:22:33:44:55"); assert(misc_init_r()==0); assert(!strcmp(mac_env,"02:11:22:33:44:55"));
 puts("PASS: read error, zero/FF ID, deterministic/distinct identities, serial/MAC failure, existing MAC");
 return 0;
}
'''.replace('"SERIAL"', '"' + serial + '"').replace('"MAC"', '"' + expected_mac + '"')
    with tempfile.TemporaryDirectory() as temp:
        source = Path(temp) / 'identity.c'; binary = Path(temp) / 'identity'
        source.write_text(prefix + actual + wrappers + init + test)
        subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror', '-Wno-sign-compare', str(source), '-lcrypto', '-o', str(binary)], check=True)
        run = subprocess.run([str(binary)], check=True, text=True, capture_output=True)
        print(run.stdout, end='')
    record = {'test':'actual patched board misc_init_r + upstream rockchip_cpuid_set/rockchip_setup_macaddr with mocked read-only eFuse/environment', 'cases':8, 'result':'passed', 'fixture_cpuid':cpuid.hex(), 'expected_serial':serial, 'expected_mac':expected_mac, 'hardware_io':False}
    (root / 'records/identity-init-validation.json').write_text(json.dumps(record,indent=2)+'\n')


if __name__ == '__main__':
    main()
