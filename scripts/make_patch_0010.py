import urllib.request
import subprocess
import tempfile
import os

url = 'https://raw.githubusercontent.com/CPH1707-Mainline/linux-sdm660-oppor11-t/r11t/legacy-full-stack/drivers/net/wireless/ath/ath10k/qmi.c'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
content = urllib.request.urlopen(req).read().decode('utf-8')

with tempfile.TemporaryDirectory() as d:
    repo = os.path.join(d, 'repo')
    os.makedirs(os.path.join(repo, 'drivers/net/wireless/ath/ath10k'), exist_ok=True)
    subprocess.run(['git', 'init'], cwd=repo, check=True)
    subprocess.run(['git', 'config', 'user.name', 'test'], cwd=repo, check=True)
    subprocess.run(['git', 'config', 'user.email', 'test@test'], cwd=repo, check=True)
    
    for hdr in ['qmi.h', 'core.h', 'snoc.h']:
        hurl = f'https://raw.githubusercontent.com/CPH1707-Mainline/linux-sdm660-oppor11-t/r11t/legacy-full-stack/drivers/net/wireless/ath/ath10k/{hdr}'
        hreq = urllib.request.Request(hurl, headers={'User-Agent': 'Mozilla/5.0'})
        try:
            hcontent = urllib.request.urlopen(hreq).read().decode('utf-8')
            with open(os.path.join(repo, 'drivers/net/wireless/ath/ath10k', hdr), 'w') as f:
                f.write(hcontent)
        except Exception:
            pass

    with open(os.path.join(repo, 'drivers/net/wireless/ath/ath10k/qmi.c'), 'w') as f:
        f.write(content)
    subprocess.run(['git', 'add', '.'], cwd=repo, check=True)
    subprocess.run(['git', 'commit', '-m', 'initial'], cwd=repo, check=True)

    cur = os.getcwd()
    for p in ['0004-ath10k-qmi-negotiate-fw-rejuvenate.patch', '0006-ath10k-qmi-vbatt-probe.patch', '0009-ath10k-qmi-skip-empty-cal-report.patch']:
        p_path = os.path.join(cur, 'patches', p)
        subprocess.run(['git', 'apply', p_path], cwd=repo, check=True)
    subprocess.run(['git', 'commit', '-a', '-m', 'applied up to 0009'], cwd=repo, check=True)

    qmi_path = os.path.join(repo, 'drivers/net/wireless/ath/ath10k/qmi.c')
    with open(qmi_path, 'r') as f:
        src = f.read()

    target1 = 'MODULE_PARM_DESC(skip_bdf_dnld, "skip QMI BDF download (experimental)");\n'
    replace1 = target1 + '''
static int fw_log_mode;
module_param(fw_log_mode, int, 0644);
MODULE_PARM_DESC(fw_log_mode, "QMI FW log mode in msa_ready (0: disable, 1: CE, 2: DIAG, -1: skip)");

static bool force_fw_ready;
module_param(force_fw_ready, bool, 0644);
MODULE_PARM_DESC(force_fw_ready, "force ath10k core register without waiting for FW_READY_IND");
'''
    assert target1 in src, 'target1 not found'
    src = src.replace(target1, replace1)

    target2 = '''\tret = ath10k_qmi_mac_addr_send_sync_msg(qmi);

out:
\treturn;
}'''

    replace2 = '''\tret = ath10k_qmi_mac_addr_send_sync_msg(qmi);
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
\t\tath10k_info(qmi->ar, "forcing FW ready indication\\n");
\t\tath10k_snoc_fw_indication(qmi->ar, ATH10K_QMI_EVENT_FW_READY_IND);
\t}

out:
\treturn;
}'''

    assert target2 in src, 'target2 not found'
    src = src.replace(target2, replace2)

    with open(qmi_path, 'w') as f:
        f.write(src)

    diff = subprocess.run(['git', 'diff'], cwd=repo, capture_output=True, text=True, check=True).stdout
    patch_header = '''From: OPPO R11 mainline bringup <r11t@local>
Subject: [PATCH] ath10k: qmi: fix diag task starvation and add force_fw_ready option

On Qualcomm Hexagon MSS / WCN3990 firmware, FW logging defaults to DIAG mode (mode 2).
Without a host DIAG router consuming the DIAG log stream, the internal DIAG buffer
overflows within seconds, starving the 'diag' task in Hexagon RTOS and triggering a
watchdog reset ('Task starvation: diag, ping: 4').
Send QMI_WLFW_INI_REQ_V01 to set fw_log_mode (default 0: disable) during msa_ready.
Also add force_fw_ready parameter to register the driver core if firmware does not
send asynchronous FW_READY_IND.

'''
    full_patch = patch_header + diff
    patch_out = os.path.join(cur, 'patches', '0010-ath10k-qmi-fix-diag-starvation.patch')
    with open(patch_out, 'w') as f:
        f.write(full_patch)
    print(f'Wrote patch to {patch_out}')

    # Validate patch apply by reverting working copy first
    subprocess.run(['git', 'checkout', 'drivers/net/wireless/ath/ath10k/qmi.c'], cwd=repo, check=True)
    subprocess.run(['git', 'apply', '--check', patch_out], cwd=repo, check=True)
    subprocess.run(['git', 'apply', patch_out], cwd=repo, check=True)
    print('Patch validated cleanly!')
