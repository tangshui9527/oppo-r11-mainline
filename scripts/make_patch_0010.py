import urllib.request
import subprocess
import tempfile
import os

with tempfile.TemporaryDirectory() as d:
    repo = os.path.join(d, 'repo')
    os.makedirs(os.path.join(repo, 'drivers/net/wireless/ath/ath10k'), exist_ok=True)
    subprocess.run(['git', 'init'], cwd=repo, check=True)
    subprocess.run(['git', 'config', 'user.name', 'test'], cwd=repo, check=True)
    subprocess.run(['git', 'config', 'user.email', 'test@test'], cwd=repo, check=True)
    
    files = ['qmi.h', 'core.h', 'snoc.h', 'ce.h', 'hw.h', 'debug.h', 'hif.h', 'htc.h', 'coredump.h', 'qmi.c', 'snoc.c']
    for f in files:
        hurl = f'https://raw.githubusercontent.com/CPH1707-Mainline/linux-sdm660-oppor11-t/r11t/legacy-full-stack/drivers/net/wireless/ath/ath10k/{f}'
        try:
            hcontent = urllib.request.urlopen(urllib.request.Request(hurl, headers={'User-Agent': 'Mozilla/5.0'})).read().decode('utf-8')
            with open(os.path.join(repo, 'drivers/net/wireless/ath/ath10k', f), 'w') as fp:
                fp.write(hcontent)
        except Exception as e:
            print(f, e)

    subprocess.run(['git', 'add', '.'], cwd=repo, check=True)
    subprocess.run(['git', 'commit', '-m', 'initial'], cwd=repo, check=True)

    cur = os.getcwd()
    for p in ['0004-ath10k-qmi-negotiate-fw-rejuvenate.patch', '0006-ath10k-qmi-vbatt-probe.patch', '0008-ath10k-ce-misc-diagnostic-snapshot.patch', '0009-ath10k-qmi-skip-empty-cal-report.patch']:
        p_path = os.path.join(cur, 'patches', p)
        res = subprocess.run(['git', 'apply', p_path], cwd=repo)
        if res.returncode != 0:
            print('Failed applying', p)
            raise SystemExit(1)
    subprocess.run(['git', 'commit', '-a', '-m', 'applied pre-patches'], cwd=repo, check=True)

    # 1. Update qmi.c
    qmi_path = os.path.join(repo, 'drivers/net/wireless/ath/ath10k/qmi.c')
    with open(qmi_path, 'r') as f:
        qmi_src = f.read()

    target1 = 'MODULE_PARM_DESC(skip_bdf_dnld, "skip QMI BDF download (experimental)");\n'
    replace1 = target1 + '''
static int fw_log_mode;
module_param(fw_log_mode, int, 0644);
MODULE_PARM_DESC(fw_log_mode, "QMI FW log mode in msa_ready (0: disable, 1: CE, 2: DIAG, -1: skip)");

static bool force_fw_ready;
module_param(force_fw_ready, bool, 0644);
MODULE_PARM_DESC(force_fw_ready, "force ath10k core register without waiting for FW_READY_IND");

static int force_fw_ready_delay_ms = 1000;
module_param(force_fw_ready_delay_ms, int, 0644);
MODULE_PARM_DESC(force_fw_ready_delay_ms, "delay in ms before forcing FW ready indication (default 1000)");
'''
    assert target1 in qmi_src, 'target1 not found in qmi.c'
    qmi_src = qmi_src.replace(target1, replace1)

    target_cfg = '''\tret = qmi_txn_init(&qmi->qmi_hdl, &txn,
\t\t\t   wlfw_wlan_cfg_resp_msg_v01_ei,
\t\t\t   &resp);
\tif (ret < 0)
\t\tgoto out;

\treq->host_version_valid = 0;'''

    replace_cfg = '''\tint retries = 15;

\treq->host_version_valid = 0;'''
    assert target_cfg in qmi_src, 'target_cfg not found in qmi.c'
    qmi_src = qmi_src.replace(target_cfg, replace_cfg)

    target_send = '''\tret = qmi_send_request(&qmi->qmi_hdl, NULL, &txn,
\t\t\t       QMI_WLFW_WLAN_CFG_REQ_V01,
\t\t\t       WLFW_WLAN_CFG_REQ_MSG_V01_MAX_MSG_LEN,
\t\t\t       wlfw_wlan_cfg_req_msg_v01_ei, req);
\tif (ret < 0) {
\t\tqmi_txn_cancel(&txn);
\t\tath10k_err(ar, "failed to send config request: %d\\n", ret);
\t\tgoto out;
\t}

\tret = qmi_txn_wait(&txn, ATH10K_QMI_TIMEOUT * HZ);
\tif (ret < 0)
\t\tgoto out;

\tif (resp.resp.result != QMI_RESULT_SUCCESS_V01) {
\t\tath10k_err(ar, "config request rejected: %d\\n", resp.resp.error);
\t\tret = -EINVAL;
\t\tgoto out;
\t}'''

    replace_send = '''retry_cfg:
\tret = qmi_txn_init(&qmi->qmi_hdl, &txn,
\t\t\t   wlfw_wlan_cfg_resp_msg_v01_ei,
\t\t\t   &resp);
\tif (ret < 0)
\t\tgoto out;

\tret = qmi_send_request(&qmi->qmi_hdl, NULL, &txn,
\t\t\t       QMI_WLFW_WLAN_CFG_REQ_V01,
\t\t\t       WLFW_WLAN_CFG_REQ_MSG_V01_MAX_MSG_LEN,
\t\t\t       wlfw_wlan_cfg_req_msg_v01_ei, req);
\tif (ret < 0) {
\t\tqmi_txn_cancel(&txn);
\t\tath10k_err(ar, "failed to send config request: %d\\n", ret);
\t\tgoto out;
\t}

\tret = qmi_txn_wait(&txn, ATH10K_QMI_TIMEOUT * HZ);
\tif (ret < 0)
\t\tgoto out;

\tif (resp.resp.result != QMI_RESULT_SUCCESS_V01) {
\t\tif (resp.resp.error == 90 && --retries > 0) {
\t\t\tath10k_info(ar, "qmi config rejected (90, IncompatibleState), retrying in 200ms... (%d left)\\n", retries);
\t\t\tmsleep(200);
\t\t\tgoto retry_cfg;
\t\t}
\t\tath10k_err(ar, "config request rejected: %d\\n", resp.resp.error);
\t\tret = -EINVAL;
\t\tgoto out;
\t}'''
    assert target_send in qmi_src, 'target_send not found in qmi.c'
    qmi_src = qmi_src.replace(target_send, replace_send)

    target_msa = '''\tret = ath10k_qmi_mac_addr_send_sync_msg(qmi);

out:
\treturn;
}'''

    replace_msa = '''\tret = ath10k_qmi_mac_addr_send_sync_msg(qmi);
\tif (ret)
\t\tath10k_dbg(qmi->ar, ATH10K_DBG_QMI, "mac addr msg returned %d\\n", ret);

\tif (fw_log_mode >= 0) {
\t\tret = ath10k_qmi_set_fw_log_mode(qmi->ar, (u8)fw_log_mode);
\t\tif (ret)
\t\t\tath10k_warn(qmi->ar, "failed to set fw log mode %d: %d\\n", fw_log_mode, ret);
\t\telse
\t\t\tath10k_info(qmi->ar, "fw log mode %d set successfully\\n", fw_log_mode);
\t}

\tif (force_fw_ready) {
\t\tif (force_fw_ready_delay_ms > 0) {
\t\t\tath10k_info(qmi->ar, "waiting %d ms before forcing FW ready indication...\\n", force_fw_ready_delay_ms);
\t\t\tmsleep(force_fw_ready_delay_ms);
\t\t}
\t\tath10k_info(qmi->ar, "forcing FW ready indication\\n");
\t\tath10k_snoc_fw_indication(qmi->ar, ATH10K_QMI_EVENT_FW_READY_IND);
\t}

out:
\treturn;
}'''
    assert target_msa in qmi_src, 'target_msa not found in qmi.c'
    qmi_src = qmi_src.replace(target_msa, replace_msa)

    with open(qmi_path, 'w') as f:
        f.write(qmi_src)

    # 2. Update snoc.c
    snoc_path = os.path.join(repo, 'drivers/net/wireless/ath/ath10k/snoc.c')
    with open(snoc_path, 'r') as f:
        snoc_src = f.read()

    target_snoc_pwr = '''\tret = ath10k_hw_power_on(ar);
\tif (ret) {
\t\tath10k_err(ar, "failed to power on device: %d\\n", ret);
\t\treturn ret;
\t}

\tret = ath10k_snoc_wlan_enable(ar, fw_mode);'''

    replace_snoc_pwr = '''\tret = ath10k_hw_power_on(ar);
\tif (ret) {
\t\tath10k_err(ar, "failed to power on device: %d\\n", ret);
\t\treturn ret;
\t}

\tmsleep(100);

\tret = ath10k_snoc_wlan_enable(ar, fw_mode);'''

    assert target_snoc_pwr in snoc_src, 'target_snoc_pwr not found in snoc.c'
    snoc_src = snoc_src.replace(target_snoc_pwr, replace_snoc_pwr)

    with open(snoc_path, 'w') as f:
        f.write(snoc_src)

    diff = subprocess.run(['git', 'diff'], cwd=repo, capture_output=True, text=True, check=True).stdout
    patch_header = '''From: OPPO R11 mainline bringup <r11t@local>
Subject: [PATCH] ath10k: qmi: fix diag starvation, retry config 90, and settle rails

1. Suppress Hexagon DIAG logging (mode 0) during msa_ready to prevent 'Task starvation: diag'.
2. Settle WCN3990 power rails and clocks for 100ms after ath10k_hw_power_on.
3. Automatically retry QMI_WLFW_WLAN_CFG_REQ_V01 on error 90 (IncompatibleState) while FW settles.
4. Add configurable delay (default 1000ms) when force_fw_ready is enabled.

'''
    full_patch = patch_header + diff
    patch_out = os.path.join(cur, 'patches', '0010-ath10k-qmi-fix-diag-starvation.patch')
    with open(patch_out, 'w') as f:
        f.write(full_patch)
    print(f'Wrote patch to {patch_out}')

    # Validate patch apply by reverting working copy first
    subprocess.run(['git', 'checkout', 'drivers/net/wireless/ath/ath10k/qmi.c', 'drivers/net/wireless/ath/ath10k/snoc.c'], cwd=repo, check=True)
    subprocess.run(['git', 'apply', '--check', patch_out], cwd=repo, check=True)
    subprocess.run(['git', 'apply', patch_out], cwd=repo, check=True)
    print('Patch validated cleanly!')
