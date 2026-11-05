# OPPO R11 刷入主线 Linux 完整规划方案

> **文档生成日期:** 2026-11-05
> **设备:** OPPO R11 (序列号: REDACTED_SERIAL)

---

## 一、设备信息采集结果

| 项目 | 值 |
|------|-----|
| **型号** | OPPO R11 (codename: `R11`, 内部代号: `oppo16051`) |
| **SoC** | Qualcomm SDM660 (Snapdragon 660) |
| **CPU** | 8核 Kryo 260 — 4× Gold (0x801) + 4× Silver (0x800), AArch64 |
| **RAM** | ~3.8 GB (3,800,496 KB) |
| **存储** | 64GB eMMC (`mmcblk0`, 约 58GB 可用) |
| **显示屏** | 1080×1920 @ 60Hz, Samsung S6E3FA3 AMOLED (DSI CMD 模式) |
| **PMIC** | PM660 + PM660A |
| **DT Compatible** | `qcom,sdm660-mtp` / `qcom,sdm660` / `qcom,mtp` |
| **当前内核** | Linux 4.4.153-perf+ (Android 11, SDK 30) |
| **Root** | Magisk |
| **Bootloader** | 已解锁 |
| **引导设备** | `c0c4000.sdhci` |
| **显示面板 ID** | `qcom,mdss_dsi_oppo16051samsung_s6e3fa3_1080p_cmd` |

### 关键分区布局

| 分区名 | 块设备 | 大小 |
|--------|--------|------|
| `boot` | mmcblk0p21 | 64 MB |
| `recovery` | mmcblk0p23 | 64 MB |
| `system` | mmcblk0p66 | ~4.7 GB |
| `vendor` | mmcblk0p67 | ~1 GB |
| `cache` | mmcblk0p65 | 256 MB |
| `userdata` | mmcblk0p69 | ~52 GB |
| `persist` | mmcblk0p5 | 32 MB |
| `modem` | mmcblk0p58 | 64 MB |
| `dsp` | mmcblk0p34/35 | 16 MB |
| `bluetooth` | mmcblk0p9 | 16 MB |

---

## 二、主线 Linux 支持现状评估

> [!CAUTION]
> **OPPO R11 目前没有任何现成的主线 Linux 移植。** 这意味着你不能像其他已支持设备那样直接下载镜像刷入，需要从头进行设备树移植工作。

### SDM660 生态现状

| 方面 | 状态 |
|------|------|
| **SoC 上游支持** | ✅ SDM660 核心 DTSI 已合入主线内核 (`arch/arm64/boot/dts/qcom/sdm660.dtsi`) |
| **CPU / SMP** | ✅ 可工作 |
| **eMMC 存储** | ✅ SDHCI 驱动可用 |
| **USB** | ✅ 基本 USB 2.0/OTG 可用 |
| **GPU (Adreno 512)** | ⚠️ 通过 `msm` DRM 驱动部分支持 |
| **Wi-Fi** | ⚠️ `ath10k_snoc` 驱动可用 (需提取固件) |
| **蓝牙** | ⚠️ 部分可用 |
| **音频** | ⚠️ WIP, 因设备而异 |
| **显示** | ⚠️ 需为 S6E3FA3 面板编写/适配驱动 |
| **摄像头** | ❌ 基本不可用 |
| **Modem/通话** | ❌ 不稳定 |
| **GPS** | ❌ 不可用 |
| **深度睡眠** | ❌ 不可用 |

### 已有 SDM660 主线 Linux 设备（可参考）

以下设备已有社区移植，可作为你移植 OPPO R11 的重要参考：

- **Xiaomi Mi A2** (`xiaomi-jasmine_sprout`) — 参考价值最高
- **Xiaomi Redmi Note 7** (`xiaomi-lavender`)
- **Xiaomi Mi Note 3** (`xiaomi-jason`)
- **Nokia 6.1** (`nokia-pl2`)
- **ASUS Zenfone Max Pro M1** (`asus-x00td`)

---

## 三、Linux 发行版选择建议

> [!IMPORTANT]
> 鉴于 OPPO R11 没有现成移植，**强烈建议先用 postmarketOS 起步**，而不是直接上 Arch Linux。

### 方案对比

| 发行版 | 推荐度 | 理由 |
|--------|--------|------|
| **postmarketOS (Alpine)** | ⭐⭐⭐⭐⭐ **首选** | 拥有 `pmbootstrap` 工具链，SDM660 共享内核包 (`linux-postmarketos-qcom-sdm660`)，社区活跃，新设备移植文档完善，是所有手机主线 Linux 移植的事实标准起点 |
| **Arch Linux ARM** | ⭐⭐⭐ 进阶选择 | 需手动处理所有事项；但可以在 postmarketOS 内核工作后，替换 rootfs 为 Arch Linux ARM 的 aarch64 通用包 |
| **Mobian (Debian)** | ⭐⭐⭐ 备选 | 软件包丰富，但对 SDM660 的集成不如 postmarketOS |

### 推荐路线

```
阶段1: postmarketOS 移植 (验证内核能启动)
         ↓
阶段2: 稳定硬件支持 (显示/触摸/USB/Wi-Fi)
         ↓
阶段3 (可选): 将 rootfs 换成 Arch Linux ARM
```

---

## 四、详细实施规划

### 阶段 0: 准备工作 (备份与环境搭建)

#### 0.1 完整备份当前系统

```bash
# 在电脑上创建备份目录
mkdir -p ~/oppo-r11-backup

# 备份关键分区 (通过 root ADB)
for part in boot recovery system vendor persist modem dsp bluetooth; do
    adb shell "su -c 'dd if=/dev/block/bootdevice/by-name/$part of=/sdcard/backup_$part.img bs=4096'"
    adb pull /sdcard/backup_$part.img ~/oppo-r11-backup/
done

# 备份完整分区表信息
adb shell "su -c 'ls -la /dev/block/bootdevice/by-name/'" > ~/oppo-r11-backup/partition-map.txt
adb shell "su -c 'cat /proc/partitions'" > ~/oppo-r11-backup/partitions.txt

# 备份 device tree blob (从当前 boot.img 提取)
adb shell "su -c 'dd if=/dev/block/bootdevice/by-name/boot of=/sdcard/stock_boot.img'"
adb pull /sdcard/stock_boot.img ~/oppo-r11-backup/
```

> [!WARNING]
> **务必完成完整备份！** 特别是 `boot`、`recovery`、`modem`、`persist` 分区。如果刷机失败，这些备份是恢复的唯一途径。

#### 0.2 提取固件文件

```bash
# 提取 Wi-Fi / 蓝牙 / GPU / DSP 等固件
adb shell "su -c 'tar czf /sdcard/firmware_mnt.tar.gz /vendor/firmware_mnt/'"
adb pull /sdcard/firmware_mnt.tar.gz ~/oppo-r11-backup/

adb shell "su -c 'tar czf /sdcard/vendor_firmware.tar.gz /vendor/firmware/'"
adb pull /sdcard/vendor_firmware.tar.gz ~/oppo-r11-backup/

# 提取 DSP 固件
adb shell "su -c 'tar czf /sdcard/dsp_firmware.tar.gz /vendor/dsp/'"
adb pull /sdcard/dsp_firmware.tar.gz ~/oppo-r11-backup/

# 提取蓝牙固件
adb shell "su -c 'tar czf /sdcard/bt_firmware.tar.gz /vendor/bt_firmware/'"
adb pull /sdcard/bt_firmware.tar.gz ~/oppo-r11-backup/
```

#### 0.3 搭建交叉编译环境 (macOS)

```bash
# 安装必要工具
brew install aarch64-elf-gcc dtc python3 git fastboot

# 安装 pmbootstrap (postmarketOS 构建工具)
pip3 install pmbootstrap

# 克隆 sdm660-mainline 内核源码
git clone https://github.com/sdm660-mainline/linux.git ~/sdm660-mainline-kernel
cd ~/sdm660-mainline-kernel
git checkout sdm660  # 切换到 SDM660 开发分支

# 克隆 lk2nd (二级引导器)
git clone https://github.com/nicoe/lk2nd-sdm660.git ~/lk2nd-sdm660
```

> [!TIP]
> 推荐使用一台 Linux 电脑（Ubuntu/Fedora）或 Docker 容器进行编译，交叉编译工具链在原生 Linux 上最稳定。macOS 可以通过 Lima/Docker 运行 Linux 虚拟机来编译。

---

### 阶段 1: 刷入 lk2nd 二级引导器

lk2nd 是关键中间层——它不替换 OPPO 原厂主引导器，而是作为 `boot.img` 刷入 boot 分区，提供标准化的 Fastboot 接口。

#### 1.1 编译 lk2nd（或获取预编译版本）

```bash
cd ~/lk2nd-sdm660

# 针对 SDM660 平台编译
make TOOLCHAIN_PREFIX=aarch64-linux-gnu- sdm660-secondary

# 生成的镜像:
# build-sdm660-secondary/lk2nd.img
```

#### 1.2 刷入 lk2nd

```bash
# 进入 fastboot 模式
adb reboot bootloader

# 确认设备已识别
fastboot devices

# 刷入 lk2nd 到 boot 分区
fastboot flash boot lk2nd.img

# 重启 — 此时 lk2nd 接管引导
fastboot reboot
```

#### 1.3 验证 lk2nd

```
重启后:
- 按住 音量减 键 → 进入 lk2nd Fastboot 菜单
- 按住 音量加 键 → 进入 Recovery
- 不按键 → 正常启动（启动 lk2nd 中存储的 OS 镜像）
```

---

### 阶段 2: 编写 OPPO R11 设备树 (DTS)

> [!IMPORTANT]
> 这是整个移植过程中最核心、最耗时的工作。你需要为 OPPO R11 编写一份主线格式的设备树文件。

#### 2.1 从现有设备提取硬件信息

```bash
# 反编译当前 Android boot.img 中的 DTB
# 先从备份的 stock_boot.img 提取 dtb
cd ~/oppo-r11-backup
# 使用 extract-dtb 或 unpackbootimg 工具
python3 -m pip install extract-dtb
extract-dtb stock_boot.img -o dtb_output/

# 反编译 DTB 为 DTS (可读格式)
dtc -I dtb -O dts -o oppo-r11-stock.dts dtb_output/01_dtbdump_*.dtb
```

#### 2.2 创建主线设备树

以 Xiaomi Mi A2 (`sdm660-xiaomi-jasmine.dts`) 为模板，创建 `sdm660-oppo-r11.dts`:

```dts
// SPDX-License-Identifier: GPL-2.0-only
/dts-v1/;

#include "sdm660.dtsi"
#include "pm660.dtsi"
#include "pm660l.dtsi"

/ {
    model = "OPPO R11";
    compatible = "oppo,r11", "qcom,sdm660";
    /* qcom,msm-id = <0x13d 0x0>; */
    /* qcom,board-id = <0x8 0x0>; */

    chosen {
        stdout-path = "serial0:115200n8";
    };

    reserved-memory {
        /* 根据提取的下游 DTS 填充 */
    };

    /* 
     * 以下节点需要根据从 stock DTS 提取的信息逐一适配:
     * - &sdhc_1 (eMMC)
     * - &usb3 (USB)
     * - &mdss_dsi0 (显示面板 - Samsung S6E3FA3)
     * - &tlmm (GPIO / 按键 / LED)
     * - 电源键 / 音量键
     * - 振动马达
     * - 触摸屏 IC
     */
};

/* 示例: 使能 UART 调试 */
&blsp1_uart2 {
    status = "okay";
};

/* 示例: 使能 eMMC */
&sdhc_1 {
    status = "okay";
};
```

#### 2.3 显示面板驱动

你的设备使用 **Samsung S6E3FA3** AMOLED 面板 (DSI Command 模式)。这是一个关键组件：

```
面板标识: qcom,mdss_dsi_oppo16051samsung_s6e3fa3_1080p_cmd
接口: MIPI DSI, Command Mode
分辨率: 1080x1920
```

- 检查主线内核 `drivers/gpu/drm/panel/` 是否已有 `s6e3fa3` 驱动
- 如果没有，需要参考下游 MDSS 面板初始化序列编写 DRM panel 驱动
- 或者初期先使用 `simplefb` (Simple Framebuffer) 跳过此步骤，通过 UART/SSH 调试

---

### 阶段 3: 编译主线内核

```bash
cd ~/sdm660-mainline-kernel

# 使用 SDM660 defconfig
make ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- sdm660_defconfig

# 将你的设备树放入源码树
cp sdm660-oppo-r11.dts arch/arm64/boot/dts/qcom/

# 在 Makefile 中添加编译目标
# 编辑 arch/arm64/boot/dts/qcom/Makefile, 添加:
# dtb-$(CONFIG_ARCH_QCOM) += sdm660-oppo-r11.dtb

# 编译内核 + DTB
make ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- -j$(nproc) Image.gz dtbs

# 编译内核模块
make ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- -j$(nproc) modules
make ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- INSTALL_MOD_PATH=./modules_out modules_install
```

---

### 阶段 4: 使用 pmbootstrap 构建 postmarketOS

#### 4.1 初始化 pmbootstrap

```bash
pmbootstrap init
# 选择:
#   Channel: edge
#   Vendor: oppo
#   Device codename: r11
```

#### 4.2 创建设备包

在 `~/.local/var/pmbootstrap/cache_git/pmaports/device/testing/` 下创建:

**`device-oppo-r11/deviceinfo`:**
```ini
deviceinfo_format_version="0"
deviceinfo_name="OPPO R11"
deviceinfo_manufacturer="OPPO"
deviceinfo_codename="oppo-r11"
deviceinfo_year="2017"
deviceinfo_dtb="qcom/sdm660-oppo-r11"
deviceinfo_append_dtb="true"
deviceinfo_arch="aarch64"
deviceinfo_chassis="handset"
deviceinfo_gpu_accelerated="true"

# Kernel
deviceinfo_kernel_cmdline="console=ttyMSM0,115200n8 earlycon"

# Boot
deviceinfo_flash_method="fastboot"
deviceinfo_generate_bootimg="true"
deviceinfo_bootimg_qcdt="false"
deviceinfo_bootimg_dtb_second="false"
deviceinfo_flash_offset_base="0x00000000"
deviceinfo_flash_offset_kernel="0x00008000"
deviceinfo_flash_offset_ramdisk="0x01000000"
deviceinfo_flash_offset_second="0x00f00000"
deviceinfo_flash_offset_tags="0x00000100"
deviceinfo_flash_pagesize="4096"
```

**`device-oppo-r11/APKBUILD`:**
```bash
pkgname=device-oppo-r11
pkgdesc="OPPO R11"
pkgver=1
pkgrel=0
url="https://postmarketos.org"
license="MIT"
arch="aarch64"
depends="
    linux-postmarketos-qcom-sdm660
    mkbootimg
    postmarketos-base
    soc-qcom-sdm660
"
makedepends="devicepkg-dev"
source="deviceinfo"
options="!check !archcheck"

build() {
    devicepkg_build $startdir $pkgname
}

package() {
    devicepkg_package $startdir $pkgname
}

sha512sums="(generate after creating)"
```

#### 4.3 构建并刷入

```bash
# 构建 postmarketOS 镜像
pmbootstrap install --sdcard  # 或不带 --sdcard 生成 boot.img + rootfs

# 将 boot.img 刷入
pmbootstrap flasher flash_kernel

# 或手动:
fastboot flash boot ~/.local/var/pmbootstrap/chroot_native/home/pmos/rootfs/boot.img
```

---

### 阶段 5 (可选): 替换为 Arch Linux ARM

在 postmarketOS 内核成功启动后，如果你仍想用 Arch Linux：

#### 5.1 准备 Arch rootfs

```bash
# 下载 Arch Linux ARM 通用 aarch64 rootfs
wget http://os.archlinuxarm.org/os/ArchLinuxARM-aarch64-latest.tar.gz

# 格式化 userdata 分区为 ext4
# (通过 lk2nd fastboot 或 recovery)
fastboot format:ext4 userdata

# 挂载并解压
mkdir -p /mnt/arch
mount /dev/mmcblk0p69 /mnt/arch
bsdtar -xpf ArchLinuxARM-aarch64-latest.tar.gz -C /mnt/arch
```

#### 5.2 安装主线内核到 Arch rootfs

```bash
# 将编译好的内核和模块复制进去
cp Image.gz /mnt/arch/boot/
cp sdm660-oppo-r11.dtb /mnt/arch/boot/
cp -r modules_out/lib/modules/* /mnt/arch/lib/modules/

# 从提取的固件中复制必要固件
mkdir -p /mnt/arch/lib/firmware/qcom
# 复制 Wi-Fi / 蓝牙 / GPU / DSP 固件...
```

#### 5.3 制作 boot.img

```bash
# 使用 mkbootimg 将内核打包为 Android boot.img 格式
mkbootimg \
    --kernel Image.gz-dtb \
    --ramdisk initramfs.cpio.gz \
    --base 0x00000000 \
    --kernel_offset 0x00008000 \
    --ramdisk_offset 0x01000000 \
    --tags_offset 0x00000100 \
    --pagesize 4096 \
    --cmdline "console=ttyMSM0,115200n8 root=/dev/mmcblk0p69 rw rootwait" \
    --output boot.img

# 通过 lk2nd fastboot 刷入
fastboot flash boot boot.img
```

---

## 五、预期时间与难度评估

| 阶段 | 预计时间 | 难度 | 说明 |
|------|----------|------|------|
| 阶段 0: 备份与环境 | 1-2 小时 | ⭐ | 直接操作 |
| 阶段 1: lk2nd | 2-4 小时 | ⭐⭐ | 可能需为 OPPO R11 调整 lk2nd 配置 |
| 阶段 2: 设备树编写 | **1-4 周** | ⭐⭐⭐⭐⭐ | **最核心最困难的部分**，需要深入理解硬件和内核 |
| 阶段 3: 内核编译 | 2-4 小时 | ⭐⭐ | 有文档参考 |
| 阶段 4: postmarketOS | 1-2 天 | ⭐⭐⭐ | 依赖阶段 2 的完成度 |
| 阶段 5: Arch 替换 | 半天 | ⭐⭐ | 在内核已工作后比较简单 |

---

## 六、风险与注意事项

> [!WARNING]
> ### 关键风险
> 1. **变砖风险:** 刷入不兼容的 boot.img 可能导致无法开机。始终保留 `recovery` 分区和所有备份。
> 2. **EDL 救砖:** 如果连 fastboot 都进不去，需要通过 Qualcomm EDL (Emergency Download) 模式使用 QFIL 工具恢复。确保你能获取到 OPPO R11 的完整 EDL 刷机包。
> 3. **没有显示:** 初期主线内核很可能无法驱动屏幕。你需要依赖 **USB SSH** 或 **UART 串口** 进行调试。
> 4. **不可做日用机:** 即使成功启动主线 Linux，摄像头、通话、GPS 等功能大概率不可用。

### 调试技巧

- **UART 调试:** 如果有 USB 转 UART 线，可以焊接到 R11 主板的 UART 测试点获取内核日志
- **USB SSH 调试:** 配置 `configfs` USB gadget 为 RNDIS 网络模式，通过 USB 网络连接 SSH
- **initramfs 日志:** 在 initramfs 中添加 `telnetd` 服务，开机后通过 USB 网络 telnet 查看日志
- **pstore/ramoops:** 利用 `pstore` 读取上一次崩溃的内核日志

---

## 七、参考资源

| 资源 | 链接 |
|------|------|
| sdm660-mainline 内核 | `https://github.com/sdm660-mainline/linux` |
| sdm660-mainline U-Boot | `https://github.com/sdm660-mainline/u-boot` |
| lk2nd SDM660 | `https://github.com/nicoe/lk2nd-sdm660` |
| postmarketOS 新设备移植指南 | `https://wiki.postmarketos.org/wiki/Porting_to_a_new_device` |
| postmarketOS SDM660 Wiki | `https://wiki.postmarketos.org/wiki/Qualcomm_Snapdragon_660_(SDM660)` |
| Arch Linux ARM aarch64 | `https://archlinuxarm.org/platforms/armv8/generic` |
| Linux 主线内核 DTS 文档 | `https://www.kernel.org/doc/Documentation/devicetree/bindings/` |
| Mainlining Guide | `https://mainlining.dev/` |
| Xiaomi Mi A2 参考移植 | postmarketOS wiki: `xiaomi-jasmine_sprout` |
| oppo-sdm660-devs (下游参考) | `https://github.com/oppo-sdm660-devs` |

---

## 八、总结与建议

### 最终建议

1. **先走 postmarketOS 路线** — 利用其成熟的 SDM660 内核包和 `pmbootstrap` 工具链，大幅降低起步难度
2. **设备树移植是成败关键** — 以 Xiaomi Mi A2 的 DTS 为蓝本，结合从 OPPO R11 stock 固件提取的硬件信息进行适配
3. **初期目标设为 UART/SSH 可登录** — 不要一开始就追求显示/触摸工作，先让内核能跑起来
4. **确认 Arch 之前先跑通 postmarketOS** — 一旦内核和基础硬件工作，替换 rootfs 为 Arch Linux ARM 是相对简单的操作
5. **建议在 EDL 方案就绪后才开始刷机** — 确保即使完全变砖也有恢复手段

> [!NOTE]
> 如果你的目标只是在手机上使用 Linux 环境（而非纯主线 Linux 体验），使用 **Termux + proot-distro** 在 Android 上运行 Arch Linux 容器是一个零风险的替代方案：
> ```bash
> pkg install proot-distro
> proot-distro install archlinux
> proot-distro login archlinux
> ```
> 这样可以在不刷机的情况下获得完整的 Arch Linux 命令行环境。
