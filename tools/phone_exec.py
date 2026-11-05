#!/usr/bin/env python3
import os, sys, time, tty, termios

SERIAL_PORT = "/dev/cu.usbmodemr11t_mainline1"

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

    marker = f"__END_{int(time.time()*1000)}__"
    full_cmd = f"\n{cmd}\necho {marker}:$?\n"
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
                if marker in text:
                    # Find exit code
                    parts = text.split(marker + ":")
                    if len(parts) > 1:
                        code_part = parts[1].split("\n")[0].strip()
                        if code_part.isdigit():
                            exit_code = int(code_part)
                            # Clean output before marker
                            clean_output = parts[0]
                            # Remove the echoed command line if present
                            lines = clean_output.split("\r\n")
                            # Filter out echo of command
                            break
        except BlockingIOError:
            pass
        time.sleep(0.05)

    os.close(fd)
    out_text = buf.decode("utf-8", errors="replace")
    return exit_code, out_text

if __name__ == "__main__":
    cmd = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "uname -a"
    code, output = run_command(cmd)
    print(f"Exit: {code}")
    print(f"Output:\n{output}")
