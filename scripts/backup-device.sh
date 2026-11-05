#!/usr/bin/env bash
set -euo pipefail

BACKUP_DIR="${1:-./backup}"
mkdir -p "$BACKUP_DIR"

echo "=== Checking ADB connection ==="
adb wait-for-device
DEVICE_MODEL=$(adb shell getprop ro.product.model | tr -d '\r')
echo "Connected to: $DEVICE_MODEL"

echo "=== Ensuring Root Access ==="
adb shell "su -c 'id'"

echo "=== Dumping Partition Table ==="
adb shell "su -c 'cat /proc/partitions'" > "$BACKUP_DIR/partitions.txt"
adb shell "su -c 'ls -la /dev/block/bootdevice/by-name/'" > "$BACKUP_DIR/by-name.txt"

echo "=== Dumping Critical Partitions ==="
CRITICAL_PARTS=(boot recovery persist modem dsp bluetooth devcfg devinfo)

for part in "${CRITICAL_PARTS[@]}"; do
    echo "Dumping partition: $part ..."
    adb shell "su -c 'dd if=/dev/block/bootdevice/by-name/$part of=/sdcard/dump_$part.img bs=4096'"
    adb pull "/sdcard/dump_$part.img" "$BACKUP_DIR/$part.img"
    adb shell "rm -f /sdcard/dump_$part.img"
done

echo "=== Dumping Hardware State (/proc & /sys) ==="
adb shell "su -c 'cat /proc/cmdline'" > "$BACKUP_DIR/stock_cmdline.txt"
adb shell "su -c 'cat /proc/meminfo'" > "$BACKUP_DIR/stock_meminfo.txt"
adb shell "su -c 'cat /proc/cpuinfo'" > "$BACKUP_DIR/stock_cpuinfo.txt"

# Extract live device tree if available
if adb shell "[ -d /sys/firmware/devicetree/base ]"; then
    echo "Pulling live devicetree node..."
    adb shell "su -c 'tar -czf /sdcard/live_dt.tar.gz /sys/firmware/devicetree/base/'"
    adb pull "/sdcard/live_dt.tar.gz" "$BACKUP_DIR/live_dt.tar.gz"
    adb shell "rm -f /sdcard/live_dt.tar.gz"
    mkdir -p "$BACKUP_DIR/live_dt"
    tar -xzf "$BACKUP_DIR/live_dt.tar.gz" -C "$BACKUP_DIR/live_dt" || true
fi

# Extract vendor firmware
echo "Dumping vendor firmware blobs..."
adb shell "su -c 'tar -czf /sdcard/firmware_mnt.tar.gz /vendor/firmware_mnt/'" || true
adb pull "/sdcard/firmware_mnt.tar.gz" "$BACKUP_DIR/" || true
adb shell "rm -f /sdcard/firmware_mnt.tar.gz" || true

echo "=== Backup Complete! Saved to: $BACKUP_DIR ==="
