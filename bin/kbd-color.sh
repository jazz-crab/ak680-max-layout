#!/usr/bin/env bash
# kbd-color.sh <R> <G> <B> — единый цвет подсветки AK680 MAX (режим Constant).
# Требует физически подключённую клавиатуру и sudo.
set -euo pipefail

r="${1:?usage: kbd-color.sh <R> <G> <B>}"
g="${2:?}"
b="${3:?}"

sudo -n iot_driver set-led 1 4 2 "$r" "$g" "$b"