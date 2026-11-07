# OPPO R11 (CPH1707) Mainline Linux & Wi-Fi Bringup 交接文档

> **更新时间**: 2026-11-07（第4轮交接·统一根因版）
> **适用机型**: OPPO R11 (`oppo16051` / `CPH1707`, 高通骁龙 SDM660)
> **内核版本**: Mainline Linux `7.0.9-sdm660+`（分支 `r11t/legacy-full-stack` + 工作区 patches/）
> **系统环境**: Arch Linux ARM aarch64（eMMC `userdata` 分区 `/dev/mmcblk1p69`，headless）
> **Wi-Fi 目标**: SSID `yyds`，密码 `goodnight`；路由器为手机绑定 IP `192.168.31.11`（按原厂 MAC）
> **本机工具**: `tools/phone_exec.py`（Mac 直连串口 `/dev/cu.usbmodemr11t_arch1`）、`tools/push_file_mac.py`（串口推文件）

---

## 0. 一句话结论（第4轮）

**所有轮次的崩溃是同一个统一根因：电池深度过放（实测 2.688V）且 USB 充电链路未工作（充电器输入 V=0/I=0），系统纯靠残血电池供电。任何射频活动（哪怕 10dBm 静默关联）都会把 VPH 拉穿固件底线 → wlan_process 约 5 秒后熄火 → RX 断流 → 约 10 秒后 MSS 看门狗咬死。**

第一轮的"36~64 秒掉电"、第三轮的"关联 11.9 秒崩"、本轮的"关联 14.6 秒崩"，全部是它在不同负载下的表现。原始交接文档的 UVLO 假说方向正确，只是当时被"headless 稳定运行"误导为已排除。

## 1. 立即行动（下一步）

1. **用原装大功率充电头给手机充电 30~60 分钟**（手机可保持开机，headless 无需屏幕）。当前 USB-Mac 供电不进充电链路，必须墙充。
2. 充完后重新接回 Mac USB，跑 `/usr/local/bin/wifi-connect`，验证关联后存活（此前必死窗口为关联后 10~16 秒）。
3. 若存活：`ssh root@<ip>`（密码 1122/123456），完成 §6 的开机自启固化。
4. **MAC 地址**（见 §5）：请在路由器后台读出绑定 `192.168.31.11` 的那台设备的 MAC（原厂 MAC），告诉我或直接写进 `/etc/modprobe.d/ath10k.conf` 的 `mac_addr=` 参数（该参数经 WLFW QMI 下发生效，已验证可用）。

## 2. 关键证据链（本轮实验，全部可复现）

### 2.1 电池实测（bq27541 计 + pm660-charger）
```
voltage_now = 2,688,000 µV (2.688V)   ← 锂电池深度过放（正常 3.4~4.2V）
current_now = -693,000 µA             ← 系统正以 693mA 从电池放电
pm660-charger usb: online=1 type=USB current_max=600mA
pm660-charger input: V=0 I=0          ← USB VBUS 在，但充电器没有在输入侧取电
pm660-charger status=Full             ← 假满电（2.688V 不可能是满电），充电被终止
```
注意：`modprobe qcom_smbx` 后 `pm660-charger` 才会出现在 power_supply（开机默认没加载）。

### 2.2 关联后 RX 断流曲线（手机端逐秒采样 /tmp/watch.log）
```
关联 t=0s   iv=88ms    ← RX 正常（信标持续到达）
t=+2s      iv=16ms
t=+4s      iv=240ms   ← RX 开始丢
t=+5s      iv=1292ms  ← RX 完全断流（inactive 纯增长 ~1s/s）
t=+10s     mss=crashed ← 看门狗咬死
```
`iv` = station dump 的 inactive time。RX 断流时内核侧零异常（无 IOMMU fault、无 memshare/RFSA 失败记录）——固件内部电压跌落熄火，AP 侧看不到任何报错。

### 2.3 已被实验排除的假说（不要再走回头路）
| 假说 | 实验 | 结论 |
| :--- | :--- | :--- |
| TX 功率过大/电气脉冲 | 10dBm 限功率 + 停 networkd + 零数据静默关联 | 仍崩，排除 |
| CX/MX proxy 投票被释放 | keep_proxy_pds 补丁（CI 构建+刷入验证） | 仍崩，假说否定，补丁已从 CI 移除 |
| Q6 memory bank 29 未供电 | bank-29 修复已在 legacy 树内，今天的模块即包含 | 仍崩，非当前根因 |
| IOMMU/SMMU fault | 崩溃窗口 dmesg 零 fault | 排除 |
| 数据量/特定报文触发 | 静默无数据也崩 | 排除 |
| 固件 ABI 缺口（RFSA/RMTFS/QRTR 系） | 关联前全链路健康（BDF/MAC/firmware ready 全过） | 非启动期问题，但关联期 ABI 缺口未被排除（电池因素干扰判断） |

### 2.4 参考发行版情报（~/Downloads/OPPO-R11T-ArchLinux-GCC-20260724，仅参考不使用）
* 其复盘文档 `OPPO_R11T_WIFI_MAINLINE_BRINGUP.md`（CPH1707-Mainline/oppo-r11-archlinux-sdm660-oppor11-t 仓库内）明说：**只验证到扫描成功，"尚未加入 wpa_supplicant 完成受控入网"**——关联期从未被任何人验证过，本节是首个实测。
* 其 DTB 的 Wi-Fi 节点与我们的**逐字段一致**（含 phandle 编号）——工作区 DTB 血统即来自该发行版。
* 其内核源 = legacy-full-stack（约 7/31 时点）+ bank-29 补丁；其 qcom_q6v5_mss.ko（recovery 镜像内可提取）srcversion 与我们不同但功能等同。
* 其文档 §16.1 也确认：**稳定 MAC 来源未解决**，随机 MAC 不能写死——印证 `00:0a:f5:89:89:ff` 是前人测试期随机地址。

## 3. 启动链现状（已稳定，可复现）

* **刷入镜像**: `/tmp/ci-art/boot-r11t-fix2.img` = CI 内核（含全部 patch）+ 工作版 DTB + **工作版 initramfs** + 完整 cmdline（`rdinit=/init panic=10 loglevel=7 consoleblank=120 rootwait rw`）。
* **⚠️ 历史教训**：CI 的 initramfs 曾被救援版 init 顶替（`rdinit=/init` 缺失 + rescue init 的 `set -eu` 一失败即 panic 循环），导致刷机后在 logo 处无限重启。**已修复**：`initramfs/init` 回写为工作版（挂载 userdata → switch_root），`build.sh` 布局对齐（`/bin/busybox` + `/newroot`），本地构建已验证与工作镜像结构一致。今后 CI 产物可直接刷。
* **Linux 内一键进 fastboot**：`python3 tools/phone_exec.py "reboot-fastboot"`（写 IMEM `0x146BF65C = 0x77665500`），实测秒进。fastboot 空闲超时无法关闭（ABL 签名），但软件重启让超时不再是问题：**探测到 fastboot → 立刻 flash** 即可。

## 4. CI 构建链（已打通）

* push 到 `main` → GitHub Actions 构建内核（应用 `patches/*.patch`）→ 编译工作区 DTB（`dts/sdm660-oppo-r11t-wifi-fixed.dts`，与在机 DTB 逐字节一致）→ 打包 boot → 产出 `qcom_q6v5_mss.ko` 单模块。
* 当前 `patches/`：`0003-remoteproc-q6v5-mss-power-sdm660-memory-bank-29.patch`（采纳上游 3750352b117a；keep_proxy_pds 实验补丁已移除）。
* 模块更新方式（无需整机重刷）：CI 产物 `qcom_q6v5_mss.ko` → `tools/push_file_mac.py` 推送到手机 → `gzip > /lib/modules/$(uname -r)/kernel/drivers/remoteproc/qcom_q6v5_mss.ko.gz`（备份旧 .ko.zst）→ `depmod -a` → `modprobe`。vermagic 一致可直接替换。

## 5. MAC 地址问题（已定位，待原厂 MAC 值）

* `ath10k_snoc` 有 `mac_addr` 参数，经 WLFW QMI 下发固件（日志 `provisioned MAC address ... through WLFW QMI`），**机制已验证可用**。
* `/etc/modprobe.d/ath10k.conf` 现被写入的 `00:0a:f5:89:89:ff` 是**前人测试期随机生成的地址**（参考发行版文档 §16.1 佐证），并非原厂 MAC——所以路由器对 `192.168.31.11` 的绑定不生效。
* 获取原厂 MAC 的途径（按优先级）：
  1. **路由器后台**：读绑定 `192.168.31.11` 的 MAC（原厂 Android 时代手机连过 Wi-Fi，绑定记录即原厂 MAC）
  2. persist 分区挖掘（`/mnt/persist/bdwlan.bin`、`bluetooth/.bt_nv.bin`，本地备份 `backup/persist.img` 可 debugfs 提取）
  3. 恢复 `modprobe.d/ath10k.conf` 时保留 `cryptmode=0`（WCN3990 firmware-5.bin 不支持 cryptmode=1）

## 6. Wi-Fi 可用后的固化清单

```bash
# 手机上执行（SSH 或串口）：
systemctl unmask r11t-wifi.service
systemctl enable wpa_supplicant-wlan0.service   # 若存在该单元
# /usr/local/bin/wifi-connect 已含：cpuidle 深度禁用 + 省电关闭 + keepalive ping
# 电池修复后这些保守措施可逐步简化
```

## 7. 其他未完成项

1. **电池/充电链路**：即使充满，USB-Mac 供电仍不会给系统充电（输入 V=0/I=0），长时间调试必须墙充或研究 pm660-charger 的 AICL/输入检测配置（`drivers/power/supply/qcom_smbx` 内核侧）。
2. bq27541 电量计数据失真（temp=-25.95°C、capacity=2639 等），修复方向：DTS 的 `ti,bq27541` 节点参数 + gauge 芯片 re-reset。
3. 关联期 ABI 缺口：若墙充后仍崩，则电池理论被证伪，回头按 §2.3 最后一行排查（对比 stock ICNSS 行为，源码在 YuxuanZuo/android_kernel_oppo_sdm660 `drivers/soc/qcom/icnss.c`，已确认其中含 VPH 电压监控参数 `ADC_MEAS1_INTERVAL_1S`——若墙充治愈，此项也佐证电压机制）。
4. 显示/图形、音频、蓝牙未回归验证。
5. 工作区遗留未提交实验产物（`test_insn.bin`、`tqftpserv_patched`、`tqftpserv_phone`）——确认无用后清理。

## 8. 复盘：本轮验证方法论

1. **逐秒曲线采样**（station dump inactive time）把"14 秒后崩"分解为"5 秒 RX 断流 → 10 秒看门狗"两个阶段——崩溃点是果不是因。
2. 单变量实验矩阵：满数据/静默 × 满功率/10dBm × 投票保持/释放，全部崩溃 → 指向公共因子（供电）。
3. 内核侧零报错 + 固件内部熄火 → 查"固件在监控什么外部条件"→ ICNSS 源码 VPH 监控 → 电池实测坐实。
4. 第三方参考（酷安/发行版/上游 patch）只在需要方向感时使用，结论一律自测。

## 9. 第4轮补遗（sxwifi 对照实验 + 电源仪表失明）

* **换 AP 对照**：sxwifi（与 yyds 完全不同的 AP/信道/密码）关联测试 → MSS 同样在关联过程中/后看门狗崩溃。**排除路由器特有信标/参数触发**。
* **电源仪表全线失明**：bq27541 的 batV 数值恒为 2688000（数小时零变化，死寄存器）；pm660-charger 的 chgV=0 在 Mac 口和笔记本口读数一致。当前内核下**没有任何可信的电源测量手段**，供电假说无法用软件证实/证伪。
* 用户确认电池有电（整机连续运行 >8h 佐证）；bq27541 读数（2.688V/-693mA/temp=-25.95°C）整体不可信，疑为 DTS 参数（sense resistor/参数表）或 gauge 芯片初始化问题。
* 无人值守测试方法论已验证：`/usr/local/bin/wifi-test2`（串口断联状态下自跑 20min 并记 `/var/log/wifi-test2.log`），脚本与 wpa 配置（sxwifi priority=100）已固化在手机。
* 待办：A) 墙充 30min 后重测关联（供电变量唯一受控实验）；B) 修复电源仪表（qcom_smbx/rradc/bq27541 读数死值排查）；C) 若 A 证伪供电说 → 对比 stock ICNSS 关联态行为（icnss.c 已取回 /tmp/icnss.c）。

## 10. 充电驱动修复（已刷入，待验证）

* **根因**：参考作者的提交 81dc0439 明确禁用 `pm660_charger` 和 `pm660_fg`（"Keep charging policy untouched"），让 PM660 充电 IC 以自主模式充电；而我们的 DTB 里 charger@1000 是 `status=okay`，主线 qcom_smbx 绑定后进入坏状态（假 Full + 输入 0/0），**主动终止了充电**。
* **修复**：DTB 中 charger@1000 → `status="disabled"`（带注释），重打包刷入 `/tmp/boot-r11t-chgfix.img`。验证：`qcom_smbx` 加载后 `/sys/class/power_supply/` 只剩 `bq27541-0`，pm660-charger 不再出现。
* **BQ27541 电量计芯片本体卡死**：读数 40 秒三次采样零变化（2.688V/-693mA/Full 恒定），且跨重启保持——芯片未做转换。stock recovery 内核下读数正常（用户实测 100%→拔线 72%），说明芯片硬件 OK、需要正确初始化或从 stock 侧复位。明日任务：i2cdump 0x55 原始寄存器诊断 + 对照 stock 驱动初始化序列。
* **用户证据**：stock recovery 内电量 100%，拔线后 72%——电池健康、充电硬件正常、范围 72~100%。

## 11. recovery 更换 + 助手任务分派

* 新 recovery（参考发行版 installer-r11t-ecm-all-write.img，ACM+ECM+RNDIS）已刷入 recovery 分区并确认 OKAY；原 TWRP 3.7.0 已备份至手机 `/root/rec-twrp.img`（64MB）。进入方式：开机组合键（`fastboot reboot recovery` 与 IMEM recovery cookie 均被 ABL 忽略，实测无效）。
* TWRP 内核实测读数正常：Battery 100%+、CPU 39°C——再次证实电池满电健康、电量计硬件无恙、仅主线驱动配置有问题。
* 助手任务已分派（交付物：assistant-reports/icnss-vs-ath10k-qmi.md 与 bq27541-frozen-gauge.md）：
  A) stock ICNSS vs 主线 ath10k_qmi 关联态差异分析（看门狗主攻线）
  B) BQ27541 冻结诊断与修复（电池读数线）

## 12. NCM 双通道部署（待手机插回数据口验证）

* 手机侧：`/usr/lib/r11t/setup-usb-acm` 已替换为 ACM+NCM 双功能版（gadget `r11t`，手机侧 IP `172.16.42.1/24`），开机自动生效。**教训：NCM 不能在运行中动态加（UDC 重绑定会杀死唯一调试通道），必须开机组合。**
* 笔记本侧：udev 规则 `/etc/udev/rules.d/99-r11t-ncm.rules` + `/usr/local/bin/r11t-ncm-up.sh`——检测到 cdc_ncm 接口自动配 `172.16.42.2/24`。手机插上后 `ssh root@172.16.42.1` 直达。
* MAC 线索：persist/bluetooth/.bt_nv.bin = `01 00 06 22 93 00 01 21 60`（候选 BT MAC `22:93:00:01:21:60`，本地管理地址；WLAN 原厂 MAC 仍以路由器 .11 绑定记录为准）。
* 重启震动：PMIC/PON 引导层行为，主线不可控，放弃。

## 13. 原厂 MAC 已确认（用户从路由器绑定读取）

`60:21:01:00:93:23`——与 persist/bt_nv.bin 的 BT 地址（`22:93:00:01:21:60`）构成
**字节序倒排 + 尾字节 +1** 的派生关系，双源交叉验证成立。待手机插回数据口后写入
`/etc/modprobe.d/ath10k.conf`（`options ath10k_snoc mac_addr=60:21:01:00:93:23`）
并重载 ath10k 验证（日志应出现 `provisioned MAC address 60:21:01:00:93:23 through WLFW QMI`）。
路由器对 192.168.31.11 的绑定届时即生效。

## 14. 精化观察：崩溃与关联无关，是 WLAN 启动后定时死亡

* sxwifi 无人值守测试（factory MAC 已生效）：`assoc_result=DISCONNECTED`（关联未完成），
  MSS 依然崩溃。综合全部时间线：**wlan_process 在 WLAN 模式使能后 ~20s 必死**，
  与关联与否、AP、功率、数据量均无关。助手任务书 A 的问题定义以此为准。
* 原厂 MAC 已生效：`provisioned MAC address 60:21:01:00:93:23 through WLFW QMI`，
  wlan0 地址正确，路由器 .11 绑定即日可用。
* 电量计补充：batV 在数小时内从 2688000 缓慢漂移至 2657000——芯片有极低频转换，
  非完全冻结；电压读数与 TWRP 的 100% 显示依然矛盾，任务书 B 继续。
* 本轮 infra：USB-NCM 双通道已通（ping 2.6ms），ssh 收尾中（rootfs 文件属主
  501:20 遗留问题导致 ssh 拒绝工作，已修 ssh_config 链，sshd_config 链待查）。

## 15. SSH over NCM 全线打通 ✅

* **Mac 本机直接直连（手机直插 Mac USB 时，推荐）**：
  直接执行 `ssh r11-usb`（已在 Mac `~/.ssh/config` 配好 IPv6 Link-Local 别名 `fe80::f811:cbff:fe8a:3475%%en12`），零延迟、免路由器、免独占串口，秒级直达 root shell。
* **跨机跳板访问（手机插在笔记本时）**：`ssh r11`（Mac 上已配 ProxyJump 别名：Mac→笔记本 192.168.31.90→手机 172.16.42.1）。
* 三个坑及修复：
  1. **Mac 不能直接测 172.16.42.1**（NCM 在笔记本上，Mac 的连接经家路由/VPN 落到陌生主机——之前"Connection closed"全是假象）。笔记本上策略路由 table 2022 也曾把 172.16.x 劫持进 tun0，已用 `ip rule add to 172.16.42.0/24 lookup main priority 100` 修正。
  2. rootfs 从 Mac 构建遗留 uid 501 属主 → ssh 拒绝运行（"Bad owner or permissions"）。已修 `/usr/lib/systemd/ssh{,_config}.d/*.conf` 属主（注意 `chown -R` 不跟符号链接，真身在 /usr/lib/systemd 下）。
  3. NetworkManager 会冲掉手动配的 NCM IP → 已建 NM 持久连接 `r11t-ncm`（enp0s20f0u5i2 静态 172.16.42.2/24）。
* TCP 数据面全程验证可用（curl 532KB 往返成功）。今后调试一律 `ssh r11`。

## 16. 夜间战报（patches 0004/0005 已构建部署，验证被卡死打断）

* **patches/0004**（rejuvenate 协商）+ **patches/0005**（bq27541 唤醒）已按助手报告实现，
  CI 构建通过（BUILD-OK），模块经 NCM scp 推送（MD5 校验一致）并安装到手机
  `/lib/modules/...`（旧模块备份 .bak）。srcversion 对比确认新模块已加载。
* **0003 bank-29 补丁已删除**——上游 legacy-full-stack 已原生包含，保留会 patch 冲突。
* **rejuvenate 协商日志未出现**：加载的新模块含补丁字符串（strings 验证 2 处），
  但 dmesg 无 "dynamic feature mask" 行。待办：干净重启后第一时间观察
  `dmesg | grep -iE "dynamic feature|rejuvenat"`——若出现成功行（prev/curr mask）
  → 协商生效，看关联存活；若出现 "fw rejuvenation requested: cause ..." → 固件错误
  路径触发但自恢复已接管（重大进展，cause 字段直接给出固件侧错误点）；若无任何
  行 → 检查 ath10k_dbg 是否被 debug_mask 覆盖（modprobe.d 是 0x200001，够用）。
* **bq27541 已见效**：安装 0005 后读数从冻结的 2657000 变为 2656000（CLR_HIB 生效，
  转换恢复）。
* **意外事件**：手机两次"卡死"（用户侧观察 + 本轮重启后 SSH 拒绝、串口僵死），
  需物理强制重启。卡死原因未知（可能与 MSS 崩溃循环叠加有关），下次会话优先排查。
* **明日剧本**（手机强制重启后）：
  1. `ssh r11 'dmesg | grep -iE "dynamic feature|rejuvenat"'` → 按 §16 第 3 点解读
  2. `/usr/local/bin/wifi-connect` → 关联 → `ping 192.168.31.1` → 存活 >60s 判定
  3. `watch -n1 cat /sys/class/power_supply/bq27541-0/voltage_now` → 读数应实时变化
  4. 若 rejuvenate 日志给出 cause → 转报告 A §四.修复 3（SSR 衔接）

## 17. rejuvenate 实测结果（0x0004 验证）+ 下一步定论

* **协商已执行**：干净重启后 dmesg 出现 `dynamic feature mask: prev 0x0 curr 0x0`——
  固件响应了 DYNAMIC_FEATURE_MASK 但**拒绝授予 FW_REJUVENATE**（curr=0，非预期 0x1）。
  结论：这台 2019 年的 OPPO 固件不给 host 开自恢复通道 → 报告 A 的"自愈路径"对本机不可用。
* **崩溃依旧**： negotiated 后 MSS 仍在 WLAN 使能后 ~20s 崩（本轮 `WLAN RT:1074`，
  PC 同 b00c56a0，错误族累计 1074/1075/1076/1078/107b）。ath10k SSR 反复自动恢复
  （state 在 crashed↔running 间循环，扫描间歇可用）。
* **已知行为模型（当前最完整版）**：崩溃仅出现在 ath10k/WLAN 使能之后；与关联、AP、
  功率、数据、cx/mx 投票、bank29、rejuvenate 协商全部无关。wlan_process 异常，
  PC 恒定，RT 码在窄区间漂移。
* **下一步（报告 A §四.修复 3，未实施）**：
  1. 实验性 VBATT 探针（ath10k_qmi 模块参数 vbatt_probe，fw_ready 后每 5s 发
     QMI_WLFW_VBATT_REQ 固定值）——若崩溃时序改变即坐实 FW 在等电压信息；
  2. SSR 衔接快速路径（rejuvenate_pending 的 del→arrive <5s 时跳过 SCM 重授）；
  3. 深挖方向：对照 stock ICNSS 的 `QMI_WLFW_WLAN_CFG`（num_vdevs/num_peers 等
     enable 配置差异）——stock icnss.c:1500+ 的 cfg 字段与 ath10k_qmi 的默认值
     逐一对照，这是唯一尚未对比的协商面。
* **基础设施均已就绪**：ssh r11（NCM 双通道）、CI 补丁流水线、模块热替换流程、
  磁盘上的 0004/0005 补丁、电量计唤醒已生效。

## 18. 本轮新增修复与验证

* **ramoops 已刷入**（DTB ramoops@b0000000 4MB，注册成功 `pstore: Registered ramoops as persistent store backend`）——下次卡死/崩溃后 /sys/fs/pstore/console-ramoops-1 可读上次内核日志。
* **蓝牙进展**：hci_uart 链路通（hci0 注册成功）；预配工具 bt-hci-test 已从参考源码
  （initramfs/bt-hci-test.c）交叉编译部署（src-cache/bt/bt-hci-test.c）。当前卡点：
  MGMT SET_POWERED status=0x03（控制器未就绪）——下一步查 qca 固件下载/rampatch
  与 WCN 芯片 BT 电源链路。
* 音频：r11t-audio.service 存在，验证待做（需播放工具）。

## 19. 全修复终验轮（夜间第二轮）

* 干净重启 → MSS 正常拉起 → 新 ath10k_snoc（0004）加载 → `dynamic feature mask` 协商
  成功执行（curr=0x0）→ 原厂 MAC 预配 ✓ → 但 wlan_process 仍崩（scan -108 洪流）。
  **rejuvenate 路线正式关闭**（固件拒绝授予），进入任务书 C（wlan_cfg 对照 + VBATT
  探针 + SSR 快速路径）。
* 基础设施验证完毕：ssh r11 全程稳定（本次会话主力通道）；ALSA 声卡注册
  （R11T sdm660-internal）；ADSP 可拉起（remoteproc1）；remoteproc 编号会漂移
  （模块重载后 0/1/2 顺序变化，用 name 字段区分，勿写死编号）。
* MSS 恢复流程要点：crashed 状态直接 echo start 会 -EINVAL；先 rmmod
  qcom_q6v5_mss → modprobe（编号漂移！）→ 按 name 找 4080000 → echo start。

## 20. 任务书 C 实验回收（夜间第三轮）

* **C1（wlan_cfg 对照）**：干净的阴性结果——stock 与主线的 QMI_WLFW_WLAN_CFG
  载荷逐字段一致（CE 表 12 条、svc 映射、shadow reg 全同）。协商面正式排除。
* **C2（VBATT 探针）**：已实施（patches/0006，ath10k_snoc.vbatt_probe=1，每 5s 发
  3.7V）。实测：固件正常接受 VBATT 消息但崩溃照旧（23→31 波动）——**电压变量排除**。
* **C3（SSR 快速路径）**：第 1 层（msa-fixed-perm DT）已刷入；第 2/3 层补丁
  （SSR 保留 BDF + watchdog 兜底）见 c3-ssr-fastpath-patch.md，待实施。
* **剩余唯一未探区**：ath10k ce.c 运行层（中断/轮询/CE 策略）与 stock HIF 的差异。
  任务书 D 候选。当前 ath10k 的 SSR 循环让系统保持"半可用"（扫描间歇成功，
  MSS running），但 wlan_process 每 ~20s 死亡使稳定 Wi-Fi 仍不可用。
* 模块状态：/lib/modules 中已是 0006 版（含 rejuvenate+vbatt），重启后自动加载。

## 21. OTG + USB 有线网络路线（已构建，待部署验证）

* 动机：Wi-Fi 看门狗未除期间，给手机一条**完全不经过 WLAN 的网络路径**（装包/调试/上网）。
* 内核配置盘点：USB_OTG=y、xHCI/EHCI=y、DWC3 双角色 + 上游已有
  "dwc3: add R11T host VBUS support"（VBUS 供电处理过）；驱动缺口
  （AX88179/AX8817X/CDCETHER 等）已补进 configs/r11-extra.config，CI 构建通过。
* 部署步骤（手机插回笔记本后）：
  1. 从 modules.tar.xz 提取 usbnet/rtl8152/ax88179_178a/cdc_ether 等 .ko.zst
     → NCM scp → 安装 /lib/modules；
  2. 用户侧：micro-USB OTG 线 + USB 网卡 + 网线插上（需注意 VBUS 供电能力）；
  3. 验证：`lsusb`（手机侧主机枚举）、新 netdev、DHCP。
* 未知项：OTG 角色/ID 引脚切换是否在运行中自动生效（可能需要重启或手动 role
  switch）；转接器芯片型号决定走哪个驱动。

## 22. OTG 有线网络实测结论

* 手机侧全就绪（usbnet/sr9800/dm9601/cdc_ether/ax88179_178a 模块已装、networkd
  DHCP 配置好、dwc3 host VBUS 支持）。用户实测 Type-C 网卡 HLY-61 + C转micro
  转接头 → **无任何角色切换事件**（dmesg history 642 行无 otg/role/vbus 记录）。
* 根因：micro-USB OTG 依赖 ID 引脚接地，Type-C 设备经转接头无法产生该信号
  （CC 协商不映射到 ID）。需**原生 micro-USB OTG 线（micro-B 公→USB-A 母）**
  + USB-A 网卡，或原生 micro-USB 网卡。驱动与配置无需任何改动，换线即测。

## 23. 电池与充电：现状、数据与剩余工作（充电期间必读）

### 现在的充电机制（已生效）
* DT 已禁用 `pm660_charger`（照参考方案）——PM660 充电 IC 处于**自主模式**：
  硬件默认参数自动充电，与系统/数据完全无关，**插上墙充直接充，无需配置**。
* 墙充（DCP）会以硬件默认限流充电；USB 数据口场景之前实测不充电（输入 0），
  属驱动未接管的正常表现。

### 电量计（BQ27541）当前数据与判读
* 0005 补丁（CLR_HIB 唤醒）已生效：读数从**永久冻结**恢复为**缓慢变化**
  （观测 2688→2657→2656 mV 漂移）。
* **读数矛盾待解**：主线读到 ~2.66V + "-693mA 放电"，而 TWRP/stock 显示 100%、
  用户确认满电。两种可能：(a) 芯片内部转换仍不正常（休眠苏醒不彻底/需重新
  初始化），(b) 寄存器读数本身有偏差（如 sense resistor/单位换算）。
* **充电验证方法（墙充插着 + 数据线连 Mac 时）**：
  ```
  ssh r11 'watch -n5 cat /sys/class/power_supply/bq27541-0/voltage_now'
  # 充电中：电压应缓慢爬升（3.7→4.2V 区间），current_now 转为正值
  # 若电压一路走到 4.2V+ 且稳定 → 充电确认；卡在 2.6V 不动 → 见下
  ```
* **若电压始终 2.6V 级不爬升**：芯片转换仍异常 → 跑助手报告 B §三的诊断脚本
  （i2c-tools 逐寄存器 dump + CLR_HIB/SET_HIB 对照实验），并对照 stock 的
  oppo_bq27541.c 初始化序列补全（源码缓存 src-cache/bq27541/）。

### 电池线剩余工作清单
1. **poll_interval 持久化**：`/etc/modprobe.d/bq27xxx.conf` 写入
   `options bq27xxx_battery poll_interval=5`（当前只在一次 modprobe 时试过，
   未持久化——重启后回到 360s 默认）。
2. **充电全链路验证**（墙充 + 读数，见上）。
3. **报告 B §三诊断脚本**跑一遍，确定芯片是否仍处于异常转换状态。
4. **充电安全确认**：自主模式默认限流/截止参数是否合适（读
   `/sys/class/power_supply/` 下 IC 节点或对照 stock DT 的充电参数；
   参考 CPH1707 树 "conservative R11T charging limits" 提交的意图）。
5. **不做的事**：VBATT 上报给 FW（C2 实验阴性，stock 也不做，无需求）。

### 与 Wi-Fi 看门狗的关系
* 已彻底排除供电/电压因素（C2 阴性实验：FW 收到 3.7V 探针值后崩溃模式不变；
  且用户确认电池满电、TWRP 显示 100%）。Wi-Fi 崩溃与电池无关，走任务书 D
  （ce.c 运行层对照）路线。

---

## 24. USB 网络代理网桥（常驻守护进程与免密联网手册）

### 背景与解决的痛点
在 Wi-Fi 暂未常驻期间，手机必须依赖 Type-C 数据线从 Mac 共享网络进行包管理（`pacman`）、代码拉取（`git`）与工具下载（`curl`）。
* **旧方案局限**：原先使用 SSH 动态端口转发（`-R 7890`），只要断开 SSH，或者在**串口控制台（`/dev/cu.usbmodem*`）**操作，手机端代理即刻失效，报错 `Could not connect to server`。
* **现行架构（全场景通用）**：
  1. **Mac 端守护进程**：工作区提供专用异步代理桥 [`scripts/usb_proxy_bridge.py`](scripts/usb_proxy_bridge.py)，在 Mac 上常驻监听 `0.0.0.0:8080`，把来自 USB NCM 网卡（`en12`，网段 `172.16.42.0/24`）的所有 HTTP/HTTPS/SOCKS 流量透明转发给 Mac 本地代理（`127.0.0.1:7890`）。
  2. **手机端自适应配置**：手机端 `/etc/profile.d/proxy.sh` 脚本在每次登录时自动探测宿主机 IP（当前动态分配为 `172.16.42.6`），自动导出 `http_proxy`、`https_proxy`、`all_proxy` 指向 `http://${HOST_IP}:8080`。
  3. **效果**：无论在 Mac 的 `ssh r11-usb` 会话中，还是在物理串口控制台（`/dev/cu.usbmodem*`）中，联网工具（`curl`、`pacman` 等）全部开箱即用，不再受 SSH 连线状态制约。

### 运维与恢复指令（后续接手必读）

若后续接手人员重启了 Mac、切换了开发机，或手机端 `curl` 提示无法连接代理，按如下步骤一键恢复：

1. **Mac 端启动/检查代理桥（后台常驻）**：
   ```bash
   cd /Users/tangshui/test/oppo-r11-mainline-workspace
   # 检查是否已在运行：
   ps aux | grep usb_proxy_bridge.py
   # 若未运行，后台常驻启动：
   nohup python3 scripts/usb_proxy_bridge.py > /tmp/usb_proxy_bridge.log 2>&1 &
   ```
   *验证*：`lsof -i :8080` 应显示 python3 正在监听。
2. **手机端验证连通性**：
   ```bash
   # 串口控制台或 SSH 中均可执行：
   source /etc/profile.d/proxy.sh
   curl -I https://www.google.com   # 应秒回 HTTP/2 200
   pacman -Sy                       # 应正常更新 core/extra 数据库
   ```

---

# 附：全项目剩余工作总清单（按优先级）

## P0 — Wi-Fi 稳定（唯一硬骨头）
1. **任务书 D 产出落地**：`assistant-reports/ce-runtime-diff.md` 已交付；草稿补丁已正式重写为标准 unified diff 补丁 `patches/0007-ath10k-ce-error-interrupt-parity.patch` 与 `0008-ath10k-ce-misc-diagnostic-snapshot.patch`，通过本地 `git apply --check` 语法与上下文双重校验，杜绝 CI 崩溃。
2. 触发 CI 构建或热更新模块 → 验证 CE 错误中断使能后是否捕获具体错误位或消除 ~20s 崩溃。
3. 并行兜底：C3 第 2 层补丁（SSR 保留 BDF/权限）草案在 `assistant-reports/c3-ssr-fastpath-patch.md`。

## P1 — 电池/充电（见 §23）
1. ✅ **poll_interval=5 已持久化**：已写入真机 `/etc/modprobe.d/bq27xxx.conf`，重载验证 `poll_interval=5` 生效，电量计读数每 5 秒刷新。
2. 墙充充电全链路验证（电压爬升观察，实测 1865mV -> 1878mV 动态增长中）。
3. 报告 B §三诊断脚本（i2c 寄存器 dump）。
4. 充电安全参数复核。

## P2 — 蓝牙（✅ 全栈打通）
1. ✅ **内核层与固件下载全部就绪**：QCA UART 握手成功，固件 `crbtfw21.tlv` 与 `crnv21.bin` 均下载完毕，控制器 `hci0` 初始化完成。
2. ✅ **BlueZ 用户态服务已激活并自启**：通过 USB 代理安装 `bluez` 和 `bluez-utils`，`bluetooth.service` 正常运行并开机自启。`bluetoothctl show` 识别到控制器 `60:21:01:00:93:22 (QCA)`，`Powered: yes`，支持 Central / Peripheral 角色。

## P3 — 音频（✅ 全栈打通，放音验证完成）
1. ✅ **ALSA 声卡注册已彻底攻克**：`qcom_q6v5_pas` 模块加载唤醒 ADSP，已持久化到真机 `/etc/modules-load.d/adsp.conf`。声卡 `0 [R11T]: sdm660-internal - OPPO R11T` 具备双 PCM 回放设备。
2. ✅ **用户态工具与混音器路由就绪**：安装 `alsa-utils`，将 `SEC_MI2S_RX Audio Mixer MultiMedia1`（连接 NXP TFA9890 Smart PA 功放）开启。
3. ✅ **放音实测与状态固化**：`speaker-test -D hw:0,0 -c 2 -r 48000 -t sine -f 440` 成功通过 Hexagon DSP AFE 播放，无任何内核错误。混音器状态已通过 `alsactl store` 保存至 `/var/lib/alsa/asound.state`。

## P4 — 待外部条件
1. 原生 micro-USB OTG 线到货 → 有线网络即插即用（驱动已装好）。
2. 任务 C 报告确认后：UP 主线社区共享成果（rejuvenate 补丁值得上游化）。

## P5 — 卡死悬案
1. ramoops + /var/log/dmesg-history.log 双保险已就位，下次卡死自动留证。
2. 注意：长按电源强制重启=冷断电，ramoops 会丢；dmesg-history 在 eMMC 不丢。

## 基建资产（已稳定，可复用）
`ssh r11-usb`（NCM 双通道/直连）｜USB 代理桥常驻服务（`scripts/usb_proxy_bridge.py`）｜
CI 补丁流水线｜push_file 模块热替换｜reboot-fastboot｜参考版 recovery（组合键进）｜
全分区原厂备份｜dmesg 磁盘记录器｜ramoops。
