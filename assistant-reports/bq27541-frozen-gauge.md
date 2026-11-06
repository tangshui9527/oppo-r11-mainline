# 任务 B：BQ27541 电量计读数冻结——诊断与修复

设备：OPPO R11，主线 Linux，`/sys/class/power_supply/bq27541-0`（voltage_now=2688000µV, current_now=-693000µA, status="Full"，多次采样零变化，跨重启保持）。
对照组：TWRP（下游内核）/ stock recovery 下同一芯片读数正常且实时。
DT：`blsp_i2c2` 下 `fuel-gauge@55`，`compatible = "ti,bq27541"`，驱动 = mainline bq27xxx + bq27xxx_battery_i2c，i2c 通信正常（能读寄存器，只是值不变）。

源码缓存：`~/test/oppo-r11-mainline-workspace/src-cache/bq27541/`（`mainline/`、`cph1707/`、`stock-oppo/`、`stock-dts/`）。

---

## 一、根因结论（一句话）

**芯片卡在 HIBERNATE（休眠）模式，ADC 转换已停止**：休眠时寄存器保持最后一次转换的快照值，i2c 读仍正常——完全匹配"读得出但不变"。主线 bq27xxx 驱动对 bq27541 **从头到尾不写任何 Control() 子命令**（无法唤醒休眠），而 stock 的 OPPO 私有驱动 probe 时会写一串 Control 子命令（含 `ENABLE_IT 0x0021` 等），把芯片唤醒——完全匹配"TWRP/stock recovery 正常"。休眠状态由电池直接供电的芯片保持，host 重启不影响——匹配"跨重启保持"。

## 二、证据（源码逐条）

| 对比项 | stock（TWRP/下游内核） | 主线 bq27xxx | 证据位置 | 证实/推测 |
|---|---|---|---|---|
| 使用的驱动 | OPPO 私有 `oppo,bq27541-battery`（**不是** bq27xxx） | mainline bq27xxx（CPH1707 树与 torvalds master md5 一致：5a05c07… / 7bb25a5…） | stock dtsi `sdm660-mtp-18321.dtsi:469-474`；color597/android_kernel_oppo_sdm660-9 `drivers/power/oppo/gauge_ic/oppo_bq27541.c` | 证实 |
| probe 时 Control 写 | `bq27541_hw_config()` 连发 CNTL_STATUS(0x0000)/DEVICE_TYPE(0x0001)/FW_VER(0x0002)/**ENABLE_IT(0x0021)** | **零次**（bq27541 条目 `BQ27XXX_DATA(bq27541, 0, BQ27XXX_O_OTDC)`，unseal key=0，无 CFGUP） | oppo_bq27541.c:685-733；mainline bq27xxx_battery.c:1043 | 证实 |
| HIBERNATE 相关命令 | 头文件定义 `SET_HIB=0x0011`、**`CLR_HIB=0x0012`**、`SET_SLP=0x0013`、`CLR_SLP=0x0014`、`RESET=0x0041`（说明该芯片休眠由 host Control 写控制，且 OPPO 工程师知道这些入口） | 全文件 `grep -ci hibernate` = **0**（battery.c 与 i2c.c 均无任何休眠处理） | oppo_bq27541.h:79-90；mainline 两个文件 | 证实 |
| 轮询频率 | oppo_gauge workqueue 秒级高频轮询 + `bq27541_pm_resume` 每次唤醒后立即读 | `poll_interval` 默认 **360 秒**（6 分钟！） | oppo_gauge.c（同仓库）；mainline bq27xxx_battery.c:1141 `static unsigned int poll_interval = 360;` | 证实 |
| 寄存器地址表 | VOLT=0x08, TEMP=0x06, FLAGS=0x0A, AI=0x14, SOC=0x2C | 完全相同（0x08/0x06/0x0A/0x14/0x2C） | oppo_bq27541.h:26-51；mainline bq27xxx_battery.c:392-410 | 证实（**排除寄存器映射错配**） |
| 读休眠芯片的行为 | — | i2c 读返回快照值（芯片手册行为，休眠仅停转换不停 i2c 接口） | 机制性知识 | 证实（机制）/ 冻结值=快照为强推测 |

**为何进入休眠**：bq27541 在满足条件（充电完成/低电流持续超过休眠定时）且 host 无唤醒写时自动进入 HIBERNATE。主线默认 360s 才轮询一次、且轮询只做读（休眠唤醒靠"电流/电压越限或 host 写 Control"，**读寄存器不唤醒**），一旦进入就永远出不来。stock 侧高频轮询 + probe 时的 Control 写序列天然防休眠。
（"何时何因首次进入"无法从源码确定——可能在 stock Android 关机静置/充满后进入，主线开机即读到冻结值；标注为推测。）

**冻结值旁证**：2688000µV=2.688V、-693000µA、temp≈-25.95°C——是一组与真实电池状态不自洽的快照（2.688V 接近 bq27541 低压域、温度明显异常），更像复位后/休眠前的脏快照，反证"芯片内部转换引擎停摆"。status="Full" 来自 Flags 的 FC 位（mainline bq27xxx_battery.c:66 `BQ27XXX_FLAG_FC=BIT(9)`，:1852、:1902-1903），也是快照。

## 三、(a) 设备端诊断脚本（可直接粘贴到手机串口）

前置：需要 root shell + i2c-tools（主线 rootfs 若无，`opkg/apt install i2c-tools` 或 busybox i2cget/i2cset）。**先在 sysfs 停止驱动轮询争用**（可选）：`echo bq27xxx_battery > /sys/bus/i2c/devices/*/driver/unbind` 更干净，但脚本不 unbind 也能跑（读写互不冲突概率高）。

```sh
#!/bin/sh
# 1. 找到 0x55 所在的 i2c 总线（blsp_i2c2）
i2cdetect -l
# 在输出里逐个试，找到含 55 的那个（假设是 N，下文替换）：
for b in 0 1 2 3 4 5 6 7 8 9 10 11 12; do
  i2cdetect -y $b 2>/dev/null | grep -q -- "55" && echo "FOUND bus $b" && N=$b && break
done
echo "bus=$N"

# 2. 连续读 Voltage(0x08)，间隔 2s —— 若两次相同且 sysfs 也冻结 → 转换停摆确认
i2cget -y $N 0x55 0x08 w; sleep 2; i2cget -y $N 0x55 0x08 w; sleep 2; i2cget -y $N 0x55 0x08 w

# 3. 读 Flags(0x0A)、Temperature(0x06)、AverageCurrent(0x14)、SOC(0x2C)
i2cget -y $N 0x55 0x0a w
i2cget -y $N 0x55 0x06 w
i2cget -y $N 0x55 0x14 w
i2cget -y $N 0x55 0x2c w

# 4. Control 子命令探测：读 CONTROL_STATUS（写 0x0000 再读 0x00/0x01）
i2cset -y $N 0x55 0x00 0x00 0x00 w
i2cget -y $N 0x55 0x00 w
# DEVICE_TYPE 应返回 0x0541（LSB=0x41）
i2cset -y $N 0x55 0x00 0x01 0x00 w
i2cget -y $N 0x55 0x00 w

# 5. ★ 关键实验：CLR_HIBERNATE（Control 写 0x0012，LSB 先行）
i2cset -y $N 0x55 0x00 0x12 0x00 w
sleep 1
# 6. 再连读 Voltage —— 若开始变化（且随时间/充电状态改变）→ 休眠冻结根因坐实
i2cget -y $N 0x55 0x08 w; sleep 2; i2cget -y $N 0x55 0x08 w; sleep 2; i2cget -y $N 0x55 0x08 w
# 7. 再读 Flags/SOC 对比第 3 步
i2cget -y $N 0x55 0x0a w
i2cget -y $N 0x55 0x2c w

# 8. 对照：SET_HIBERNATE(0x0011) 复现冻结（确认因果，做完再 CLR 一次恢复）
i2cset -y $N 0x55 0x00 0x11 0x00 w
sleep 1
i2cget -y $N 0x55 0x08 w; sleep 2; i2cget -y $N 0x55 0x08 w
i2cset -y $N 0x55 0x00 0x12 0x00 w   # 恢复
```

**结果解读**：

| 观测 | 含义 |
|---|---|
| 第 2 步三次相同 + 第 6 步开始变化 | 芯片在 HIBERNATE，主报告根因成立 |
| 第 4 步 DEVICE_TYPE ≠ 0x0541 | 芯片不是 bq27541（可能是 bq27411，stock 驱动也处理 27411，改用其命令集） |
| 第 5 步后电压仍冻结 | 休眠假说动摇 → 芯片可能 SEALED 后异常/转换引擎挂死，下一步：Control(RESET 0x0041) 试探（会清学习状态，先记录 Flags），或对照 TWRP 下 dump |
| i2cget 全部报错 | 总线/地址问题（不在本故障范畴） |

注意：`i2cget w` 打印的是 16-bit 小端 word 的 host 解释，bq27541 word 值 = 打印值直接按 LSB=低字节读；Voltage 单位 mV，Current 单位 mA（有符号，补码），Temperature 单位 0.1K。

## 四、(b) 修复补丁草案

方案：给 bq27xxx 增加"带 HIBERNATE 的芯片族，probe 与每轮 update 前发 Control(CLR_HIB)"。对不支持该子命令的芯片零影响（bit 门控）。同时把冻结检测做进 update：读到的值与上轮完全一致且芯片休眠标志可判定时，先唤醒再读（简化版：每轮都先发唤醒写，i2c 成本 ~2 字节，可忽略）。

```diff
--- a/drivers/power/supply/bq27xxx_battery.c
+++ b/drivers/power/supply/bq27xxx_battery.c
@@
-#define BQ27XXX_O_UTOT		BIT(2) /* has OT overtemperature flag */
+#define BQ27XXX_O_UTOT		BIT(2) /* has OT overtemperature flag */
 #define BQ27XXX_O_CFGUP		BIT(3)
 #define BQ27XXX_O_RAM		BIT(4)
+/* BIT(5) reserved upstream; allocate locally */
+#define BQ27XXX_O_HIB		BIT(5) /* enters HIBERNATE; needs host CLR_HIB wake */
 #define BQ27XXX_O_SOC_SI	BIT(6) /* SoC is single register */
@@
-	[BQ27541]   = BQ27XXX_DATA(bq27541,   0         , BQ27XXX_O_OTDC),
+	[BQ27541]   = BQ27XXX_DATA(bq27541,   0         , BQ27XXX_O_OTDC | BQ27XXX_O_HIB),
```
（同族 BQ27542/BQ27546/BQ27742 若实测同样休眠，同样加 bit；先只动 27541 保守验证。）

```diff
@@ bq27xxx_battery_update_unlocked()
 static void bq27xxx_battery_update_unlocked(struct bq27xxx_device_info *di)
 {
 	union power_supply_propval status = di->last_status;
 	struct bq27xxx_reg_cache cache = {0, };
 	bool has_singe_flag = di->opts & BQ27XXX_O_ZERO;
 
+	/*
+	 * Gauges with BQ27XXX_O_HIB (bq27541 family) can enter HIBERNATE,
+	 * which stops the conversion engine; register reads then return a
+	 * frozen snapshot forever. Reading does not wake the gauge; only a
+	 * Control() subcommand does (CLR_HIBERNATE = 0x0012).
+	 */
+	if (di->opts & BQ27XXX_O_HIB)
+		bq27xxx_write(di, BQ27XXX_REG_CTRL, 0x0012, false);
+
 	cache.flags = bq27xxx_read(di, BQ27XXX_REG_FLAGS, has_singe_flag);
```

注：`bq27xxx_write()` 已存在（i2c 路径 = `bq27xxx_battery_i2c_write`，LE16 写 0x00 寄存器，与 OPPO `bq27541_i2c_txsubcmd` 等价，oppo_bq27541.c:314-317）。若树内该函数名不同（有的是 `bq27xxx_write`，有的仅 i2c/one-wire 各自实现），按实际符号替换。

**配套（DT 或模块参数，二选一即可）**：把轮询从 360s 缩到 5s，读数才会"实时"：
```
# /etc/modprobe.d/bq27xxx.conf 或内核 cmdline：
bq27xxx_battery.poll_interval=5
```
（不加也行——补丁每轮 update 都会唤醒芯片，360s 一个点仍会推进，只是曲线粗糙；建议加上。）

**验证**：刷补丁重启后 `watch -n1 cat /sys/class/power_supply/bq27541-0/{voltage_now,current_now,capacity}` 应随充放变化；诊断脚本第 6 步的现象应复现于 sysfs。

**上游化备注**：该 bug 属"主线驱动对 bq27541 休眠模式无处理"，真机休眠冻结是真实 upstream 病例，值得整理后投 linux-pm@；补丁需处理 one-wire（w1 bq27000）路径不受影响（O_HIB 只挂 i2c 芯片族，无冲突）。

## 五、(c) DT 差异检查

stock 节点（sdm660-mtp-18321.dtsi:468-474，注意在 `#ifdef VENDOR_EDIT` 内且该 dtsi 中**被注释掉**——OPPO 实际启用的节点在 oppo 机型 dts 里，属性内容一致）：

```dts
bq27541-battery@55 {
    status = "okay";
    compatible = "oppo,bq27541-battery";
    reg = <0x55>;
    qcom,modify-soc-smooth;   /* OPPO 私有：SoC 平滑算法开关，主线驱动不解析，无对应物 */
};
```

主线节点（CPH1707 树 sdm660-oppo-r11t.dts:318-321）：`compatible/reg/status` 齐全，**没有缺失关键属性**。可选改进（非冻结根因）：
- `power-supplies = <&bms/&charger>`：主线 bq27xxx 不解析此属性（仅 NVM 型芯片支持 `monitored-battery`，见 bq27xxx_battery.c:1110），加了也无害但无用；
- `interrupts` + GPOUT 引脚：bq27541 有 GPOUT 可做转换完成中断，主线 i2c 驱动未实现中断化，现阶段不必做。

真正要补的不是 DT，而是上节的驱动补丁 + poll_interval。

## 六、后续建议（接续 HANDOVER §电源仪表线）

1. 先跑 §三 诊断脚本，把第 2/4/5/6 步输出发回——一步即可证实/证伪；
2. 证实后刷 §四 补丁（同时 `poll_interval=5`）；
3. 读数恢复后，结合 HANDOVER 中的墙充实验，重测 Wi-Fi 关联（供电假说的软件手段就位了）。
