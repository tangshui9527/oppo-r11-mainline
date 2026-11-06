#!/usr/bin/env python3
"""Push a file to the phone over the LOCAL Mac serial console, chunked.

Usage: push_file_mac.py <local_file> <device_path> [chunk_size]
"""
import base64
import glob
import hashlib
import re
import subprocess  # noqa: F401 (parity with remote variant)
import sys
import os
import time

MARKER = "__PUSH_END__"


def get_port():
    c = glob.glob("/dev/cu.usbmodemr11t*")
    if not c:
        sys.exit("no serial port found")
    return c[0]


def send(cmd, timeout=15.0):
    import termios, tty
    fd = os.open(get_port(), os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    tty.setraw(fd)
    time.sleep(0.15)
    try:
        while os.read(fd, 65536):
            pass
    except BlockingIOError:
        pass
    full = "\x03\x0c\n" + cmd + f"\necho {MARKER}:$?\n"
    os.write(fd, full.encode())
    start = time.time()
    buf = b""
    while time.time() - start < timeout:
        try:
            c = os.read(fd, 65536)
            if c:
                buf += c
                tail = buf.split(f"echo {MARKER}:$?".encode())[-1]
                if re.search(f"{MARKER}:\\d+".encode(), tail):
                    break
        except BlockingIOError:
            pass
        time.sleep(0.03)
    os.close(fd)
    return buf.decode("utf-8", "replace")


def main():
    local, remote = sys.argv[1], sys.argv[2]
    chunk = int(sys.argv[3]) if len(sys.argv) > 3 else 400
    data = open(local, "rb").read()
    b64 = base64.b64encode(data).decode()
    md5 = hashlib.md5(data).hexdigest()
    n = (len(b64) + chunk - 1) // chunk
    print(f"pushing {local} ({len(data)} bytes, {n} chunks) -> {remote}")

    send("rm -f /tmp/.push.b64")
    for i in range(n):
        part = b64[i * chunk:(i + 1) * chunk]
        out = send(f"printf %s '{part}' >> /tmp/.push.b64", timeout=10)
        if f"{MARKER}:0" not in out:
            print(f"chunk {i} failed:\n{out[-300:]}")
            sys.exit(1)
        if (i + 1) % 20 == 0:
            print(f"  {i + 1}/{n}")

    out = send(f"base64 -d /tmp/.push.b64 > {remote} && md5sum {remote} && "
               f"rm -f /tmp/.push.b64", timeout=30)
    ok = md5 in out
    print("MD5 match: OK" if ok else f"MD5 MISMATCH! expected {md5}\n{out[-400:]}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
