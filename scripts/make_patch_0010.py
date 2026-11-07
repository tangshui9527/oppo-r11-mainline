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

    # 1. Update snoc.h
    snoc_h_path = os.path.join(repo, 'drivers/net/wireless/ath/ath10k/snoc.h')
    with open(snoc_h_path, 'r') as f:
        snoc_h_src = f.read()

    target_snoc_flags = '''enum ath10k_snoc_flags {
\tATH10K_SNOC_FLAG_REGISTERED,
\tATH10K_SNOC_FLAG_UNREGISTERING,
\tATH10K_SNOC_FLAG_MODEM_STOPPED,
\tATH10K_SNOC_FLAG_RECOVERY,
\tATH10K_SNOC_FLAG_8BIT_HOST_CAP_QUIRK,
};'''

    replace_snoc_flags = '''enum ath10k_snoc_flags {
\tATH10K_SNOC_FLAG_REGISTERED,
\tATH10K_SNOC_FLAG_UNREGISTERING,
\tATH10K_SNOC_FLAG_MODEM_STOPPED,
\tATH10K_SNOC_FLAG_RECOVERY,
\tATH10K_SNOC_FLAG_8BIT_HOST_CAP_QUIRK,
\tATH10K_SNOC_FLAG_POWERED_ON,
};'''
    assert target_snoc_flags in snoc_h_src, 'target_snoc_flags not found'
    snoc_h_src = snoc_h_src.replace(target_snoc_flags, replace_snoc_flags)
    with open(snoc_h_path, 'w') as f:
        f.write(snoc_h_src)

    # 2. Update snoc.c
    snoc_c_path = os.path.join(repo, 'drivers/net/wireless/ath/ath10k/snoc.c')
    with open(snoc_c_path, 'r') as f:
        snoc_c_src = f.read()

    target_pwr_funcs = '''static int ath10k_hw_power_on(struct ath10k *ar)
{
\tstruct ath10k_snoc *ar_snoc = ath10k_snoc_priv(ar);
\tint ret;

\tath10k_dbg(ar, ATH10K_DBG_SNOC, "soc power on\\n");

\tret = pwrseq_power_on(ar_snoc->pwrseq);
\tif (ret)
\t\treturn ret;

\tret = regulator_bulk_enable(ar_snoc->num_vregs, ar_snoc->vregs);
\tif (ret)
\t\tgoto pwrseq_off;

\tret = clk_bulk_prepare_enable(ar_snoc->num_clks, ar_snoc->clks);
\tif (ret)
\t\tgoto vreg_off;

\treturn ret;

vreg_off:
\tregulator_bulk_disable(ar_snoc->num_vregs, ar_snoc->vregs);
pwrseq_off:
\tpwrseq_power_off(ar_snoc->pwrseq);

\treturn ret;
}

static int ath10k_hw_power_off(struct ath10k *ar)
{
\tstruct ath10k_snoc *ar_snoc = ath10k_snoc_priv(ar);
\tint ret_seq = 0;
\tint ret_vreg;

\tath10k_dbg(ar, ATH10K_DBG_SNOC, "soc power off\\n");

\tclk_bulk_disable_unprepare(ar_snoc->num_clks, ar_snoc->clks);

\tret_vreg = regulator_bulk_disable(ar_snoc->num_vregs, ar_snoc->vregs);

\tif (ar_snoc->pwrseq)
\t\tret_seq = pwrseq_power_off(ar_snoc->pwrseq);

\treturn ret_vreg ? : ret_seq;
}'''

    replace_pwr_funcs = '''static int ath10k_hw_power_on(struct ath10k *ar)
{
\tstruct ath10k_snoc *ar_snoc = ath10k_snoc_priv(ar);
\tint ret;

\tif (test_bit(ATH10K_SNOC_FLAG_POWERED_ON, &ar_snoc->flags))
\t\treturn 0;

\tath10k_info(ar, "soc power on (enabling regulators & clocks)\\n");

\tret = pwrseq_power_on(ar_snoc->pwrseq);
\tif (ret)
\t\treturn ret;

\tret = regulator_bulk_enable(ar_snoc->num_vregs, ar_snoc->vregs);
\tif (ret)
\t\tgoto pwrseq_off;

\tret = clk_bulk_prepare_enable(ar_snoc->num_clks, ar_snoc->clks);
\tif (ret)
\t\tgoto vreg_off;

\tset_bit(ATH10K_SNOC_FLAG_POWERED_ON, &ar_snoc->flags);
\treturn 0;

vreg_off:
\tregulator_bulk_disable(ar_snoc->num_vregs, ar_snoc->vregs);
pwrseq_off:
\tpwrseq_power_off(ar_snoc->pwrseq);

\treturn ret;
}

static int ath10k_hw_power_off(struct ath10k *ar)
{
\tstruct ath10k_snoc *ar_snoc = ath10k_snoc_priv(ar);
\tint ret_seq = 0;
\tint ret_vreg;

\tif (!test_bit(ATH10K_SNOC_FLAG_POWERED_ON, &ar_snoc->flags))
\t\treturn 0;

\tath10k_info(ar, "soc power off (disabling regulators & clocks)\\n");
\tclear_bit(ATH10K_SNOC_FLAG_POWERED_ON, &ar_snoc->flags);

\tclk_bulk_disable_unprepare(ar_snoc->num_clks, ar_snoc->clks);

\tret_vreg = regulator_bulk_disable(ar_snoc->num_vregs, ar_snoc->vregs);

\tif (ar_snoc->pwrseq)
\t\tret_seq = pwrseq_power_off(ar_snoc->pwrseq);

\treturn ret_vreg ? : ret_seq;
}'''
    assert target_pwr_funcs in snoc_c_src, 'target_pwr_funcs not found'
    snoc_c_src = snoc_c_src.replace(target_pwr_funcs, replace_pwr_funcs)

    target_probe_pwr = '''\tret = ath10k_setup_msa_resources(ar, msa_size);
\tif (ret) {
\t\tath10k_warn(ar, "failed to setup msa resources: %d\\n", ret);
\t\tgoto err_free_irq;
\t}

\tret = ath10k_fw_init(ar);'''

    replace_probe_pwr = '''\tret = ath10k_setup_msa_resources(ar, msa_size);
\tif (ret) {
\t\tath10k_warn(ar, "failed to setup msa resources: %d\\n", ret);
\t\tgoto err_free_irq;
\t}

\tret = ath10k_hw_power_on(ar);
\tif (ret) {
\t\tath10k_err(ar, "failed to power on hardware during probe: %d\\n", ret);
\t\tgoto err_free_irq;
\t}

\tret = ath10k_fw_init(ar);'''
    assert target_probe_pwr in snoc_c_src, 'target_probe_pwr not found'
    snoc_c_src = snoc_c_src.replace(target_probe_pwr, replace_probe_pwr)

    target_free_res = '''static int ath10k_snoc_free_resources(struct ath10k *ar)
{
\tstruct ath10k_snoc *ar_snoc = ath10k_snoc_priv(ar);

\tath10k_dbg(ar, ATH10K_DBG_SNOC, "snoc free resources\\n");

\tset_bit(ATH10K_SNOC_FLAG_UNREGISTERING, &ar_snoc->flags);

\tath10k_core_unregister(ar);
\tath10k_fw_deinit(ar);'''

    replace_free_res = '''static int ath10k_snoc_free_resources(struct ath10k *ar)
{
\tstruct ath10k_snoc *ar_snoc = ath10k_snoc_priv(ar);

\tath10k_dbg(ar, ATH10K_DBG_SNOC, "snoc free resources\\n");

\tset_bit(ATH10K_SNOC_FLAG_UNREGISTERING, &ar_snoc->flags);

\tath10k_core_unregister(ar);
\tath10k_fw_deinit(ar);
\tath10k_hw_power_off(ar);'''
    assert target_free_res in snoc_c_src, 'target_free_res not found'
    snoc_c_src = snoc_c_src.replace(target_free_res, replace_free_res)

    with open(snoc_c_path, 'w') as f:
        f.write(snoc_c_src)

    # 3. Update qmi.c
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

static bool skip_qmi_cfg;
module_param(skip_qmi_cfg, bool, 0644);
MODULE_PARM_DESC(skip_qmi_cfg, "skip or bypass QMI WLAN CFG request if rejected (default false)");
'''
    assert target1 in qmi_src, 'target1 not found in qmi.c'
    qmi_src = qmi_src.replace(target1, replace1)

    target_cfg_resp = '''\tif (resp.resp.result != QMI_RESULT_SUCCESS_V01) {
\t\tath10k_err(ar, "config request rejected: %d\\n", resp.resp.error);
\t\tret = -EINVAL;
\t\tgoto out;
\t}'''

    replace_cfg_resp = '''\tif (resp.resp.result != QMI_RESULT_SUCCESS_V01) {
\t\tif (resp.resp.error == 90 || skip_qmi_cfg) {
\t\t\tath10k_warn(ar, "qmi config rejected (%d), bypassing config as optional for mission mode\\n", resp.resp.error);
\t\t\tret = 0;
\t\t\tgoto out;
\t\t}
\t\tath10k_err(ar, "config request rejected: %d\\n", resp.resp.error);
\t\tret = -EINVAL;
\t\tgoto out;
\t}'''
    assert target_cfg_resp in qmi_src, 'target_cfg_resp not found in qmi.c'
    qmi_src = qmi_src.replace(target_cfg_resp, replace_cfg_resp)

    target_wlan_enable = '''\tret = ath10k_qmi_cfg_send_sync_msg(ar, config, version);
\tif (ret) {
\t\tath10k_err(ar, "failed to send qmi config: %d\\n", ret);
\t\treturn ret;
\t}

\tret = ath10k_qmi_mode_send_sync_msg(ar, mode);
\tif (ret) {
\t\tath10k_err(ar, "failed to send qmi mode: %d\\n", ret);
\t\treturn ret;
\t}'''

    replace_wlan_enable = '''\tif (!skip_qmi_cfg) {
\t\tret = ath10k_qmi_cfg_send_sync_msg(ar, config, version);
\t\tif (ret) {
\t\t\tath10k_err(ar, "failed to send qmi config: %d\\n", ret);
\t\t\treturn ret;
\t\t}
\t} else {
\t\tath10k_info(ar, "skipping qmi config request per module param\\n");
\t}

\tret = ath10k_qmi_mode_send_sync_msg(ar, mode);
\tif (ret) {
\t\tif (skip_qmi_cfg) {
\t\t\tath10k_warn(ar, "mode request returned %d, ignoring per skip_qmi_cfg to proceed to CE pipes\\n", ret);
\t\t\treturn 0;
\t\t}
\t\tath10k_err(ar, "failed to send qmi mode: %d\\n", ret);
\t\treturn ret;
\t}'''
    assert target_wlan_enable in qmi_src, 'target_wlan_enable not found in qmi.c'
    qmi_src = qmi_src.replace(target_wlan_enable, replace_wlan_enable)

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

    diff = subprocess.run(['git', 'diff'], cwd=repo, capture_output=True, text=True, check=True).stdout
    patch_header = '''From: OPPO R11 mainline bringup <r11t@local>
Subject: [PATCH] ath10k: power on hardware early during probe, handle cfg error 90, and suppress diag starvation

1. Early hardware power-on: In downstream Qualcomm kernels (icnss.c), WCN3990
   regulators (0.8V cx/mx, 1.8V xo, 1.3V rfa, 3.3V ch0) and RF reference clock
   are powered on BEFORE QMI communication so Hexagon modem firmware can detect
   and calibrate the WCN3990 chip and send QMI_WLFW_FW_READY_IND_V01.
   Make ath10k_hw_power_on idempotent and call it early in ath10k_snoc_probe.
2. Graceful CFG 90 bypass: If Hexagon firmware rejects QMI_WLFW_WLAN_CFG_REQ_V01
   with error 90 (IncompatibleState), bypass it and proceed to WLAN mode request,
   matching downstream icnss behavior.
3. Suppress Hexagon DIAG logging (fw_log_mode=0) to prevent 'Task starvation: diag'.
4. Retain force_fw_ready parameter with configurable delay as a fallback.

'''
    full_patch = patch_header + diff
    patch_out = os.path.join(cur, 'patches', '0010-ath10k-qmi-fix-diag-starvation.patch')
    with open(patch_out, 'w') as f:
        f.write(full_patch)
    print(f'Wrote patch to {patch_out}')

    # Validate patch apply by reverting working copy first
    subprocess.run(['git', 'checkout', 'drivers/net/wireless/ath/ath10k/snoc.h', 'drivers/net/wireless/ath/ath10k/snoc.c', 'drivers/net/wireless/ath/ath10k/qmi.c'], cwd=repo, check=True)
    subprocess.run(['git', 'apply', '--check', patch_out], cwd=repo, check=True)
    subprocess.run(['git', 'apply', patch_out], cwd=repo, check=True)
    print('Patch validated cleanly!')
