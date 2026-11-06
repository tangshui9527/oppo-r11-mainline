# C2：VBATT 探针补丁（实验变量）

目的：验证"WCN3990 FW 是否因收不到电池电压上报而行为异常"（任务 A 已确认 stock R11 默认不发 VBATT，但 stock 的 quirks 是 module param 可调，无法 100% 排除产品配置改过——用探针实验把这个变量也钉死）。

前置确认：CPH1707 树的 `qmi_wlfw_v01.h:517-529` 与 `qmi_wlfw_v01.c:1682-1710` **已含** `wlfw_vbatt_req_msg_v01`（`u64 voltage_uv`）与 resp 的完整定义和 ei 数组（与 stock `wlan_firmware_service_v01.h:599-611` 相同）。补丁只需改 `drivers/net/wireless/ath/ath10k/qmi.c` + `qmi.h`。

## 补丁草案

```diff
--- a/drivers/net/wireless/ath/ath10k/qmi.h
+++ b/drivers/net/wireless/ath/ath10k/qmi.h
@@ struct ath10k_qmi {
 	struct work_struct event_work;
 	struct workqueue_struct *event_wq;
+	struct delayed_work vbatt_work;
@@
 	bool msa_fixed_perm;
 	bool no_msa_ready_indicator;
+	bool vbatt_probe;
 	enum ath10k_qmi_state state;
 };
--- a/drivers/net/wireless/ath/ath10k/qmi.c
+++ b/drivers/net/wireless/ath/ath10k/qmi.c
@@ 文件头 module_param 区
+/*
+ * Experimental: periodically send QMI_WLFW_VBATT_REQ with a fixed voltage,
+ * replicating the stock ICNSS vbatt feature (disabled by default there too).
+ * Only to test whether FW behaviour depends on receiving battery voltage.
+ */
+static bool vbatt_probe;
+module_param(vbatt_probe, bool, 0644);
+MODULE_PARM_DESC(vbatt_probe, "send periodic VBATT QMI messages (experimental)");
+
+static void ath10k_qmi_vbatt_work(struct work_struct *w)
+{
+	struct ath10k_qmi *qmi = container_of(to_delayed_work(w),
+					      struct ath10k_qmi, vbatt_work);
+	struct wlfw_vbatt_req_msg_v01 req = { .voltage_uv = 3700000ULL };
+	struct wlfw_vbatt_resp_msg_v01 resp = {};
+	struct qmi_txn txn;
+	int ret;
+
+	ret = qmi_txn_init(&qmi->qmi_hdl, &txn,
+			   wlfw_vbatt_resp_msg_v01_ei, &resp);
+	if (ret < 0)
+		goto resched;
+
+	ret = qmi_send_request(&qmi->qmi_hdl, NULL, &txn,
+			       QMI_WLFW_VBATT_REQ_V01,
+			       WLFW_VBATT_REQ_MSG_V01_MAX_MSG_LEN,
+			       wlfw_vbatt_req_msg_v01_ei, &req);
+	if (ret < 0) {
+		qmi_txn_cancel(&txn);
+		goto resched;
+	}
+
+	ret = qmi_txn_wait(&txn, ATH10K_QMI_TIMEOUT * HZ);
+	if (ret)
+		ath10k_dbg(qmi->ar, ATH10K_DBG_QMI, "vbatt send failed: %d\n", ret);
+
+resched:
+	schedule_delayed_work(&qmi->vbatt_work, 5 * HZ);
+}
@@ ath10k_qmi_event_fw_ready_ind() 开头
+	if (qmi->vbatt_probe && !delayed_work_pending(&qmi->vbatt_work))
+		schedule_delayed_work(&qmi->vbatt_work, 0);
@@ ath10k_qmi_event_server_exit() 开头
+	cancel_delayed_work_sync(&qmi->vbatt_work);
@@ ath10k_qmi_probe()/qmi 结构初始化处
+	INIT_DELAYED_WORK(&qmi->vbatt_work, ath10k_qmi_vbatt_work);
+	qmi->vbatt_probe = vbatt_probe;   /* 或同样用 of_property 读 DT */
```

注意：
- `INIT_DELAYED_WORK` 放 `ath10k_qmi_probe`（qmi.c:1135 附近 kzalloc 之后）；模块卸载路径记得 `cancel_delayed_work_sync`。
- 固定 3.7V 探针值对 FW 无害假设基于：stock 侧该消息本来就是"告知性"（host 读 VADC 后发给 FW，FW 不回控制指令）。若想更接近真实，可改读 `/sys/class/power_supply/bq27541-0/voltage_now`——但在电量计冻结修复（任务 B）落地前，固定值反而隔离变量，**推荐固定值**。
- 若 FW 对未知/超频消息敏感（不至于，stock 同一 FW 就有此消息），第一条日志即可看到 resp.result。

## 实验矩阵与判读

| 现象 | 结论 |
|---|---|
| 开 vbatt_probe 后崩溃时序/概率无变化 | VBATT 变量排除，回到 rejuvenate 主线（任务 A 修复 1） |
| 崩溃推迟或消失 | FW 确实依赖电压信息——需要正式实现（对接 pm660/bq27541 真实电压） |
| 打开即崩/异常日志 | FW 对该消息路径有 bug，本身就是发现 |
| dmesg 无 vbatt 相关痕迹 | 探针没跑起来（检查 module param 是否生效：`cat /sys/module/ath10k_snoc/parameters/vbatt_probe`，注意 module_param 挂在 ath10k_snoc 还是 qmi 所在模块名） |

使用：`insmod ath10k_snoc.ko` 后 `echo 1 > /sys/module/ath10k_snoc/parameters/vbatt_probe`（或编入 cmdline `ath10k_snoc.vbatt_probe=1`），关联后观察 ≥5 个周期。
