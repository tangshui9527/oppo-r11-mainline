# OPPO R11 Mainline Linux & Arch Linux ARM Bringup

Mainline Linux 7.0.9 + Native **Arch Linux ARM aarch64** root filesystem for the **OPPO R11** (`oppo16051` / `CPH1707` / Qualcomm Snapdragon 660 / SDM660).

## Hardware Specifications

| Component | Detail |
| :--- | :--- |
| **Device Model** | OPPO R11 / R11t (`oppo16051`, `CPH1707`) |
| **SoC** | Qualcomm SDM660 (8× Kryo 260) |
| **RAM** | 4GB LPDDR4X |
| **Storage** | 64GB eMMC (`/dev/mmcblk1`) |
| **Display** | 1080×1920 Samsung S6E3FA3 AMOLED (MIPI DSI Command Mode) — **Verified Working** |
| **PMIC** | PM660 + PM660A |
| **Board ID** | `0x8 0 0x3eb3` (16051) / MSM ID: `0x13d 0x0` (SDM660) |

---

## Critical OPPO SDM660 ABL Requirements

1. **Android Boot Image Header Version 1**:
   * Stock ABL requires Android Boot Header v1 with valid `os_version` (`9.0.0`) and `os_patch_level` (`2019-09`).
   * Boot base: `0x80000000`, Kernel offset: `0x00008000`, Ramdisk offset: `0x03000000`, Tags offset: `0x00000100`.
   * Packager: `tools/mkbootimg_v1.py`.
2. **Appended DTB**:
   * DTB must be appended directly to the kernel binary (`cat Image.gz dtb > Image.gz-dtb`) with `dt_size = 0` in header.
3. **TrustZone Secure Gap (Critical Anti-EDL Fix)**:
   * OPPO R11 TrustZone reserves `0x89500000` (size `0x1700000`). If Linux allocates memory in this range, TrustZone triggers a hard panic dropping the device into Qualcomm EDL mode (`QUSB_BULK 05c6:900e`).
   * Ramdisk must load at `0x83000000` and must never cross `0x85600000`.
4. **Flashing vs Boot**:
   * Stock ABL disables `fastboot boot`. Images must be flashed directly via `fastboot flash boot <image>`.

---

## Repository Structure

```text
.
├── .github/workflows/
│   └── build.yml              # CI workflow building kernel, DTB, modules & boot image
├── configs/
│   └── r11-extra.config       # Kernel config fragments (USB configfs, DRM, Devtmpfs)
├── dts/
│   └── sdm660-oppo-r11t.dts   # Upstream board DTS with TrustZone gap & board-id fix
├── initramfs/
│   ├── init                   # Early RAM-root init script
│   └── build.sh               # Initramfs packaging script
├── scripts/
│   └── backup-device.sh       # One-click device partition & firmware backup script
├── tools/
│   ├── img2simg.py            # Android sparse image converter
│   ├── mkbootimg_v1.py        # Android Boot Header Version 1 packager
│   └── phone_exec.py          # POSIX USB serial console runner
└── README.md
```

---

## Fastboot Deployment Guide

### 1. Boot Partition (Mainline Kernel + Early Initramfs)
```bash
fastboot flash boot out_cph1707/oppo-r11-cph1707-boot/boot-r11t-arch.img
```

### 2. Userdata Partition (Arch Linux ARM Rootfs)
```bash
# Convert raw rootfs image to Android sparse format
python3 tools/img2simg.py arch_rootfs.img arch_rootfs.simg

# Flash sparse rootfs to userdata
fastboot flash userdata arch_rootfs.simg
```

### 3. Reboot into Native Linux
```bash
fastboot reboot
```
The device boots directly into Arch Linux ARM with console output active on the 1080p AMOLED display!
