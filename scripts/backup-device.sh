#!/usr/bin/env bash
set -euo pipefail

TARGET_SERIAL="${ADB_SERIAL:-REDACTED_SERIAL}"
BACKUP_DIR="${1:-./backup}"
mkdir -p "$BACKUP_DIR"

ADB="adb -s $TARGET_SERIAL"

echo "=== Target Device: $TARGET_SERIAL ==="
DEVICE_MODEL=$($ADB shell getprop ro.product.model | tr -d '\r')
echo "Connected to: $DEVICE_MODEL"

echo "=== Ensuring Root Access ==="
$ADB shell "su -c 'id'"

echo "=== Dumping Partition Table ==="
$ADB shell "su -c 'cat /proc/partitions'" > "$BACKUP_DIR/partitions.txt"
$ADB shell "su -c 'ls -la /dev/block/bootdevice/by-name/'" > "$BACKUP_DIR/by-name.txt"

echo "=== Dumping Critical Partitions ==="
CRITICAL_PARTS=(boot recovery persist modem dsp bluetooth devcfg devinfo)

for part in "${CRITICAL_PARTS[@]}"; do
    echo "Dumping partition: $part ..."
    $ADB shell "su -c 'dd if=/dev/block/bootdevice/by-name/$part of=/sdcard/dump_$part.img bs=4096'"
    $ADB pull "/sdcard/dump_$part.img" "$BACKUP_DIR/$part.img"
    $ADB shell "rm -f /sdcard/dump_$part.img"
done

echo "=== Dumping Hardware State (/proc & /sys) ==="
$ADB shell "su -c 'cat /proc/cmdline'" > "$BACKUP_DIR/stock_cmdline.txt"
$ADB shell "su -c 'cat /proc/meminfo'" > "$BACKUP_DIR/stock_meminfo.txt"
$ADB shell "su -c 'cat /proc/cpuinfo'" > "$BACKUP_DIR/stock_cpuinfo.txt"

# Extract live device tree if available
if $ADB shell "[ -d /sys/firmware/devicetree/base ]"; then
    echo "Pulling live devicetree node..."
    $ADB shell "su -c 'tar -czf /sdcard/live_dt.tar.gz /sys/firmware/devicetree/base/'"
    $ADB pull "/sdcard/live_dt.tar.gz" "$BACKUP_DIR/live_dt.tar.gz"
    $ADB shell "rm -f /sdcard/live_dt.tar.gz"
    mkdir -p "$BACKUP_DIR/live_dt"
    tar -xzf "$BACKUP_DIR/live_dt.tar.gz" -C "$BACKUP_DIR/live_dt" 2>/dev/null || true
fi

# Extract vendor firmware
echo "Dumping vendor firmware blobs..."
$ADB shell "su -c 'tar -czf /sdcard/firmware_mnt.tar.gz /vendor/firmware_mnt/'" || true
$ADB pull "/sdcard/firmware_mnt.tar.gz" "$BACKUP_DIR/" || true
$ADB shell "rm -f /sdcard/firmware_mnt.tar.gz" || true

echo "=== Backup Complete! Saved to: $BACKUP_DIR ==="
