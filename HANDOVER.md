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

* 正确访问方式：`ssh r11`（Mac 上已配 ProxyJump 别名：Mac→笔记本 192.168.31.90→手机 172.16.42.1）。
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
