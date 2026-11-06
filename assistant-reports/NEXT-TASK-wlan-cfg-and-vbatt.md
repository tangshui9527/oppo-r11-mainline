# 任务 C（任务 A 续）：wlan_cfg 协商面对照 + VBATT 探针 + SSR 快速路径

> 背景（务必先读）：
> ~/test/oppo-r11-mainline-workspace/HANDOVER.md §17 与
> assistant-reports/icnss-vs-ath10k-qmi.md
>
> 已确认事实：WCN3990 的 wlan_process 在 WLAN 使能后 ~20s 必然 fatal
> （err_qdi.c:459:EX:wlan_process:1:WLAN RT:1074..107b，PC 恒定 b00c56a0），
> 与关联/AP/功率/数据/cx-mx 投票/bank29/rejuvenate 协商全部无关。
> **关键新事实：本机固件拒绝授予 FW_REJUVENATE**（DYNAMIC_FEATURE_MASK
> 响应 curr=0x0），故"自恢复"路线不可用，必须阻止错误本身发生。

素材：
- stock ICNSS（已缓存）：~/test/oppo-r11-mainline-workspace/src-cache/icnss/icnss.c
  （分支 KERNEL.LA.UM.7.2.r1-06900-sdm660.0-REL）
  wlan_enable 的 cfg 构造在 icnss.c:3249-3318（host_version/tgt_cfg/svc_cfg/shadow_reg）。
- 主线 ath10k_qmi：CPH1707-Mainline/linux-sdm660-oppor11-t r11t/legacy-full-stack
  drivers/net/wireless/ath/ath10k/qmi.c 的 ath10k_qmi_cfg_send_sync_msg()
  （对照 ath10k Snoc 传入的 config——来自 ath10k_snoc.c 的 ce_tgt_cfg 等）。
- 消息定义：同目录 qmi_wlfw_v01.h（wlfw_wlan_cfg_req_msg_v01_ei）。

三个子任务：

## C1. wlan_cfg 协商面逐字段对照（最高优先）
stock icnss_wlan_enable() 与主线 ath10k_qmi_cfg_send_sync_msg() 发出的
QMI_WLFW_WLAN_CFG_REQ 逐字段对照：host_version 字符串、CE tgt_cfg 表
(pipe_num/pipe_dir/nentries/nbytes_max/flags——两端数值逐行对比！)、
svc_cfg 表、shadow_reg 表、以及 ath10k_snoc.c 里 config 的来源
（ath10k_hw_params 的 target_ce_config）。任何 nentries/nbytes/flags 差异
都可能是 wlan_process 启动后 ~20s 崩溃的根因（CE 环配置错 → 固件 DMA 越界）。
注意 stock 的 CE 配置表在 stock 内核的 qcacld/icnss 静态表里
（icnss.c 搜 ce_svc_cfg / target_ce_config），也要找出来对照。

## C2. 实验性 VBATT 探针（低风险并行）
给 ath10k_qmi 加模块参数 vbatt_probe（默认 0）：开启后 fw_ready 起每 5s 发
QMI_WLFW_VBATT_REQ（0x0032，消息定义在 qmi_wlfw_v01.h，stock 默认
VBATT_DISABLE 所以从未发过——本任务是实验变量）。观察崩溃时序是否改变。
VBATT_REQ 的字段：见 qmi_wlfw_v01.h 的 wlfw_vbatt_req_msg_v01（voltage_valid/
voltage，单位 mV，发 3700）。

## C3. SSR 快速路径（兜底）
即使崩溃无法根除，让它"自愈无感"：event_server_exit 时若距上次 fw_ready <10s
且非 unregistering → 标记 fast_restart；server 重新 arrive 时跳过 SCM MSA
权限重授（保留原 mapping），只重跑 ind_register/host_cap/cap。目标：崩溃对
用户态不可见（wlan0 不断）。

交付：assistant-reports/wlan-cfg-diff.md（C1 对照表 + C2/C3 补丁草案，
patches/0006 命名，可直接进 CI）。
