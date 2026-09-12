#!/usr/bin/env bash
# mouse-color.sh <R> <G> <B> — статичный цвет подсветки ZELOTES C-18 (8-битный RGB).
# Сборка c18_usb_seq3: gcc c18_usb_seq3.c -o c18_usb_seq3 $(pkg-config --cflags --libs libusb-1.0)
# (исходники: https://github.com/PadreAdamo/c18_reverseengineer)
set -euo pipefail

BIN="${BIN:-/usr/local/bin/c18_usb_seq3}"
BASE="0f001e0a191905010103646401c0f0030101191922395cd0f35c730022395cd0f35c73001fff0000000031000031000031000031000031000031000031000031"

r="${1:?usage: mouse-color.sh <R> <G> <B>}"
g="${2:?}"
b="${3:?}"

payload="$(python3 - "$r" "$g" "$b" "$BASE" <<'PY'
import sys
r, g, b, base = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3]), bytearray.fromhex(sys.argv[4])
scale = 0x31 / 255.0          # прошивка мыши: канал 0-255 -> 0-0x31
trip = bytes(round(c * scale) for c in (r, g, b))
for i in range(8):            # 8 RGB-триплетов хвоста (байты 40..63)
    base[40 + i * 3 : 40 + i * 3 + 3] = trip
print(base.hex())
PY
)"

echo "c18: static r=$r g=$g b=$b"
sudo -n "$BIN" "$payload"