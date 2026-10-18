#!/usr/bin/env bash
# deskflow-color.sh <server|client> — раскраска клавиатуры и мыши по активному
# экрану Deskflow: на сервере (server) голубой, на клиенте (client) болотно-зелёный.
# ВАЖНО: server/client — плейсхолдеры; подставь имена своих хостов ровно так, как они
# пишутся в строке лога Deskflow (switch from "X" to "Y"), и поправь case ниже.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
state="${1:?usage: deskflow-color.sh server|client}"

case "$state" in
  server)    R=0  G=150 B=255 ;;
  client) R=107 G=142 B=35 ;;
  *) echo "unknown screen: $state" >&2; exit 2 ;;
esac

"$DIR/kbd-color.sh"   "$R" "$G" "$B"
"$DIR/mouse-color.sh" "$R" "$G" "$B"