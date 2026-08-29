#!/bin/bash
# layout-switch.sh <0|1> — переключение раскладки ВСЕХ клавиатур Hyprland
# НЕВЕРНЫЕ имена вроде "-------gaming-keyboard" начинаются с "-" — нужен "--".
IDX="${1:-0}"
hyprctl devices -j | python3 -c "
import json,sys
d=json.load(sys.stdin)
for k in d.get('keyboards', []):
    print(k['name'])
" | while IFS= read -r n; do
    hyprctl switchxkblayout -- "$n" "$IDX" >/dev/null 2>&1
done