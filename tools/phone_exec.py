#!/usr/bin/env python3
import os, sys, time, tty, termios

import glob
import re

def get_serial_port():
    candidates = glob.glob("/dev/cu.usbmodemr11t*")
    if candidates:
        return candidates[0]
    return "/dev/cu.usbmodemr11t_arch1"

SERIAL_PORT = get_serial_port()

def run_command(cmd, timeout=5.0):
    fd = os.open(SERIAL_PORT, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    tty.setraw(fd)
    
    # Flush pending input
    time.sleep(0.1)
    while True:
        try:
            if not os.read(fd, 4096): break
        except BlockingIOError:
            break

    marker_sent = f"__END_{int(time.time()*1000)}__"
    full_cmd = f"\x03\x0c\n{cmd}\necho RESULT_{marker_sent}:$?\n"
    target = f"RESULT_{marker_sent}:"
    os.write(fd, full_cmd.encode("utf-8"))

    start = time.time()
    buf = b""
    exit_code = None

    while time.time() - start < timeout:
        try:
            chunk = os.read(fd, 4096)
            if chunk:
                buf += chunk
                text = buf.decode("utf-8", errors="replace")
                if target in text:
                    parts = text.split(target)
                    # The last part will follow the actual output of echo
                    if len(parts) > 1:
                        tokens = parts[-1].strip().split()
                        if tokens and tokens[0].isdigit():
                            exit_code = int(tokens[0])
                            break
        except BlockingIOError:
            pass
        time.sleep(0.05)

    os.close(fd)
    out_text = buf.decode("utf-8", errors="replace")
    # Drop terminal OSC/bracketed-paste noise and the echoed command line
    out_text = re.sub(r"\x1b\][^\x07\x1b]*(\x07|\x1b\\)", "", out_text)
    out_text = re.sub(r"\x1b\[\?2004[hl]|\x1b\[\?[0-9;]*[a-zA-Z]", "", out_text)
    lines = [ln for ln in out_text.split("\r\n")
             if ln.strip() and marker_sent not in ln and cmd not in ln]
    return exit_code, "\n".join(lines)

if __name__ == "__main__":
    timeout = 10.0
    args = sys.argv[1:]
    if args and args[0].startswith("--timeout="):
        timeout = float(args[0].split("=")[1])
        args = args[1:]
    cmd = " ".join(args) if args else "uname -a"
    code, output = run_command(cmd, timeout=timeout)
    print(f"Exit: {code}")
    print(f"Output:\n{output}")
