# 任务 D：ath10k CE 运行层 vs stock HIF（Adrastea SNOC 路径）行为对照

背景：wlan_process 在 WLAN 使能后 ~20s fatal（RT:1074-107b 漂移、PC=b00c56a0 恒定）；QMI 协商面已全等（C1 阴性）。本报告覆盖 C1 §6 指出的"host 运行期对 FW 的影响"。

素材：主线 `ath10k-ce.c/ce.h/hw.c/snoc.c`（CPH1707 树，已缓存 `src-cache/icnss/`）；stock HIF（oppo-sdm660-devs lineage-22.2 `qca-wifi-host-cmn/hif/src/`，已缓存 `src-cache/stock-oppo/qcacld/`）。SDM660/WCN3990 = Adrastea 非 SRNG 路径（stock `if_snoc.c:222`），stock service 层用 `ce_service_legacy.c`。

## 一、差异清单

| # | stock HIF 行为 | 主线 ath10k 行为 | 证据 (stock / mainline) | 可能性评估 |
|---|---|---|---|---|
| 1 | **CE init 时对每个 CE 使能 error 中断**：`CE_ERROR_INTR_ENABLE` 写 MISC_IE(0x34) \|= 0x3E0（AXI err/DST addr err/SRC len err/**DST_MAX_LEN_VIO**/DST/SRC ring overflow） | **error 中断从无 enable 路径**：`ath10k_ce_per_engine_handler_adjust()` 只处理 copy-complete + watermark；`ath10k_ce_error_intr_disable()` 只在 disable 流程被调用 | ce_main.c:1624-1630 + ce_reg.h:454-477（宏定义）/ ath10k-ce.c:1303-1322（handler_adjust 无 error 使能；`grep error_intr_enable` = 0 处） | **高（诊断价值）/ 中（因果）**：这是 CE 运行层最实质的寄存器级差异。FW 侧若发生 CE 错误（如 DST_MAX_LEN_VIO——CTRL1 DEST_MAX_LENGTH POR=0x80=128B，见 #4），stock 能看到、主线完全静默；且 MISC_IS(0x38) 位在主线**永不清除** |
| 2 | service 路径会读 MISC_IS 并打印错误（`CE_MISC_INT_STATUS_GET` 用于 DEBUG 和校验） | `ath10k_ce_per_engine_service()` 只清 HOST_IS(0x30) 的 cc_mask\|wm_mask，MISC_IS 位**从不读不清** | ce_reg.h:461-463 + ce_main.c:3760-3781 / ath10k-ce.c:1236-1258 | 与 #1 同链：主线 CE 错误状态位无限累积 |
| 3 | disable 中断后**读回 flush**（write 0 → read） | disable 只写不读（posted write，可能在 re-enable 前未落） | hif_io32_snoc.h:35-54 / ath10k-ce.c:377-383 | 低：host 侧竞态，不直接杀 FW，顺手修 |
| 4 | CTRL1(0x18) DEST_MAX_LENGTH：**两侧都不写**（POR=0x80=128B） | 同（仅 src ring 写 dmax=src_sz_max，ath10k-ce.c:1387） | adrastea_reg_def.h:553/698（POR 0x80）/ ath10k-ce.c:1427-1432（dest init 无 dmax） | 阴性：两侧一致，但**值得注意**——若 FW 侧对该字段有不同期望，会触发 DST_MAX_LEN_VIO（正好是 #1 的错误位），见 §三 |
| 5 | watermark 阈值：stock **不写** SRC/DST watermark 寄存器（0x4c/0x50） | init 写 lowmark=0 / highmark=nentries（src+dst） | ce_main.c grep WATERMARK=0 处（仅宏定义）/ ath10k-ce.c:1394-1400, 1428-1432 | 低：阈值本身不触发行为（watermark 中断两侧均屏蔽/未使能），但寄存器状态不同 |
| 6 | watermark 中断策略：legacy service 按 CE_WM 标志**动态 enable/disable**（`ce_per_engine_handleradjust_legacy`，ce_service_legacy.c:1100-1120） | 一次性 disable（handler_adjust 固定关 watermark） | ce_service_legacy.c:1115-1117 / ath10k-ce.c:1303-1306 | 低：中断策略差异，host 侧 |
| 7 | IRQ 处理模型：per-CE irq → tasklet（不 mask，service 中清状态） | per-CE irq → `ath10k_ce_disable_interrupt`（关 copy-complete+error+watermark）→ napi → service → handler_adjust 重新开 | if_snoc.c:352-373 / ath10k-snoc.c:1227-1250, 928-946 | 低：模型差异，均常见；配合 #3 顺手对齐 |
| 8 | per-CE poll_timer（10ms） | 无 | ce_main.c:1608-1620（**仅 epping 路径**） | 阴性：mission 模式不跑 |
| 9 | sleep_timer / target 唤醒握手（`Q_TARGET_ACCESS_BEGIN`） | 无（也无对应实现） | ce_main.c:3353（仅 `ce_srng_based` 才挂 bus_ops，Adrastea 不挂）→ SNOC 实际 no-op / ath10k 注释提到"last int cleared 后 HW 睡眠"（ath10k-ce.c:1242-1246）但无实现 | 阴性：两侧都没有 SNOC 唤醒握手；**但该注释值得警惕**——若主线在 FW 休眠态访问 CE 寄存器（如 #10 的诊断轮询），会踩坑 |
| 10 | OOM RX 恢复：`ce_oom_recovery` workqueue 持续重投直到至少 1 个 desc 成功 | `rx_post_retry` timer（10ms 重试，snoc.c:540-562） | ce_main.c:1633-1635 / ath10k-snoc.c:540-562, 1412 | 阴性（功能等价） |
| 11 | doorbell/UPD：CTRL1.IDX_UPD_EN（bit19）POR=0，两侧都不置 | 同 | adrastea_reg_def.h:570 / ath10k-hw.c wcn3990_ctrl1_upd.enable=0 | 阴性 |

排除项汇总：runtime PM（两侧 HIF 层均无）、fastpath（stock `ce_sendlist_send` 与 ath10k `ath10k_ce_send_nolock` 语义等价，scatter-gather 差异仅 host 效率）、rri_on_ddr（Genoa 专属，两侧均未启）、per-CE irq 亲和性（stock 也无专门亲和）。

## 二、机制推演（RT:1074-107b + PC 恒定）

PC 恒定 + RT 码小幅漂移 = FW 在同一函数的不同分支反复命中同一断言。C1 已证 QMI 协商全等 → FW 的 CE 环初始化输入与 stock 完全一致 → **差异只能来自运行期 host 行为改变 FW 的观察结果**。候选链（按概率）：

1. **CE 错误事件静默累积链（#1+#2）**：运行期某 CE 错误（最可能 DST_MAX_LEN_VIO：POR max-length=128B vs HTT/WMI 消息 >128B；或 ring overflow）在两块板都会发生，stock 上 host 立即得到中断并处理/打印，主线上错误位无声累积。若 FW 侧对"CE 错误后 host 不响应"有超时看门狗（20s 量级、PC 恒定的内部断言完全符合这类看门狗形态），即可复现故障。**此链的前半段（寄存器差异）为源码证实，后半段（FW 看门狗）为推测**——补丁 0007 落地后 dmesg 的 CE 错误打印会直接检验它。
2. 时间线兼容性：使能后 ~20s → 关联/流量推动 CE 使用率上来后首个错误事件出现 → FW 内部超时 → fatal。静默 10dBm 也崩 → 与关联无关，只与"CE 中断总闸打开后的活动"有关，兼容。
3. 无法从源码证实 FW 内部断言的语义（无 FW 符号），RT:1074-107b 只能作为修后对照指标。

## 三、Top 2 补丁（已落 patches/0007、0008 草案）

### 0007（首选）：CE error 中断与 MISC_IS 处理对齐 stock

三件事（一个补丁）：
1. CE init（`ath10k_ce_init_pipe` 末尾/handler_adjust）对每个 CE 写 `MISC_IE(0x34) |= 0x3E0`（与 stock 宏 CE_ERROR_MASK 完全一致）；
2. `ath10k_ce_per_engine_service()` 增加 misc 处理：读 MISC_IS(0x38)，非零则打印 CE id + 位解码（AXI_ERR/DST_ADDR/SRC_LEN/DST_MAX_LEN_VIO/OFLOW×2）并写 0 清除——stock 语义；
3. copy-complete/watermark disable 写后**读回**（对齐 hif_io32_snoc.h 的 flush 习惯）。

预期：a) 若 ~20s 崩溃前 dmesg 开始出现 CE 错误打印 → 机制坐实且拿到具体错误位；b) 若错误位全零但仍崩 → #1 因果排除，错误位累积假说证伪，转 FW 内部（用 0008 抓现场）。

### 0008（诊断兜底，默认关闭）：CE 状态快照

module param `ce_diag_poll=0`（开启后 1s 周期读 12 个 CE 的 HOST_IS/MISC_IS 并记录 delta），并在 `ATH10K_SNOC_FLAG_RECOVERY` 置位瞬间（FW 死前最后机会）dump 全部 CE 状态。**默认关**——ath10k-ce.c:1242-1246 的警告（CE 时钟关闭后访问寄存器可能硬件故障）意味着轮询本身有风险，仅诊断期开启。对照点：崩溃瞬间 MISC_IS/HOST_IS 的非零位。

## 四、验证顺序建议

1. 只上 0007 → 复跑关联 + 静默测试（原时序下 10/20s 两档观察）；
2. dmesg `grep -i "ce.*err\|misc"` 对照 RT 码漂移；
3. 若 0007 治愈：提交主线社区前需评估"主线从未使能 error int 是历史行为"——保留 error 打印但 rate-limit；
4. 若未治愈：开 0008 复跑，抓 FW 死前最后的 CE 状态，对照 PC=b00c56a0。
