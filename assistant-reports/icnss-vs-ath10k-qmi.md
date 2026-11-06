# 任务 A：stock ICNSS vs 主线 ath10k_qmi 关联态行为差异分析

设备：OPPO R11 (SDM660 + WCN3990)，主线 Linux (CPH1707-Mainline/linux-sdm660-oppor11-t, r11t/legacy-full-stack)。
故障：Wi-Fi 关联 AP 后 ~5s RX 完全断流，~10-16s MSS 看门狗崩溃（"SFR Init: wdog or kernel error suspected"）。
已排除：路由器差异、TX 功率（10dBm 静默同崩）、数据量、cx/mx proxy 投票、Q6 memory bank 29（已修）、启动期 BDF/MAC/WLAN PD/WLFW 链路。

**源码版本**：
- stock：`YuxuanZuo/android_kernel_oppo_sdm660` @ `KERNEL.LA.UM.7.2.r1-06900-sdm660.0-REL`（下文行号基于 `src-cache/icnss/icnss.c`）
- 主线：CPH1707 树 `drivers/net/wireless/ath/ath10k/qmi.c`（下文 `qmi.c:NNN`）、`ath10k-snoc.c`、`qmi_wlfw_v01.h`

所有源码已缓存于 `~/test/oppo-r11-mainline-workspace/src-cache/icnss/`，行号可直接复核。

---

## 一、结论先行（TL;DR）

1. **stock ICNSS 在稳态（fw_ready 之后）没有任何周期性 timer/workqueue**（全文件 grep `timer_setup/mod_timer/schedule_delayed_work` 仅命中 event work 一个）。"stock 有心跳而 ath10k 没有"的假说**不成立**，可以排除。
2. stock 会做而 ath10k **永远不做**的关键项是 **FW_REJUVENATE（固件自恢复）机制的三件套**：
   - `IND_REGISTER` 里置 `rejuvenate_enable=1`（icnss.c:1384-1387）；
   - 单独发送 `QMI_WLFW_DYNAMIC_FEATURE_MASK_REQ`（0x003B，icnss.c:1928-1985，在 server_arrive 流程 icnss.c:2171 调用），默认 feature mask = `QMI_WLFW_FW_REJUVENATE_V01`（icnss.c:179）；
   - 收到 `REJUVENATE_IND` 后记录 cause，并在 PD service down 时发送 `REJUVENATE_ACK`（icnss.c:1829 / 1883 / 2422-2437）。
   ath10k_qmi 对以上三项均为**零实现**（qmi.c:805-825 的 IND_REGISTER 连字段都没填；qmi_msg_handler 表 qmi.c:1015-1032 只挂了 FW_READY/MSA_READY 两个 indication）。
3. 这是**唯一一个**"固件侧可选、由 host 协商决定行为路径、且在出错时刻（≈关联后数秒）被触发"的差异项，与"~5s 断流 → ~10-16s 看门狗"的时间线吻合度最高（机制推演见 §三）。
4. HANDOVER 中怀疑的 **VBATT/VPH 监控可以降级**：stock 默认 quirks = `BIT(VBATT_DISABLE) | BIT(FW_REJUVENATE_ENABLE)`（icnss.c:173-176），即 **R11 stock 默认根本不发 VBATT**；且 stock DTS 的 icnss 节点（sdm660.dtsi:1979-2011）没有 vadc/adc_tm iio 通道，`icnss_init_vph_monitor()` 即使 quirks 放开也会因 `adc_tm_dev==NULL` 失败（icnss.c:4456-4482）。两块板行为一致，不构成差异。
5. MSA 内存与权限两侧完全一致（区域 0x85600000 guard + 0x85700000 msa 各 1MB；VMID 集合 `{MSS_MSA, WLAN}` + 非安全加 `WLAN_CE`，icnss.c:224-260 vs qmi.c:41-65），排除该方向。
6. `qmi_wlfw_v01.h`（CPH1707 树内）**已经包含** rejuvenate / dynamic_feature_mask / pin_connect 全部消息定义与 ei 数组（qmi_wlfw_v01.h:37-38, 48, 52, 125, 202-213），修复只需改 `qmi.c`，无需移植消息定义——补丁成本很低。

---

## 二、差异清单

| # | stock ICNSS 行为 | 主线 ath10k_qmi 行为 | 源码证据 (stock / ath10k) | 与崩溃关联度 |
|---|---|---|---|---|
| 1 | IND_REGISTER 置 `rejuvenate_enable=1`，向 FW 声明 host 支持固件自恢复 | 只填 client_id/fw_ready/msa_ready（+可选 xo_cal），无 rejuvenate 字段 | icnss.c:1375-1387 / qmi.c:805-824 | **高**：改变 FW 出错时的行为路径 |
| 2 | server_arrive 后发 `DYNAMIC_FEATURE_MASK`，默认 mask=`FW_REJUVENATE` | 完全不发送（消息处理表里无此 msg_id） | icnss.c:179, 1928-1985, 2171 / qmi_wlfw_v01.h:15,38（定义在但没人用） | **高**：与 #1 同一机制的第二个开关 |
| 3 | `REJUVENATE_IND` 解码（cause/subsystem/line/function）+ PD down 时发 `REJUVENATE_ACK` 触发 FW 自恢复重启 | 无此 indication 处理；server_exit 仅做 ath10k_core_unregister + 释放 MSA 权限 | icnss.c:1829-1881, 1883-1926, 2422-2437 / qmi.c:950-963, 1015-1032 | **高**：不出错时无感知，出错时决定"自愈 vs 死亡" |
| 4 | IND_REGISTER 置 `pin_connect_result_enable=1` 并处理 `PIN_CONNECT_RESULT_IND`（WCN3990 引脚连接结果回告） | 两者皆无 | icnss.c:1382-1383, 898-936 / qmi.c:805-824 | 中低：多数 FW 版本容忍缺省；失败时一般仅打日志 |
| 5 | VBATT：读 VADC VPH_PWR 并按 1s ADC_TM 阈值监控、越限发 `QMI_WLFW_VBATT_REQ`(0x0032) | 无任何电压上报 | icnss.c:712-757, 761-871, 877-891 / （无） | **低**：stock 默认 `VBATT_DISABLE`（icnss.c:173-176）且 DT 无 iio 通道（sdm660.dtsi:1979-2011），R11 上 stock 也不发 → 非差异 |
| 6 | 发 `QMI_WLFW_CAP_REQ`(0x0024) 获取 chip/fw 版本信息 | 同样发 CAP（qmi.c:860-871 流程内），另额外发 `HOST_CAP`(`daemon_support=0`) | icnss.c:1404-1452 / qmi.c:707-753 | 低：HOST_CAP 是新协议消息，旧 FW 回 NOT_SUPPORTED 也被容忍（qmi.c:745-750），方向无冲突 |
| 7 | 卸载/测试模式用 `QMI_WLFW_SHUTDOWN_REQ`(0x0021)；正常 off 用 WLAN_MODE off | 只用 WLAN_MODE off | icnss.c:1670-1690, 3329-3355 / qmi.c:920-955 区域 | 低：稳态不触发 |
| 8 | ATHDIAG read/write（debugfs 通道，QCA 驱动调试用） | 无（qmi_wlfw_v01.h 有 ATHDIAG_WRITE 定义） | icnss.c（ATHDIAG 消息族）/ （无） | 低：仅调试路径 |
| 9 | SSR：完整 PD restart 状态机（`PD_SERVICE_DOWN` 事件、`pd_restart_complete`、uevent FW_CRASHED、`ICNSS_QMI_ASSERT` 兜底） | server_exit → core_unregister；server 重新 arrive → 全量重初始化（MSA 权限重授等）。无 rejuvenate 区分 | icnss.c:2269-2316, 2422-2500 / qmi.c:950-963, 862-948 | 中：即使触发自恢复，恢复路径质量也不同；是 #1-#3 的放大器 |
| 10 | 周期性 timer/workqueue | **两侧都无**（stock 仅 event work；ath10k 仅 event_work） | icnss.c:4665-4666 / qmi.c:1164 | 无差异：**"缺心跳"假说排除** |
| 11 | MSA 权限（SCM VMID 授予）| 相同集合 | icnss.c:224-260 / qmi.c:41-65 | 无差异；DT 区域地址也一致（sdm660.dtsi:322-331 vs r11t dts wlan-msa-mem@85700000） |
| 12 | fw_ready 后立即 `icnss_hw_power_off()` 释放 proxy（icnss.c:2318-2338） | ath10k snoc 侧保持 regulator/时钟由 snoc 管理 | icnss.c:2325 / ath10k-snoc.c:1106 | 用户已实测 proxy 投票保持无异常，不评估 |

---

## 三、机制推演：为什么是"关联后 ~5s 断流，~10-16s MSS 看门狗"

### 已被源码排除的假说
- **缺周期性心跳/vbatt**：stock 稳态无 timer（#10），VBATT 默认关闭（#5）。
- **MSA 内存/权限错配**：区域地址、大小、guard、VMID 完全一致（#11）。
- **proxy 供电投票**：用户实测保持（背景已排除）。

### 主假说（候选 1）：缺 FW_REJUVENATE 协商 → FW 出错走不可恢复路径

推理链：
1. LA.UM.7.2 世代 WCN3990 FW 内置 rejuvenate 能力：当 FW 检测到内部资源耗尽/状态机卡死（cause 会在 IND 里带出，stock 打印 `Cause for rejuvenation / requesting_sub_system / line_number / function_name`，icnss.c:1864-1868——**`requesting_sub_system` 字段本身说明 FW 侧可能代表其它子系统发起**），向 host 发 `REJUVENATE_IND`，等 host 回 `REJUVENATE_ACK` 后自杀重启、QMI 服务重新上线，host 走 PD restart 流程衔接。
2. stock 协商（IND_REGISTER + DYNAMIC_FEATURE_MASK）告诉 FW "支持 rejuvenate"，FW 出错时走自恢复路径。
3. 主线 ath10k 从不协商 → FW 的 rejuvenate 分支被禁用（或 IND 发出无人理会/无人 ACK）。当关联后数秒 FW 首次触发该内部错误（数据面刚转起来、FW 内部周期性任务开始满负荷），FW 走**硬故障路径**：先表现为 CE 数据面停止 → **RX 断流（~5s）**；随后 FW 侧/其依赖链超时升级 → QMI 服务消失 → 在本平台上最终表现为 **MSS 报 wdog（~10-16s）**。
4. 与"10dBm 静默无数据同崩"兼容：触发条件不是流量大小，而是 FW 内部状态机在关联后进入的阶段（静默关联同样会推进该状态机）。
5. **注意**：第 3 步"FW 硬故障 → MSS wdog"的跨子系统传导路径是**推测**（WCN3990 FW 与 MSS 的共享依赖——XO 校准链路 `requesting_sub_system`、或 modem↔WLAN glink 依赖——均无法从这两份驱动源码直接证实）。但"协商缺失使 FW 出错时从自愈变为死亡"这半段是源码可直接证实的。

### 次假说（候选 2 的兜底解释）
即使 rejuvenate 不是根因，#1-#3 的补丁也会带来**免费的诊断增强**：FW 一旦出错，主线内核 dmesg 将打印 cause/line/function（stock 能看到而主线现在完全静默），可直接证伪/证实本报告。

---

## 四、Top 3 候选修复（按"最可能解释崩溃"排序）

### 修复 1（首选）：移植 FW_REJUVENATE 协商三件套到 ath10k qmi.c

好消息：`qmi_wlfw_v01.h/.c` 已有全部定义（`wlfw_rejuvenate_ind_msg_v01_ei`、`wlfw_rejuvenate_ack_req_msg_v01_ei`、`wlfw_dynamic_feature_mask_req_msg_v01_ei`、`wlfw_ind_register_req_msg_v01_ei` 里的 rejuvenate_enable 字段），只需改 `drivers/net/wireless/ath/ath10k/qmi.c`。

补丁草案（对 qmi.c 现有结构）：

```diff
--- a/drivers/net/wireless/ath/ath10k/qmi.c
+++ b/drivers/net/wireless/ath/ath10k/qmi.c
@@ struct ath10k_qmi {
 	bool fw_ready;
 	bool no_msa_ready_indicator;
+	bool rejuvenate_pending;	/* REJUVENATE_IND seen, ACK pending */
@@ ath10k_qmi_ind_register_send_sync_msg()
 	req.msa_ready_enable_valid = 1;
 	req.msa_ready_enable = 1;
+	req.rejuvenate_enable_valid = 1;
+	req.rejuvenate_enable = 1;
+	req.pin_connect_result_enable_valid = 1;
+	req.pin_connect_result_enable = 1;
@@ 新函数（放在 host_cap 之后）
+static int ath10k_qmi_dynamic_feature_mask_send_sync(struct ath10k_qmi *qmi)
+{
+	struct wlfw_dynamic_feature_mask_req_msg_v01 req = {};
+	struct wlfw_dynamic_feature_mask_resp_msg_v01 resp = {};
+	struct qmi_txn txn;
+	int ret;
+
+	req.mask_valid = 1;
+	req.mask = QMI_WLFW_FW_REJUVENATE_V01;
+
+	ret = qmi_txn_init(&qmi->qmi_hdl, &txn,
+			   wlfw_dynamic_feature_mask_resp_msg_v01_ei, &resp);
+	if (ret < 0)
+		return ret;
+
+	ret = qmi_send_request(&qmi->qmi_hdl, NULL, &txn,
+			       QMI_WLFW_DYNAMIC_FEATURE_MASK_REQ_V01,
+			       WLFW_DYNAMIC_FEATURE_MASK_REQ_MSG_V01_MAX_MSG_LEN,
+			       wlfw_dynamic_feature_mask_req_msg_v01_ei, &req);
+	if (ret < 0) {
+		qmi_txn_cancel(&txn);
+		return ret;
+	}
+	ret = qmi_txn_wait(&txn, ATH10K_QMI_TIMEOUT * HZ);
+	if (ret < 0)
+		return ret;
+
+	ath10k_info(qmi->ar, "dynamic feature mask: prev 0x%llx curr 0x%llx\n",
+		    resp.prev_mask, resp.curr_mask);
+	return 0;	/* 旧 FW 回 NOT_SUPPORTED 时宽容处理 */
+}
@@ event_server_arrive()，ath10k_qmi_cap_send_sync_msg() 之后：
+	ret = ath10k_qmi_dynamic_feature_mask_send_sync(qmi);
+	if (ret && ret != -ENOTSUPP)
+		ath10k_dbg(ar, ATH10K_DBG_QMI,
+			   "dynamic feature mask rejected: %d\n", ret);
@@ 新 indication 回调 + handler 表项：
+static void ath10k_qmi_rejuvenate_ind(struct qmi_handle *qmi_hdl,
+				      struct sockaddr_qrtr *sq,
+				      struct qmi_txn *txn, const void *data)
+{
+	struct ath10k_qmi *qmi = container_of(qmi_hdl, struct ath10k_qmi, qmi_hdl);
+	const struct wlfw_rejuvenate_ind_msg_v01 *ind = data;
+
+	ath10k_info(qmi->ar, "fw rejuvenate: cause 0x%x subsystem 0x%x line %u func %s\n",
+		    ind->cause_for_rejuvenation, ind->requesting_sub_system,
+		    ind->line_number, ind->function_name);
+	qmi->rejuvenate_pending = true;
+}
+
 static const struct qmi_msg_handler qmi_msg_handler[] = {
 	{ ... FW_READY ... },
 	{ ... MSA_READY ... },
+	{
+		.type = QMI_INDICATION,
+		.msg_id = QMI_WLFW_REJUVENATE_IND_V01,
+		.ei = wlfw_rejuvenate_ind_msg_v01_ei,
+		.decoded_size = sizeof(struct wlfw_rejuvenate_ind_msg_v01),
+		.fn = ath10k_qmi_rejuvenate_ind,
+	},
 	{}
 };
@@ event_server_exit() 开头（对齐 stock：PD down 后 ACK）：
+	if (qmi->rejuvenate_pending) {
+		struct wlfw_rejuvenate_ack_req_msg_v01 req = {};
+		struct wlfw_rejuvenate_ack_resp_msg_v01 resp = {};
+		struct qmi_txn txn;
+
+		if (!qmi_txn_init(&qmi->qmi_hdl, &txn,
+				  wlfw_rejuvenate_ack_resp_msg_v01_ei, &resp)) {
+			if (!qmi_send_request(&qmi->qmi_hdl, NULL, &txn,
+					      QMI_WLFW_REJUVENATE_ACK_REQ_V01,
+					      WLFW_REJUVENATE_ACK_REQ_MSG_V01_MAX_MSG_LEN,
+					      wlfw_rejuvenate_ack_req_msg_v01_ei, &req))
+				qmi_txn_wait(&txn, ATH10K_QMI_TIMEOUT * HZ);
+			else
+				qmi_txn_cancel(&txn);
+		}
+		qmi->rejuvenate_pending = false;
+	}
```

注意点：
- stock 的 ACK 时机是 **PD service down 之后**（icnss.c:2422-2437），即 FW 已经撤下 QMI 服务。若 ACK 必须经 QMI 送达，需改在 `new_server` 后对上一轮 pending ACK（伪代码按"exit 前尽力发送 + FW 重启后 server 重新 arrive 再全量重初始化"处理；若实测发现 FW 不收 exit 前的 ACK，则把 ACK 挪到 `event_server_arrive` 开头发送）。
- `resp.prev_mask/curr_mask` 字段名以树内 `qmi_wlfw_v01.h` 实际结构为准。

**验证方法**：
1. 复现原崩溃：看 dmesg 是否出现 `fw rejuvenate: cause ...`（若出现 → 直接拿到 cause/subsystem/line/function，根因定位跳到 FW 侧错误点）；
2. 若打了 rejuvenate 但仍 MSS 崩溃 → 说明 rejuvenate 生效但恢复衔接失败，转向修 SSR 衔接（候选 3）；
3. 若不再崩溃且稳定关联 >5min → 根因坐实。

### 修复 2（低成本并行加）：pin_connect_result_enable + IND 日志

上面 diff 已包含（IND_REGISTER 两行 + 无需处理函数，先只打日志）。WCN3990 的 pin connect 结果若 FW 在等 host 确认，日志立即可见。与修复 1 同一提交或独立小补丁。

### 修复 3（若 1/2 后仍崩）：SSR 衔接 + 实验性 VBATT 探针

- ath10k `event_server_exit` 目前无条件 `ath10k_core_unregister`；FW 短暂重启（rejuvenate 造成的服务闪断）会被当成彻底退出，重连后 MSA 权限重授（SCM 调用）与 core_register 竞态可能二次引爆。伪代码：在 `fw_ready` 后的 re-arrive 路径加"若距离 del_server < 5s 且 rejuvenate_pending 曾置位 → 快速路径（跳过 SCM 权限重授，只重发 ind_register/cap）"。
- 实验性 VBATT 探针（对照 stock 唯一未被本地复现的功能面）：加模块参数 `ath10k_qmi.vbatt_probe=1`，fw_ready 后每 5s 发一条 `QMI_WLFW_VBATT_REQ` 固定 3.7V。若崩溃时序改变 → FW 确实在等电压信息，再补正式实现。**标注：stock R11 默认不发 VBATT，此项仅为实验变量**。

---

## 五、证据可信度标注

| 结论 | 状态 |
|---|---|
| stock 无稳态周期 timer | 源码证实（grep 全文件） |
| stock 默认 VBATT_DISABLE、DT 无 iio 通道 | 源码证实（icnss.c:173-176, sdm660.dtsi:1979-2011） |
| ath10k 不发 DYNAMIC_FEATURE_MASK / 不协商 rejuvenate / 无 REJUVENATE_IND handler | 源码证实（qmi.c:805-824, 1015-1032, 消息全集对比） |
| qmi_wlfw_v01.h 已含所需消息定义 | 源码证实（qmi_wlfw_v01.h:15,37,38,48,52,125,202-213） |
| MSA 区域/权限一致 | 源码证实（含 workspace dts 复核） |
| "缺 rejuvenate → FW 硬故障 → MSS wdog" 传导机制 | **推测**（前半段证实，跨子系统传导待修复 1 的日志验证） |
| 5s/10s 时间线与 FW 关联后状态机推进的对应 | 推测（与"静默同崩"现象兼容） |

## 六、给用户的下一步

1. 打修复 1+2 的补丁，重编 ath10k 模块，关联后等 60s；
2. 无论如何先 `dmesg | grep -i rejuvenate`；
3. 若拿不到 rejuvenate 打印但崩溃时序改变（如从 10s 变 16s 或不再崩），把 dmesg 全量贴回，按 §四.修复 3 继续。
