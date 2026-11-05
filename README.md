# OPPO R11 Mainline Linux Bringup

Mainline Linux 6.12 LTS + USB NCM early-debug environment for the **OPPO R11** (`oppo16051` / Qualcomm Snapdragon 660 / SDM660).

## Hardware Specifications

| Component | Detail |
| :--- | :--- |
| **SoC** | Qualcomm SDM660 (8× Kryo 260) |
| **RAM** | 4GB LPDDR4X |
| **Storage** | 64GB eMMC |
| **Display** | 1080×1920 Samsung S6E3FA3 AMOLED (MIPI DSI Command Mode) |
| **PMIC** | PM660 + PM660A |
| **Board ID** | 0x8 (MTP) / MSM ID: 0x13d (SDM660) |

## Repository Architecture

```
.
├── .github/workflows/
│   └── build.yml              # CI workflow building kernel, DTB, initramfs & boot.img
├── configs/
│   └── r11-extra.config       # Kernel config fragments (USB configfs, simplefb)
├── dts/
│   └── sdm660-oppo-r11.dts    # Upstream board DTS for OPPO R11
├── initramfs/
│   ├── init                   # Early RAM-root init script with USB NCM gadget & telnet
│   ├── build.sh               # Assembles initramfs with Alpine aarch64 busybox
│   └── setup-ncm.sh           # Fallback network rebind script
├── scripts/
│   └── backup-device.sh       # One-click device partition & firmware backup script
├── tools/
│   └── mkbootimg.py           # Android boot header v0 packaging tool
└── OPPO-R11-Mainline-Linux-Plan.md
```

## Quick Start: Testing Early Boot via Fastboot

1. Download `oppo-r11-mainline-boot` artifact from GitHub Actions.
2. Unpack `r11-mainline-boot.img`.
3. Put OPPO R11 into fastboot mode (`adb reboot bootloader`).
4. Boot image into RAM without flashing:
   ```bash
   fastboot boot r11-mainline-boot.img
   ```
5. Configure host USB interface:
   - Interface: NCM / RNDIS
   - Host IP: `172.16.42.2/24`
   - Gateway / Device IP: `172.16.42.1`
6. Connect to root shell:
   ```bash
   telnet 172.16.42.1
   ```
