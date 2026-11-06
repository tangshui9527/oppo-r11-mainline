#!/usr/bin/env python3
"""Run a command on the R11 via the remote host's USB serial console.

Usage: remote_exec.py <command> [timeout]
Assumes SSH key auth and a phone console on /dev/ttyACM*.
Set R11_HOST=user@host before use.
"""
import os
import subprocess
import sys
import time

# SSH target comes from the environment; never hardcode host credentials here.
HOST = os.environ["R11_HOST"]
REMOTE_PORT_CMD = "ls /dev/ttyACM* 2>/dev/null | head -1"
MARKER = "__R11_EXEC_END__"


def remote_python(script: str, timeout: float = 60.0) -> str:
    """Push a python3 script to the remote host via stdin and run it."""
    cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", HOST,
           "python3 -"]
    proc = subprocess.run(cmd, input=script, capture_output=True,
                          text=True, timeout=timeout)
    return proc.stdout + proc.stderr


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    command = sys.argv[1]
    timeout = float(sys.argv[2]) if len(sys.argv) > 2 else 8.0

    # Find the ACM device on the remote host
    port = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", HOST, REMOTE_PORT_CMD],
        capture_output=True, text=True).stdout.strip()
    if not port:
        print("ERROR: no /dev/ttyACM* device on remote host (phone off?)")
        sys.exit(1)

    script = f"""
import os, sys, time

port = {port!r}
cmd = {command!r}
timeout = {timeout!r}

fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
import termios, tty
tty.setraw(fd)
time.sleep(0.2)
while True:
    try:
        if not os.read(fd, 65536):
            break
    except BlockingIOError:
        break

full = "\\x03\\x0c\\n" + cmd + "\\necho {MARKER}:$?\\n"
os.write(fd, full.encode())
start = time.time()
buf = b""
while time.time() - start < timeout:
    try:
        chunk = os.read(fd, 65536)
        if chunk:
            buf += chunk
            if b"{MARKER}:" in buf:
                time.sleep(0.05)
                try:
                    buf += os.read(fd, 65536)
                except BlockingIOError:
                    pass
                break
    except BlockingIOError:
        pass
    time.sleep(0.05)
os.close(fd)
text = buf.decode("utf-8", errors="replace")
lines = text.split("\\r\\n")
# drop the echoed command line and everything from the marker on
out = []
for ln in lines[1:]:
    if "{MARKER}" in ln:
        break
    out.append(ln)
print("\\n".join(out).strip())
"""
    print(remote_python(script, timeout=timeout + 30))


if __name__ == "__main__":
    main()
