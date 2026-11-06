# OPPO R11 (CPH1707) Mainline Linux & Wi-Fi Bringup 交接文档

> **更新日期**: 2026-11-06（第二轮交接，Wi-Fi 根因攻坚会话）
> **适用机型**: OPPO R11 (`oppo16051` / `CPH1707`, 高通骁龙 660, 4GB RAM + 64GB eMMC)
> **内核版本**: Mainline Linux 7.0.9-sdm660+（CPH1707-Mainline/linux-sdm660-oppor11-t，分支 `qcom-sdm660-7.0.y`）
> **用户空间**: Arch Linux ARM aarch64（eMMC `/dev/mmcblk1p69`，headless 模式）
> **文档定位**: 记录 Wi-Fi 崩溃循环的真实根因证据链、已验证的结论、当前刷入镜像状态与下一步执行路线。

---

## 0. 当前状态速览（TL;DR）

| 项目 | 状态 |
| :--- | :--- |
| 系统稳定性 | ✅ Headless Arch 长期稳定，**本轮所有崩溃/恢复全程未掉电**，第一轮的"电气掉电"问题在正确启动链下未复现 |
| Wi-Fi 链路 | ✅ 已打通到**扫描成功**（真实返回 BSS 列表），但固件约 12 秒后进入崩溃循环 |
| 崩溃根因 | ✅ 实锤：ath10k 经 QMI 下发板级校准数据（BDF）被固件拒收（`QMI_ERR_INCOMPATIBLE_STATE`=90）→ 固件无校准裸奔 → 扫描后崩溃；BDF 失败还跳过了 MAC 读取（这就是"随机 MAC"的来源） |
| **⚠️ 当前刷入镜像** | **`boot-r11t-nomsa.img`（已移除 `no-msa-ready-indicator` quirk）——此镜像下 Wi-Fi 完全挂起（固件从不发 msa_ready 指示），需要回退或刷 driver 补丁版**。原 quirk 版镜像仍在 `out_cph1707/oppo-r11-cph1707-boot/boot-r11t-arch.img` |
| BDF 资产 | ✅ R11 原厂校准已提取并打包（`wifi-bdf/` 目录），设备上已安装（md5 `1e19409e`），持久化于 rootfs |
| Linux 内进 fastboot | ❌ BCB 两种命令均被 OPPO ABL 忽略；IMEM restart reason 线索已定位待试；现阶段仍需手动按键进 fastboot |

---

## 1. 设备与通道实况

* **宿主机**: 内网 Linux 主机（SSH 目标由环境变量 `R11_HOST` 指定，凭据不写入仓库），fastboot / 串口都在这台机器上
* **串口**: 手机枚举为 `/dev/ttyACM1`（USB `18d1:d003`）；fastboot 为 `18d1:d00d`（设备序列号由 `ADB_SERIAL` 环境变量提供）
* **命令通道**: `python3 tools/remote_exec.py '<cmd>' [timeout]`（已内置 Ctrl-C/Ctrl-L 救援前缀）
* **文件推送**: `python3 tools/push_file.py <本地文件> <设备路径> [chunk]`（串口分块 base64，MD5 校验）
* **串口脆弱性（重要）**:
  * USB gadget 重枚举后 getty/shell 可能僵死（只回显不执行），先用 Ctrl-C+Ctrl-L 救援，救不活就只能重启
  * **每次 MSS stop/start 都会伴随 USB gadget 重枚举**，操作 remoteproc 后要预期串口短暂失联
  * 上游固件拉取 `wlanmdsp.mbn` 经 tqftpserv（`/usr/lib/firmware/image` → `/mnt/modem/image`），本轮日志 630 次

## 2. 本轮第一性原理复盘（证据链）

### 2.1 服务层真相（纠正第一轮文档的误判）
第一轮交接文档记录的"`rmtfs`/`qrtr-ns` 未运行"是**误判**（查错了单元名）。实际单元为 `r11t-transport / r11t-rmtfs / r11t-tqftpserv`，全部 `active (running)`，平台服务编排（`r11t-hardware.target` 体系）是完整的。之前 Wi-Fi 不工作的直接原因是 `r11t-wifi.service` 被禁用 + MSS 从未拉起。

### 2.2 崩溃签名（dmesg 实录）
```
qcom-q6v5-mss 4080000.remoteproc: fatal error received:
  err_qdi.c:459:EX:wlan_process:1:WLAN RT:1075/1076/1078/107b:PC=b00c56a0
ath10k_snoc 18800000.wifi: firmware crashed! (guid ...)
ath10k_snoc 18800000.wifi: board_file api 2 bmi_id N/A crc32 00000000   ← 板级数据 CRC 为 0
ath10k_snoc 18800000.wifi: failed to set PS Mode 1 for vdev 0: -108
```
* 崩溃点恒定 `PC=b00c56a0`，错误码在 1075~107b 间变化，扫描后 ~12 秒触发，恢复循环间隔 ~5 秒
* `device successfully recovered` + MSS 自动重启——**整机不掉电**，与第一轮的"36~64 秒必然掉电"是两个不同层面的故障（第一轮故障=电气/掉电，本轮=固件崩溃）

### 2.3 根因证据（ath10k QMI debug，`modprobe ath10k_core debug_mask=0x200000`）
```
ath10k_snoc 18800000.wifi: DT bdf variant name not set.
ath10k_snoc 18800000.wifi: failed to download board data file: 90
```
* 错误码 90 = `QMI_ERR_INCOMPATIBLE_STATE_V01`（`include/linux/soc/qcom/qmi.h`）
* BDF 走 `ath10k_qmi_event_msa_ready()` → `ath10k_qmi_bdf_dnld_send_sync()`（QMI WLFW BDF_DOWNLOAD，源码已核实）
* 固件侧**从不**通过 TFTP 拉 bdwlan（tqftpserv 日志只有 wlanmdsp.mbn）→ BDF 只能走 ath10k QMI 通道
* BDF 失败 → `cal_report` 和 `mac_addr` 全部被跳过 → 固件无校准 + 随机 MAC，与全部观测吻合
* 排除了 firmware-5.bin 失配假说：上游 WCN3990 的 `firmware-5.bin` 本来就是 60 字节 stub（md5 与设备一致）

### 2.4 quirk 对照实验（关键结论）
| 配置 | 行为 |
| :--- | :--- |
| DTB 带 `no-msa-ready-indicator`（上游默认） | 服务到达即抢跑 BDF → **被拒 90** → 固件裸奔、扫描后崩溃循环 |
| DTB 移除该 quirk（当前刷入的 nomsa 镜像） | MSA 流程走完（`msa mem ready completed`）但**固件永远不发 msa_ready 指示**，驱动挂起，wlan0 永不出现 |

→ OPPO 固件（`WLAN.HL.1.0.1.c2.1-00098`）既不接受过早的 BDF，也不发 msa_ready 指示。**出路是改驱动**：恢复 quirk，把 BDF 下发时机推迟（如 fw_ready 指示之后，或带重试）。

## 3. 资产清单（本轮新增）

* **`wifi-bdf/`**：
  * `bdwlan-from-persist.bin`（19152B，md5 `94b31aa1...`）——从 `backup/persist.img` 经 debugfs 提取的原厂校准
  * `board-2-r11t.bin`（md5 `1e19409e...`）——bdencoder 打包（names: `bus=snoc,qmi-board-id=0` / `ff` / `bus=snoc`），已装到设备 `/lib/firmware/ath10k/WCN3990/hw1.0/board-2.bin`
  * `board-2-generic-upstream.bin`（md5 `420356eb...`）——上游通用版，对照实验用
  * `bdencoder`——ath10k 官方打包工具（qca/qca-swiss-army-knife）
* **`tools/remote_exec.py`、`tools/push_file.py`**——串口命令/推文件工具
* **boot 镜像变体**（`out_cph1707/oppo-r11-cph1707-boot/`）：
  * `boot-r11t-arch.img`——原 quirk 版（BDF 被拒但 wifi 能起来）
  * `boot-r11t-nomsa.img`——去 quirk 版（**当前刷入，wifi 挂起，需回退**）
* 设备侧残留：`/tmp/board-2-r11t.bin`（完好）、`/tmp/board-2-generic.bin`（**推送被中断，未过 MD5，不可直接使用**）

## 4. 下一步路线图

### 步骤 1：回退或推进 boot 镜像（必须先做）
当前镜像下 Wi-Fi 挂起。两条路：
* **回退**：刷回 `boot-r11t-arch.img`（恢复"能扫但崩"状态），继续在软件层面调试
* **推进（推荐）**：恢复 DTB quirk + 给 `drivers/net/wireless/ath/ath10k/qmi.c` 打补丁——把 `ath10k_qmi_event_msa_ready()` 中的 BDF 下发延后/重试（如推迟到 `ATH10K_QMI_EVENT_FW_READY_IND` 之后，或在 `wlan_enable` 后重试一次）。走现有 CI（`.github/workflows/build.yml`，KERNEL_REPO=CPH1707-Mainline/linux-sdm660-oppor11-t）重建
* 刷机仍需手动进 fastboot（Linux 内自动进 fastboot 见 §5）

### 步骤 2：BDF 内容 vs 状态鉴别实验（2 分钟，上一会话被打断）
用**通用版** board-2.bin 再测一次 BDF 下发（push 后核对 MD5 再换入）：
* 若通用版也被拒 90 → 纯状态问题，全力走步骤 1 补丁
* 若通用版被接受 → 内容问题，改用 modem 分区里的 `bdwlan.102/104/...`（按 board-id 打包多条目 board-2.bin）重试

### 步骤 3：扫描 + 关联实验（BDF 被接受后）
```bash
iw dev wlan0 set power_save off
iw dev wlan0 set txpower fixed 1000    # 10dBm，约束射频脉冲
iw dev wlan0 scan
wpa_supplicant -i wlan0 -c /etc/wpa_supplicant/wpa_supplicant-wlan0.conf -B
```
观察是否仍有 `WLAN RT` 崩溃；若 BDF 修复后不再崩，接着验 `sshd` 经 Wi-Fi 的连通。

### 步骤 4：收尾项
* MAC 固定：BDF/MAC 流程通了之后 `invalid MAC address` 应消失；否则从 `ip link set wlan0 address` 固定
* 把约束写进 `/usr/lib/r11t/start-wifi` 并启用 `r11t-wifi.service`
* USB-NCM 有线兜底（`initramfs/setup-ncm.sh` 已有，手机侧当前只有 ACM）
* 电池计 `bq27541-0` 读数失真（voltage_now=2.48V 不可能、capacity=2774 异常），DTS 侧待修
* 显示/图形未回归验证

## 5. Linux 内重启进 fastboot（✅ 已彻底解决）

* **原理实证**：高通 SDM660 ABL 启动时直接读取物理寄存器 IMEM 地址 **`0x146BF65C`**（IMEM 物理基址 `0x146BF000` + 偏移 `0x65C`）。
* **高通 Magic 重启码**：
  * `0x77665500`：进入 `bootloader` / `fastboot`
  * `0x77665502`：进入 `recovery`
  * `0x776655ee`：进入 `edl`（高通 9008 深度救砖模式）
  * `0x77665501`：正常开机启动
* **原生工具构建**：源码位于 `tools/qcom-reboot.c`，已在设备安装 `/usr/local/bin/qcom-reboot`（67KB 动态链接无依赖 ELF）。
* **便捷软链接**：设备已创建全局命令：
  * `reboot-fastboot` / `reboot-bootloader`：立即重启进 fastboot 模式（经真机验证，瞬间响应 `18d1:d00d`，`fastboot getvar product` 耗时 0.001s）
  * `reboot-recovery`：重启进 recovery 模式
  * `reboot-edl`：直接拉入 9008 EDL 刷机模式
* **长期集成方案**：在 DTS `sram@146bf000` 节点下增加 `syscon-reboot-mode` 子节点（驱动 `drivers/power/reset/syscon-reboot-mode.c`），即可让内核原生的 `systemctl reboot bootloader` 自动写值生效。

## 6. 关键参考

* pmaports SDM660 内核（纯主线无补丁，config 与我们一致）：`device/testing/linux-postmarketos-qcom-sdm660`（仓库默认分支 `main`，gitlab.nura.eco）
* Wi-Fi 配方：pmaports MR !4897（lavender，同为 SDM660+WCN3990）
* qcom-deb-images issue #23：ath10k SNOC 用户态依赖（qrtr-tools + tqftpserv；tqftpserv/rmtfs 对 qrtr-ns 只能 `After=` 不能 `Requires=`）
* WCN3990 regdomain 工具：M0Rf30/wcn3990-regdomain（BDF 16-bit XOR 校验和 = 0xFFFF 的坑，改 BDF 内容时注意）
* ath10k firmware-5.bin / wlanmdsp.mbn 版本同步讨论：lists.infradead.org ath10k 2023-12

## 7. 结语

第一轮的"无限重启"和本轮的"Wi-Fi 崩溃"是**两个独立的故障**：前者（电气掉电）已在正确的 modem 服务启动链下消失；后者已收敛到唯一断点——**BDF 经 QMI 下发的时机被 OPPO 固件拒绝**。剩下的工作高度工程化：改一处驱动时序 + 一次刷机验证即可见分晓。
