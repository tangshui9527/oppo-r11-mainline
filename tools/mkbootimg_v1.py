#!/usr/bin/env python3
"""mkbootimg_v1.py -- pack a Linux kernel (+appended DTB) + initramfs into an
Android boot image with a Version 1 header (for Qualcomm SDM660 ABL).
"""

import argparse
import hashlib
import struct


def pad(data: bytes, page_size: int) -> bytes:
    rem = len(data) % page_size
    return data + (b"\0" * (page_size - rem) if rem else b"")


def parse_os_version(version_str: str, patch_str: str) -> int:
    a, b, c = (int(x) for x in (version_str.split(".") + ["0", "0"])[:3])
    y, m = (int(x) for x in patch_str.split("-")[:2])
    os_ver = (a << 14) | (b << 7) | c
    os_patch = ((y - 2000) << 4) | m
    return (os_ver << 11) | os_patch


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--kernel", required=True)
    p.add_argument("--ramdisk", required=True)
    p.add_argument("--dtb", help="Optional separate DTB or will be appended to kernel")
    p.add_argument("--cmdline", default="console=ttyMSM0,115200n8 earlycon=msm_serial_dm,0xc170000 rootwait rw")
    p.add_argument("--base", type=lambda x: int(x, 16), default=0x80000000)
    p.add_argument("--kernel_offset", type=lambda x: int(x, 16), default=0x00008000)
    p.add_argument("--ramdisk_offset", type=lambda x: int(x, 16), default=0x03000000)
    p.add_argument("--tags_offset", type=lambda x: int(x, 16), default=0x00000100)
    p.add_argument("--second_offset", type=lambda x: int(x, 16), default=0x00F00000)
    p.add_argument("--pagesize", type=int, default=4096)
    p.add_argument("--os_version", default="9.0.0")
    p.add_argument("--os_patch_level", default="2019-09")
    p.add_argument("-o", "--output", required=True)
    args = p.parse_args()

    with open(args.kernel, "rb") as f:
        k_data = f.read()
    if args.dtb:
        with open(args.dtb, "rb") as f:
            d_data = f.read()
        k_data = k_data + d_data

    with open(args.ramdisk, "rb") as f:
        r_data = f.read()

    page = args.pagesize
    kernel_addr = args.base + args.kernel_offset
    ramdisk_addr = args.base + args.ramdisk_offset
    second_addr = args.base + args.second_offset
    tags_addr = args.base + args.tags_offset

    os_val = parse_os_version(args.os_version, args.os_patch_level)

    hdr = bytearray(page)
    struct.pack_into(
        "<8s10I",
        hdr,
        0,
        b"ANDROID!",
        len(k_data),
        kernel_addr,
        len(r_data),
        ramdisk_addr,
        0,
        second_addr,
        tags_addr,
        page,
        1,  # header_version = 1
        os_val,
    )

    cmdline_b = args.cmdline.encode("ascii")[:512]
    hdr[64 : 64 + len(cmdline_b)] = cmdline_b

    # Version 1 extension (offset 1632)
    # recovery_dtbo_size (uint32)
    # recovery_dtbo_offset (uint64)
    # header_size (uint32 = 1648)
    struct.pack_into("<IQI", hdr, 1632, 0, 0, 1648)

    # Calculate SHA1 checksum across kernel and ramdisk
    h = hashlib.sha1()
    h.update(k_data)
    h.update(r_data)
    digest = h.digest()
    hdr[576 : 576 + len(digest)] = digest

    blob = bytes(hdr) + pad(k_data, page) + pad(r_data, page)

    with open(args.output, "wb") as f:
        f.write(blob)

    print(f"Packed Boot Image v1: {args.output} (size: {len(blob)} bytes)")
    print(f"  Kernel (+DTB): {len(k_data)} B @ {hex(kernel_addr)}")
    print(f"  Ramdisk:       {len(r_data)} B @ {hex(ramdisk_addr)}")
    print(f"  Tags:          @ {hex(tags_addr)}")
    print(f"  Cmdline:       {args.cmdline}")


if __name__ == "__main__":
    main()
