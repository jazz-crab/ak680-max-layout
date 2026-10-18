#!/usr/bin/env bash
# deskflow-color-daemon.sh — меняет цвет клавиатуры и мыши по активному экрану
# Deskflow-сервера. Deskflow 1.26 не умеет enter/exit-команды, поэтому следим за
# строкой "switch from "X" to "Y"" в логе сервера (/tmp/deskflow-server.log).
#
# Запуск: deskflow-color-daemon.sh  (по желанию — в фон, например из hyprland autostart)
#
# Имена хостов, которые скрипт прокидывает в deskflow-color.sh, берутся из лога Deskflow
# как есть; в примерах ниже они заменены плейсхолдерами server/client — подставь свои.
set -euo pipefail

LOG="${DESKFLOW_LOG:-/tmp/deskflow-server.log}"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APPLY="$DIR/deskflow-color.sh"

# Текущее состояние из хвоста лога (если он уже реагировал):
current="$(
  grep -o 'switch from "[^"]*" to "[^"]*"' "$LOG" 2>/dev/null \
    | tail -1 \
    | sed -E 's/.*to "([^"]*)"/\1/' \
    || true
)"
if [ -n "$current" ]; then
  echo "deskflow-color: initial screen = $current"
  "$APPLY" "$current" || true
else
  # Нет ещё ни одного переключения в логе — считаем активным сервер (server).
  echo "deskflow-color: no switch yet, default server"
  "$APPLY" server || true
fi

# Подписка на новые строки: появление/переход курсора на экран X.
tail -n 0 -F "$LOG" | while IFS= read -r line; do
  case "$line" in
    *'switch from '*)
      target="$(echo "$line" | sed -E 's/.*to "([^"]*)".*/\1/')"
      if [ -n "$target" ]; then
        echo "deskflow-color: switch -> $target"
        "$APPLY" "$target" || true
      fi
      ;;
  esac
done