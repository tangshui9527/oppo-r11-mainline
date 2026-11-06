#!/usr/bin/env python3
"""Push a local file to the R11 over the remote serial console, chunked.

Usage: push_file.py <local_file> <device_path> [chunk_size]
Sends base64 chunks appended to /tmp/.push.b64 on the device, then decodes
and verifies MD5. Set R11_HOST=user@host before use.
"""
import base64
import hashlib
import os
import subprocess
import sys
import time

# SSH target comes from the environment; never hardcode host credentials here.
HOST = os.environ["R11_HOST"]
MARKER = "__PUSH_END__"


def send(cmd: str, timeout: float = 15.0) -> str:
    script = f"""
import os, time, termios, tty
fd = os.open("/dev/ttyACM1", os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
tty.setraw(fd)
os.write(fd, b"\\n")
time.sleep(0.15)
try:
    while os.read(fd, 65536): pass
except BlockingIOError:
    pass
full = "{cmd}\\necho {MARKER}:$?\\n"
os.write(fd, full.encode())
start = time.time()
buf = b""
import re
while time.time() - start < {timeout}:
    try:
        c = os.read(fd, 65536)
        if c:
            buf += c
            if re.search(rb"{MARKER}:\d+", buf.split(b"echo {MARKER}:$?")[-1]):
                break
    except BlockingIOError:
        pass
    time.sleep(0.03)
print(buf.decode("utf-8", "replace"))
"""
    p = subprocess.run(["ssh", "-o", "BatchMode=yes", HOST, "python3", "-"],
                       input=script, capture_output=True, text=True,
                       timeout=timeout + 20)
    return p.stdout


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
        if (i + 1) % 10 == 0:
            print(f"  {i + 1}/{n}")

    out = send(f"base64 -d /tmp/.push.b64 > {remote} && md5sum {remote} && "
               f"rm -f /tmp/.push.b64", timeout=20)
    ok = md5 in out
    print("MD5 match: OK" if ok else f"MD5 MISMATCH! expected {md5}\n{out[-400:]}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
