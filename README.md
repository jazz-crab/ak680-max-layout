# AK680 MAX Layout

Кастомная раскладка для **AJAZZ AK680 MAX RGB** (wired USB, Hall-effect, VID/PID
`3151:502D`, Device ID `2255`, протокол RY5088) под Arch Linux / Hyprland.

## Что настроено

| Клавиша | Стало | Где реализовано |
|---------|-------|-----------------|
| Угол (левая от 1) | `` ` `` / **ё** | прошивка (remap index 1 → HID 0x35) |
| CapsLock | **Esc** | прошивка (remap index 3) |
| Колонка (Home/Del/PgUp/PgDn) | **Del/Home/PrtSc/End** | прошивка (remap 85–88) |
| Правый Shift | **обычный Shift** (по умолчанию) | — |
| Правый Alt | **переключение на EN** | Hyprland bind `code:108` |
| Правый Ctrl | **переключение на RU** | Hyprland bind `code:105` |

> Ремапы прошивки — по **индексам матрицы**, не по именам: `iot_driver` берёт имена
> клавиш из статической таблицы, которая для этой клавиатуры расходится с физикой
> (86→Delete, 87→PageUp, 88→PageDown). Подробности — в
> [docs/issue-monsgeek-akko-linux.txt](docs/issue-monsgeek-akko-linux.txt).

## Файлы

| Файл в репо | Куда | Зачем |
|-------------|------|-------|
| `bin/layout-switch.sh` | `~/bin/layout-switch.sh` | переключение раскладки **всех** клавиатур Hyprland (`0`=EN, `1`=RU) |
| `xkb/symbols_custom_xkb` | _архив_ (было `/usr/share/X11/xkb/symbols/custom`) | вариант `rshift_compose` — если захочешь вернуть Compose на другую клавишу |
| `hypr/hyprland.lua` | `~/.config/hypr/hyprland.lua` | `kb_layout = "us,ru"` + бинды `code:108/105` |
| `docs/keymap-raw.txt` | — | полная физическая карта клавиш (wev) |
| `docs/issue-monsgeek-akko-linux.txt` | — | баг-репорт для monsgeek-akko-linux |

## Ремапы прошивки (команды)

```bash
iot_driver reset                     # вернуть к заводским (подтвердить y)
iot_driver remap 1 '`'               # угол (Esc) -> grave/ё  — ВАЖНО: индекс 1, не 0
iot_driver remap 3 Escape            # Caps -> Esc
iot_driver remap 85 Delete           # Home -> Delete
iot_driver remap 86 Home             # Delete -> Home
iot_driver remap 87 prtsc            # PageUp -> PrtScr
iot_driver remap 88 End              # PageDown -> End
```

Примечания:
- **index 0 — пустышка**: `remap 0 ...` молча не применяется, а физический Esc это **index 1**.
- `remap N N` ≠ no-op: целевое число 0–9 трактуется как имя клавиши-цифры (перезапишет клавишу!). Сначала `reset`.
- Индексы 85–88 (по клавишам): 85=Home, 86=Delete, 87=PageUp, 88=PageDown (физика).

## Установка раскладок Hyprland

1. Скопировать `bin/layout-switch.sh` → `~/bin/` (`chmod +x`).
2. В `hyprland.lua`: `kb_layout = "us,ru"` и два бинда (см. `hypr/hyprland.lua`).
3. `hyprctl reload`.

## Почему скрипт переключения такой странный

Имена клавиатур в Hyprland/evdev начинаются с дефисов
(`-------gaming-keyboard`), поэтому `hyprctl switchxkblayout <имя>` принимает имя за
флаги и молча падает. Фикс — разделитель `--`:

```bash
hyprctl switchxkblayout -- "-------gaming-keyboard" 0
```

Скрипт перебирает все устройства из `hyprctl devices -j`, потому что печать может
идти не через тот интерфейс, который переключаешь по имени.

## Compose (архив, если захочешь вернуть на другую клавишу)

В `xkb/symbols_custom_xkb` лежит вариант `rshift_compose` (правый Shift → Multi_key).
Если решишь вернуть Compose, но не на правый Shift — поменяй клавишу в файле
(например `replace key <RCTL>` для правого Ctrl или `RALT`) и подключи
`kb_layout = "custom(...),ru"`.

Последовательности Compose:

| Последовательность | Результат |
|--------------------|-----------|
| `Comp < <` | « |
| `Comp > >` | » |
| `Comp - - -` | — |
| `Comp . .` | … |
| `Comp o o` | ° |
| `Comp ( c` | © |
| `Comp ( r` | ® |
| `Comp c ,` | ç |

Полный список: `/usr/share/X11/locale/en_US.UTF-8/Compose`.

## Диагностика

- `iot_driver info` — VID/PID, Device ID, имя прошивки.
- `hyprctl devices` — текущая раскладка каждой клавиатуры.
- `hyprctl binds | grep -A2 code:108|105` — проверка биндов.

Тестировано на Arch Linux (Hyprland/Wayland), 2026-08-30.