# 去广告域名表

基于 AdAway 默认 hosts，作者 Kicelo、Dominik Schuermann 和 AdAway 贡献者。
来源：https://github.com/AdAway/adaway.github.io ，原文件 upstream-hosts.txt。
授权：Creative Commons Attribution 3.0，https://creativecommons.org/licenses/by/3.0/ 。
本项目修改：只选取 record.json 中记录的广告域名，将回环目标替换为 0.0.0.0，
补充系统 localhost 条目，并生成 CMFA classical rule-provider 文件。
未将整个上游过滤表直接启用。来源和输出 SHA-256 保存在 record.json。

系统通过 /system/etc/hosts 过滤这些精确域名；不需要占用 VPN 槽位。
install-port.py 对固定版本 system/core 应用 0003-rootdir-adblock-hosts.patch，
由 Android 原有的 etc_hosts 模块安装，避免两个模块生成同一个系统路径。
CMFA 可选导入 /product/etc/firefly-tv/adblock/cmfa-rules.yaml：

```yaml
rule-providers:
  firefly-adblock:
    type: file
    behavior: classical
    path: /product/etc/firefly-tv/adblock/cmfa-rules.yaml
rules:
  - RULE-SET,firefly-adblock,REJECT
  # 接现有分流规则
```

该规则可减少部分广告域名请求。与正片共用域名的贴片广告不在此表的过滤范围内。
自行实现 DNS/DoH 的应用也可能绕过系统 hosts。SmartTube 使用其自身提供的广告处理。
hosts.clean 为排查误拦截时的干净模板；本版本固件不提供动态替换系统 hosts 的开关。
