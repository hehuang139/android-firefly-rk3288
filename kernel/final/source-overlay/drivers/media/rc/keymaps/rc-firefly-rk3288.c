// SPDX-License-Identifier: GPL-2.0-only
// Original Firefly 12-key remote, NEC address 0x00 (wire user code 0x00ff).
// Source: Firefly-docs/products-docs, module_ir_remote_info.png at
// 0d90ce26a859bda4912898d6ccf66d90b0869c56. Mainline rc-core uses command
// bytes, unlike the old vendor PWM table which stored inverted command bytes.
#include <linux/module.h>
#include <media/rc-map.h>

static struct rc_map_table firefly_rk3288[] = {
    { 0x0014, KEY_POWER },
    { 0x0013, KEY_MENU },
    { 0x0003, KEY_UP },
    { 0x0002, KEY_DOWN },
    { 0x000e, KEY_LEFT },
    { 0x001a, KEY_RIGHT },
    { 0x0007, KEY_OK },
    { 0x005c, KEY_SETUP },
    { 0x0048, KEY_HOME },
    { 0x0001, KEY_BACK },
    { 0x0058, KEY_VOLUMEDOWN },
    { 0x000b, KEY_VOLUMEUP },
};

static struct rc_map_list firefly_rk3288_map = {
    .map = {
        .scan = firefly_rk3288,
        .size = ARRAY_SIZE(firefly_rk3288),
        .rc_proto = RC_PROTO_NEC,
        .name = "rc-firefly-rk3288",
    }
};

static int __init init_rc_map_firefly_rk3288(void)
{
    return rc_map_register(&firefly_rk3288_map);
}

static void __exit exit_rc_map_firefly_rk3288(void)
{
    rc_map_unregister(&firefly_rk3288_map);
}

module_init(init_rc_map_firefly_rk3288);
module_exit(exit_rc_map_firefly_rk3288);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Original Firefly-RK3288 12-key IR remote map");
