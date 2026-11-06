# 任务 D：ath10k CE 运行层 vs stock HIF 行为对照（最后未探区）

> 背景（先读）：HANDOVER.md §17-20 + assistant-reports/c1-wlancfg-ce-compare.md。
> 状态总结：wlan_process 在 WLAN 使能后 ~20s fatal（RT:1074-107b，PC=b00c56a0 恒定）。
> 已排除（实验/源码双证）：QMI 协商面全等（C1）、VBATT（C2 实验阴性）、rejuvenate
> 协商（FW 拒绝）、cx/mx 投票、bank29、关联/功率/数据变量、MSA 内存权限。
> C1 报告 §6 指出剩余方向：**host 运行期对 FW 的影响——CE 中断/轮询策略差异
> （ath10k ce.c 运行层 vs stock HIF ce_main.c）**。

素材：
- stock HIF：oppo-sdm660-devs/android_kernel_oppo_sdm660（lineage-22.2）
  qca-wifi-host-cmn/hif/src/ce/ce_main.c、ce_src.c、ce_dst.c、ce_service.c、
  hif/src/ath_procfs.c、hif/src/snoc/if_snoc.c（缓存已在 src-cache/stock-oppo/qcacld/）
- 主线：drivers/net/wireless/ath/ath10k/ce.c、ce.h、snoc.c（CPH1707 树）

对照要点（按"能解释 ~20s 定时死"的概率排）：
1. **CE 中断 vs 轮询**：ath10k_snoc 对 WCN3990 的 CE 是否用 interrupt 模式而
   stock 用 poll（或反之）？irq 处理差异（enable/disable/ack 时机）。
2. **copy engine 的 interrupt_mitigation / rx retry**：ath10k 有
   ATH10K_IRQ_NUM.../snoc 的 wdog 喂狗路径？
3. **CE pipe 的水源/汇配置运行期差异**：src_ring/dst_ring 的 fill 逻辑、
   低水位处理、环形回绕边界。
4. **fastpath/CE 配送延迟**：stock HIF 的 ce_send_fastpath 与 ath10k 差异。
5. **per-CE irq 名字/亲和性**：snoc 的每 CE irq 注册差异（stock 有
   ce_irq_summary？）。
6. 额外线索：崩溃 RT 码在 1074-107b 漂移 + PC 恒定 → 同一函数不同分支。
   对照 stock 中该 PC 附近的函数（如果 stock 有 vmlinux/System.map 可算——
   modem 侧 PC 无法对照，忽略）。

交付：assistant-reports/ce-runtime-diff.md——差异清单（stock 行为 | ath10k 行为 |
文件:行号 | 可能性评估）+ top2 补丁草案（patches/0007+，可直接进 CI）。
