# C3：SSR 快速路径兜底（崩溃无法根除时让自愈对用户态无感）

目标：当 WLAN 固件短暂重启（无论 rejuvenate 还是 SSR）时，让主线 ath10k 的恢复又快又静——netdev 不消失、IP/关联态尽量保住、恢复延迟从秒级压到亚秒级。

## 现状梳理（主线已有的恢复路径）

主线**不是**全量 unregister：`ath10k_snoc_fw_indication()`（ath10k-snoc.c:1367-1404）在 `ATH10K_SNOC_FLAG_REGISTERED` 已置位时走 `ath10k_core_start_recovery(ar)`（保 netdev 的 core 重启），FW_DOWN 只置 RECOVERY/CRASH_FLUSH 标志。真正慢/脏的部分在 QMI 层：

| 步骤（每次 FW 重启都跑） | 位置 | 成本/风险 |
|---|---|---|
| `ath10k_qmi_remove_msa_permission()` | qmi.c:955（server_exit） | 2-3 次 SCM 调用；随后 re-arrive 又要重授（setup, qmi.c:891） |
| `ath10k_core_free_board_files()` | qmi.c:956 | 释放 BDF；re-arrive 后 msa_ready 再从 fs 重读 + 重下发 BDF（qmi.c:969, 134 区） |
| 全套 QMI 重握手 | qmi.c:862-905（server_arrive） | ind_register/host_cap/msa_mem_info/msa_ready/cap，必要的部分 |
| crash dump | qmi.c:958-960 | `ath10k_snoc_fw_crashed_dump`，SSR 时无害但耗时 |
| 用户态感知 | core_start_recovery | 重启期间 netdev 在但不可用（好于 down/up） |

stock 对照：icnss 的 PD restart 同样重握手，但 SCM 权限由 `msa_fixed_perm` 类似机制/或重启后重授，rejuvenate 时恢复感知为"闪断"。

## 补丁草案（三层，逐层独立可回退）

### 第 1 层（DT，零代码）：跳过 SCM 权限往返

`qmi.h` 的 `msa_fixed_perm` 已支持（qmi.c:1144 读 DT），置位后 setup/remove 全部短路（qmi.c:99-101, 120-122）。MSS/WLAN VMID 权限是 Hyp 层对内存区域的授权，**跨 PD 重启持续有效**，固件重启无需撤/授。

```diff
--- a/arch/arm64/boot/dts/qcom/sdm660-oppo-r11t.dts
+++ b/arch/arm64/boot/dts/qcom/sdm660-oppo-r11t.dts
@@ wifi@18800000
 			qcom,snoc-host-cap-8bit-quirk;
 			qcom,no-msa-ready-indicator;
+			qcom,msa-fixed-perm;
```

风险：仅当未来要**热更换** MSA 区域时才需要真实撤权；本设备区域固定（0x85700000），安全。

### 第 2 层（qmi.c）：SSR 退出时保留 BDF、只做必要通知

```diff
--- a/drivers/net/wireless/ath/ath10k/qmi.c
+++ b/drivers/net/wireless/ath/ath10k/qmi.c
@@ ath10k_qmi_event_server_exit()
 static void ath10k_qmi_event_server_exit(struct ath10k_qmi *qmi)
 {
 	struct ath10k *ar = qmi->ar;
 	struct ath10k_snoc *ar_snoc = ath10k_snoc_priv(ar);
 
-	ath10k_qmi_remove_msa_permission(qmi);
-	ath10k_core_free_board_files(ar);
+	if (test_bit(ATH10K_SNOC_FLAG_UNREGISTERING, &ar_snoc->flags) ||
+	    test_bit(ATH10K_SNOC_FLAG_MODEM_STOPPED, &ar_snoc->flags)) {
+		/* real shutdown: release everything */
+		ath10k_qmi_remove_msa_permission(qmi);
+		ath10k_core_free_board_files(ar);
+	}
+	/* SSR: keep MSA perms and board files; FW will re-arrive shortly */
 	if (!test_bit(ATH10K_SNOC_FLAG_UNREGISTERING, &ar_snoc->flags) &&
 	    !test_bit(ATH10K_SNOC_FLAG_MODEM_STOPPED, &ar_snoc->flags))
 		ath10k_snoc_fw_crashed_dump(ar);
@@ ath10k_qmi_event_msa_ready()
 {
 	int ret;
 
-	ret = ath10k_qmi_fetch_board_file(qmi);
-	if (ret)
-		goto out;
+	/* keep board files across SSR: fetch only if we lost them */
+	if (!ar->normal_mode_fw.board) {
+		ret = ath10k_qmi_fetch_board_file(qmi);
+		if (ret)
+			goto out;
+	}
 
 	ret = ath10k_qmi_bdf_dnld_send_sync(qmi);
```

（`ar->normal_mode_fw.board` 字段名以树内 core.h 实际为准；`ath10k_core_fetch_board_file` 成功后即持有该结构，`free_board_files` 不再被调即保持。）

### 第 3 层（qmi.c）：SSR 到达加速 + 超时兜底

与任务 A 的 rejuvenate 补丁联动：`REJUVENATE_IND` 置 `rejuvenate_pending` 后，`del_server` 记录 `jiffies`；`new_server` 在 N 秒内回来则视为预期闪断（不打 fw_crashed_dump、跳过第 2 层之外的重初始化降级）；**超时兜底**——若 10s 内 FW 未回来，走一次 `ath10k_core_unregister` 级别的彻底复位，防止卡死在 RECOVERY 状态：

```diff
@@ struct ath10k_qmi（qmi.h）
+	unsigned long fw_down_jiffies;
+	bool fast_restart_expected;
@@ ath10k_qmi_del_server()
 	if (qmi->state == ATH10K_QMI_STATE_INIT_DONE) {
+		qmi->fw_down_jiffies = jiffies;
+		qmi->fast_restart_expected = qmi->rejuvenate_pending;
 		ath10k_qmi_driver_event_post(qmi, ATH10K_QMI_EVENT_SERVER_EXIT, NULL);
 	}
@@ ath10k_qmi_new_server()
 	ath10k_dbg(ar, ATH10K_DBG_QMI, "qmi wifi fw qmi service connected\n");
+	if (qmi->fast_restart_expected &&
+	    time_after(jiffies, qmi->fw_down_jiffies + 10 * HZ))
+		qmi->fast_restart_expected = false;	/* came back too late */
 	ath10k_qmi_driver_event_post(qmi, ATH10K_QMI_EVENT_SERVER_ARRIVE, NULL);
@@ ath10k_qmi_event_server_exit()（第 2 层基础上）
 	if (!test_bit(ATH10K_SNOC_FLAG_UNREGISTERING, ...) &&
 	    !test_bit(ATH10K_SNOC_FLAG_MODEM_STOPPED, ...)) {
-		ath10k_snoc_fw_crashed_dump(ar);
+		if (qmi->fast_restart_expected)
+			ath10k_dbg(ar, ATH10K_DBG_QMI, "fw quick restart expected\n");
+		else
+			ath10k_snoc_fw_crashed_dump(ar);
+		/* timeout fallback: schedule full reset if FW never returns */
+		schedule_delayed_work(&ar_snoc->ssr_watchdog_work, 15 * HZ);
 	}
@@ ath10k_snoc（snoc.h/snoc.c）
+	struct delayed_work ssr_watchdog_work;	/* cancel on new_server & probe */
+
+static void ath10k_snoc_ssr_watchdog(struct work_struct *w)
+{
+	struct ath10k_snoc *ar_snoc = container_of(w, struct ath10k_snoc,
+						   ssr_watchdog_work.work);
+	struct ath10k *ar = ar_snoc->ar;
+
+	if (test_bit(ATH10K_SNOC_FLAG_REGISTERED, &ar_snoc->flags) &&
+	    !test_bit(ATH10K_SNOC_FLAG_UNREGISTERING, &ar_snoc->flags)) {
+		ath10k_err(ar, "fw did not come back after SSR, forcing reset\n");
+		ath10k_core_start_recovery(ar);
+	}
+}
```

（`new_server` 成功路径里 `cancel_delayed_work_sync(&ar_snoc->ssr_watchdog_work)`；字段名/工作队列初始化照 snoc.c 现有 work 模式。）

## 验证方法

1. 第 1 层：重启后 `dmesg | grep -i "msa\|scm"` 应不再出现 per-restart unmap/map；关联后手动触发 FW 重启（若有 debugfs trigger recovery：`/sys/kernel/debug/ath10k/.../simulate_fw_crash`）；
2. 第 2 层：触发两次 SSR，第二次 dmesg 应无 BDF fetch 字样、恢复时间（FW_READY 到 wlan 可用）明显缩短（可用 `time` 关联事件的 dmesg 时间戳差）；
3. 第 3 层：配合任务 A rejuvenate 补丁，rejuvenate 闪断后 2-3s 内 wlan 恢复且 nmcli/上层无 disconnect 事件（"对用户态无感"验收标准：`journalctl -u NetworkManager` 无 down/up 记录，或 ping 只丢 2-3 个包）；
4. 兜底：人为拦住 FW（如加载后 rmmod 前杀 FW？无法直接做——改为：把 10s 阈值临时调成 2s 验证 watchdog 路径能走到 core_start_recovery）。

## 与任务 A 补丁的关系

任务 A 的 rejuvenate 三件套是根因修复；本补丁是恢复质量优化，两者正交但共用 `rejuvenate_pending`/`fast_restart_expected` 状态。建议合入顺序：A 修复 1 → C3 第 1/2 层 → 观察一周 → 视需要上第 3 层。
