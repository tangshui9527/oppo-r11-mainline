#!/usr/bin/env python3
"""mkbootimg.py -- pack a Linux zImage + initramfs + single DTB into an
Android boot image accepted by the (unsigned, v0-header) MSM8909 aboot.

Layout verified on-device (Hisense M20-T, boot partition repack experiment,
2026-10-29): Android boot image header v0, page size 2048, sections
page-aligned in order kernel / ramdisk / dt.  The stock bootloader reads
sizes directly from the header, calls the DT section (dt_size) and does not
check any signature (experiment produced a booted kernel from a modified
image; see workspace AGENTS.md).

Addresses copied from the stock image:
    kernel_addr = 0x80008000, ramdisk_addr = 0x81000000,
    second_addr = 0x80f00000, tags_addr = 0x80000100, page_size = 2048.
"""

import argparse
import struct
import zlib


def page_align(n: int, page: int) -> int:
    return (n + page - 1) // page * page


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kernel", required=True)
    ap.add_argument("--ramdisk", required=True)
    ap.add_argument("--dtb", required=True, help="single-decision DTB (goes into dt_size)")
    ap.add_argument("--cmdline", default="console=ttyHSL0,115200,n8")
    ap.add_argument("--bootimg", required=True)
    ap.add_argument("--page-size", type=int, default=2048)
    ap.add_argument("--kernel-addr", default="0x80008000")
    ap.add_argument("--ramdisk-addr", default="0x81000000")
    ap.add_argument("--tags-addr", default="0x80000100")
    ap.add_argument("--board-name", default="")
    args = ap.parse_args()

    page = args.page_size
    kernel = open(args.kernel, "rb").read()
    ramdisk = open(args.ramdisk, "rb").read()
    dtb = open(args.dtb, "rb").read()

    hdr = bytearray(page)
    struct.pack_into(
        "<8s10I",
        hdr,
        0,
        b"ANDROID!",
        len(kernel), int(args.kernel_addr, 16),
        len(ramdisk), int(args.ramdisk_addr, 16),
        0, 0x80F00000,                      # second_size / second_addr
        int(args.tags_addr, 16),
        page,
        len(dtb),                            # dt_size
        0,
    )
    hdr[48:64] = args.board_name.encode()[:16].ljust(16, b"\0")
    cmdline = args.cmdline.encode()
    if len(cmdline) > 512:
        raise SystemExit("cmdline longer than 512 bytes")
    hdr[64:64 + len(cmdline)] = cmdline
    # id (32) and extra_cmdline (1024) fields stay zero.

    blob = bytes(hdr)
    for section in (kernel, ramdisk, dtb):
        blob += section + b"\0" * (-len(section) % page)

    with open(args.bootimg, "wb") as f:
        f.write(blob)

    used = page + page_align(len(kernel), page) + page_align(len(ramdisk), page) + page_align(len(dtb), page)
    print(f"boot image : {args.bootimg} ({len(blob)} bytes, {used} used, crc32={zlib.crc32(blob):#010x})")
    print(f"  kernel   {len(kernel)} B   ramdisk {len(ramdisk)} B   dtb {len(dtb)} B")
    print(f"  cmdline  {args.cmdline!r}")
    print(f"  NOTE: image+padding must fit the boot partition (verify against dd target size).")


if __name__ == "__main__":
    main()
