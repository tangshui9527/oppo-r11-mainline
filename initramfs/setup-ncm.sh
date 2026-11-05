#!/bin/sh
# Re-run NCM gadget bring-up from shell if the first attempt failed (e.g. UDC late probe)
(
    ip link set usb0 up 2>/dev/null || true
    if ! ip addr show usb0 2>/dev/null | grep -q 172.16.42.1; then
        ifconfig usb0 172.16.42.1 netmask 255.255.255.0 up 2>/dev/null
    fi
    echo "usb0 state:"
    ifconfig usb0 2>/dev/null || echo "(no usb0)"
) > /tmp/ncm-recheck.log 2>&1
echo done
