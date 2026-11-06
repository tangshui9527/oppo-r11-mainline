#!/usr/bin/env bash
# build.sh -- assemble the oppo-r11 mainline initramfs cpio (gzip).
#
# Produces: initramfs.cpio.gz
# Uses static aarch64 busybox from Alpine Linux

set -euo pipefail
cd "$(dirname "$0")"

_ALPINE=v3.21
_BB_APK="busybox-static-1.37.0-r14.apk"       # aarch64, alpine 3.21 main
_BASE=https://dl-cdn.alpinelinux.org/alpine/${_ALPINE}/main/aarch64

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

echo "[initramfs] fetching ${_BB_APK} for aarch64"
if ! curl -fSL -o "$WORK/bb.apk" "${_BASE}/${_BB_APK}" 2>/dev/null; then
    echo "[initramfs] pinned version missing, resolving from APKINDEX"
    BBFILE=$(curl -fsSL "${_BASE}/APKINDEX.tar.gz" | tar -xzO APKINDEX \
        | awk '/^P:busybox-static$/{p=1} p && /^V:/{v=$2; p=0} END{print "busybox-static-" v ".apk"}')
    curl -fSL -o "$WORK/bb.apk" "${_BASE}/${BBFILE}"
fi

mkdir -p "$WORK/fs"
if ! tar -xf "$WORK/bb.apk" -C "$WORK/fs" 2>/dev/null; then
    gzip -dc "$WORK/bb.apk" | tar -xf - -C "$WORK/fs"
fi
BB="$WORK/fs/bin/busybox.static"
[ -f "$BB" ] || { echo "busybox.static not found in apk"; exit 1; }

STAGE="$WORK/stage"
# Layout must match initramfs/init: /bin/busybox, /newroot, plus the usual
# pseudo-filesystem mountpoints. (The rescue-era layout of /busybox at the
# initramfs root produced images that panic-looped with rdinit=/init.)
mkdir -p "$STAGE/bin" "$STAGE/dev" "$STAGE/proc" "$STAGE/sys" "$STAGE/newroot"
install -m 0755 "$BB" "$STAGE/bin/busybox"
install -m 0755 init "$STAGE/init"
[ -f setup-ncm.sh ] && install -m 0755 setup-ncm.sh "$STAGE/etc/setup-ncm.sh" || true

(cd "$STAGE" && find . | cpio -o -H newc --owner=0:0 2>/dev/null) | gzip -9 > initramfs.cpio.gz
ls -l initramfs.cpio.gz
echo "[initramfs] done"
