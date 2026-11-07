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
    for p in ['0004-ath10k-qmi-negotiate-fw-rejuvenate.patch', '0006-ath10k-qmi-vbatt-probe.patch']:
        p_path = os.path.join(cur, 'patches', p)
        subprocess.run(['git', 'apply', p_path], cwd=repo, check=True)
    subprocess.run(['git', 'commit', '-a', '-m', 'applied 0004 and 0006'], cwd=repo, check=True)

    qmi_path = os.path.join(repo, 'drivers/net/wireless/ath/ath10k/qmi.c')
    with open(qmi_path, 'r') as f:
        src = f.read()

    target1 = 'MODULE_PARM_DESC(vbatt_probe, "send periodic VBATT QMI messages (experimental)");\n'
    replace1 = target1 + '''
static bool skip_empty_cal_report = true;
module_param(skip_empty_cal_report, bool, 0644);
MODULE_PARM_DESC(skip_empty_cal_report, "skip QMI cal report request if empty (default: true)");

static bool skip_bdf_dnld;
module_param(skip_bdf_dnld, bool, 0644);
MODULE_PARM_DESC(skip_bdf_dnld, "skip QMI BDF download (experimental)");
'''
    assert target1 in src, 'target1 not found'
    src = src.replace(target1, replace1)

    target2 = '''	ret = qmi_txn_init(&qmi->qmi_hdl, &txn, wlfw_cal_report_resp_msg_v01_ei,
			   &resp);
	if (ret < 0)
		goto out;

	for (i = 0; i < QMI_WLFW_MAX_NUM_CAL_V01; i++) {
		if (qmi->cal_data[i].total_size &&
		    qmi->cal_data[i].data) {
			req.meta_data[j] = qmi->cal_data[i].cal_id;
			j++;
		}
	}
	req.meta_data_len = j;'''

    replace2 = '''	for (i = 0; i < QMI_WLFW_MAX_NUM_CAL_V01; i++) {
		if (qmi->cal_data[i].total_size &&
		    qmi->cal_data[i].data) {
			req.meta_data[j] = qmi->cal_data[i].cal_id;
			j++;
		}
	}
	req.meta_data_len = j;

	if (skip_empty_cal_report && !req.meta_data_len && !req.xo_cal_data_valid) {
		ath10k_dbg(ar, ATH10K_DBG_QMI, "skipping empty cal report request\\n");
		return 0;
	}

	ret = qmi_txn_init(&qmi->qmi_hdl, &txn, wlfw_cal_report_resp_msg_v01_ei,
			   &resp);
	if (ret < 0)
		goto out;'''

    assert target2 in src, 'target2 not found'
    src = src.replace(target2, replace2)

    target3 = '''	ret = ath10k_qmi_bdf_dnld_send_sync(qmi);
	if (ret)
		goto out;'''

    replace3 = '''	if (!skip_bdf_dnld) {
		ret = ath10k_qmi_bdf_dnld_send_sync(qmi);
		if (ret)
			goto out;
	} else {
		ath10k_dbg(qmi->ar, ATH10K_DBG_QMI, "skipping bdf download request\\n");
	}'''

    assert target3 in src, 'target3 not found'
    src = src.replace(target3, replace3)

    with open(qmi_path, 'w') as f:
        f.write(src)

    diff = subprocess.check_output(['git', 'diff'], cwd=repo).decode('utf-8')
    header = '''From: OPPO R11 mainline bringup <r11t@local>
Subject: [PATCH] ath10k: qmi: skip empty cal report request and allow bdf skip

On SDM660 (WCN3990 with integrated MSS modem), calibration data is loaded
directly by the modem via RFSA (memshare client 4) from the modem NV partition.
ath10k_qmi constructs a CAL_REPORT_REQ with meta_data_len=0 and xo_cal_data_valid=0,
which crashes the WCN3990 firmware within 28ms with an SFR watchdog fatal error.
Skip CAL_REPORT_REQ when no calibration data is present (default: true).
Also add skip_bdf_dnld module parameter for runtime flexibility.

'''
    full_patch = header + diff
    out_patch_path = os.path.join(cur, 'patches/0009-ath10k-qmi-skip-empty-cal-report.patch')
    with open(out_patch_path, 'w') as f:
        f.write(full_patch)
    print('Wrote patch to:', out_patch_path)

    # Validate patch
    subprocess.run(['git', 'checkout', '.'], cwd=repo, check=True)
    res = subprocess.run(['git', 'apply', '--check', out_patch_path], cwd=repo)
    print('Validation git apply --check returncode:', res.returncode)
    assert res.returncode == 0, 'Validation failed!'
