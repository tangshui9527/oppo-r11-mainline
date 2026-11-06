# C1：QMI_WLFW_WLAN_CFG 逐字段对照（stock qcacld/icnss vs 主线 ath10k）

结论先行：**两边 WLAN_CFG 载荷逐字段一致**。CE 管道表不是差异面，"CE 环配置错误 → 固件 DMA 越界 → ~20s 定时崩"这条候选链在 QMI 协商面上被**排除**。证据如下（全部源码已缓存，行号可复核）。

## 1. 数据源确认（关键前提）

stock 侧 WLAN_CFG 的内容**不是 icnss.c 决定的**，而是 qcacld 传入：

- 调用链：qcacld `hif_wlan_enable()`（`qca-wifi-host-cmn/hif/src/ce/ce_main.c:2942`）→ `hif_get_target_ce_config()`（ce_main.c:2726，取自 `hif_state->target_ce_config`）→ `pld_wlan_enable()` → `pld_snoc_wlan_enable()`（`qcacld-3.0/core/pld/src/pld_snoc.c:334-365`，纯转发）→ `icnss_wlan_enable()`（icnss.c:3246）。
- SDM660 走 **`TARGET_TYPE_ADRASTEA`**（`if_snoc.c:222`：`QCA_WIFI_3_0_ADRASTEA` 硬编码），非 lowdesc 属性未置位 → 使用 **`target_ce_config_wlan_adrastea`**（`ce_assignment.h:873`）。注意不是 qca6390 表（那是 PCI 路径）。
- 主线侧：`ath10k_snoc_wlan_enable()`（ath10k-snoc.c:971-1019）→ `target_ce_config_wlan`（ath10k-snoc.c:244-364）。
- stock 树（YuxuanZuo）不含 qcacld；qcacld 取自 `oppo-sdm660-devs/android_kernel_oppo_sdm660`（lineage-22.2, drivers/staging/qca-wifi-host-cmn + qcacld-3.0），与 R11 同平台。

## 2. CE 目标管道表（tgt_cfg）逐字段

| CE | 方向 | nentries | nbytes_max | flags (stock adrastea) | flags (mainline) | 一致? |
|----|------|---------|-----------|------------------------|------------------|-------|
| 0 | OUT | 32 | 2048 | 0 (CE_ATTR_FLAGS=0，LE host) | 0 | ✅ |
| 1 | IN | 32 | 2048 | 0 | 0 | ✅ |
| 2 | IN | **64** | 2048 | 0 | 0 | ✅ |
| 3 | OUT | 32 | 2048 | 0 | 0 | ✅ |
| 4 | OUT | 256 | 256 | 0x08 (DISABLE_INTR) | 0x08 (DIS_INTR=BIT3) | ✅ |
| 5 | OUT | 1024 | 64 | 0x08 | 0x08 | ✅ |
| 6 | INOUT | 32 | 16384 | 0 | 0 | ✅ |
| 7 | H2H(4) | 0 | 0 | 0x08 | 0x08 | ✅ |
| 8 | IN | 32 | 2048 | 0 | 0 | ✅ |
| 9 | IN | 32 | 2048 | 0 | 0 | ✅ |
| 10 | IN | 32 | 2048 | 0 | 0 | ✅ |
| 11 | IN | 32 | 2048 | 0 | 0 | ✅ |

宏数值核实：stock `CE_ATTR_FLAGS=0`（ce_assignment.h:59-61，LE host 分支）、`CE_ATTR_DISABLE_INTR=0x08`（ce_api.h:402）；mainline `CE_ATTR_FLAGS=0`（ce.h:386）、`CE_ATTR_DIS_INTR=BIT(3)=0x08`（ce.h:279）。PIPEDIR 语义一致（IN=1/OUT=2/INOUT=3/H2H=4；stock 由 if_ahb.c:673-681 的 `pipedir & PIPEDIR_OUT/IN` 位用法与 ath10k ce.h:415-418 推断吻合，标注为推断）。
表条目数：两边都是 12（CE0-11）。

## 3. service-to-pipe 映射表

stock `target_service_to_ce_map_wlan`（ce_main.c:285-395，ADRASTEA 分支含末尾三条）与 mainline `target_service_to_ce_map_wlan`（ath10k-snoc.c:366 起）逐条一致：WMI VO/BK/BE/VI/CONTROL OUT→3/IN→2、HTC_CTRL_RSVD OUT→0/IN→2、HTC_RAW OUT/IN→2、HTT_DATA_MSG OUT→4/IN→1、WDI_IPA_TX OUT→5、**ADRASTEA 专属三条 HTT_DATA2→IN 9 / HTT_DATA3→IN 10 / PKTLOG→IN 11**、尾部 {0,0,0} 哨兵。✅

## 4. shadow reg 配置

stock `target_shadow_reg_cfg_map`（ce_main.c:167-181）：SRC{0,3,4,5,7}@0x3C + DST{1,2,7,8,9,10,11}@0x40，共 12 条；`ADRASTEA_SRC_WR_INDEX_OFFSET=0x3C`、DST=0x40（ce_main.c:164-165）。
mainline `target_shadow_reg_cfg_map`（ath10k-snoc.c:75-118）：SRC{0,3,4,5,7}@0x3C + DST{1,2,7,8,9,10,11}@0x40，共 12 条（WCN3990_SRC/DST_WR_IDX_OFFSET，ath10k-snoc.c:73-74）。✅

## 5. 其余字段

| 字段 | stock | mainline | 评估 |
|---|---|---|---|
| host_version | `"QWLAN_VERSIONSTR"`（ce_main.c:3000，valid=1） | valid=0（qmi.c ath10k_qmi_cfg_send_sync_msg） | FW 仅记录/日志用，无行为分支（stock 头文件无对应处理），**无风险** |
| shadow_reg_v2 | 未填（icnss.c 无引用） | 未填（qmi.c 无引用，消息定义头文件有但未用） | 一致 |
| WLAN_MODE | MISSION | MISSION | 一致 |

## 6. 结论与影响

1. **C1 是干净的阴性结果**：QMI 协商面上 CE/服务/shadow 配置完全一致，不存在"主线配置让固件环配置错位"的可能。结合任务 A 已排除 MSA 内存/权限差异与周期行为差异（除 rejuvenate），"~20s 定时崩"的候选空间进一步收窄到：FW_REJUVENATE 协商缺失（任务 A 首选）、以及 FW 内部与 host 无关的状态机问题（只能靠 rejuvenate cause 日志或 FW 侧工具定位）。
2. "CE DMA 越界"若仍怀疑，只能来自**运行期行为**（如 host 侧 ring 深度与 FW 侧期望不符的表现层），但 QMI 协商值一致意味着 FW 侧初始化完全相同——固件崩溃应该与 stock 下完全同路径，即 stock 也应崩。stock 不崩 + 协商一致 → 根因回到"stock 做了而主线没做的协商/恢复路径"（rejuvenate 三件套），或 host 运行期对 FW 的影响（如 ATH10K 的 CE 中断/poll 策略差异——那是 ce.c 运行层，不在本任务范围，列为后备方向）。

源码缓存：`src-cache/icnss/`（主线）与 `src-cache/stock-oppo/qcacld/`（sparse clone 于 /tmp/osd-sparse，已复制关键文件：ce_main.c、ce_assignment.h、pld_snoc.c、if_snoc.c、pld_common.h）。
