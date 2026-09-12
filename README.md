# AK680 MAX Layout

Кастомная раскладка для **AJAZZ AK680 MAX RGB** (wired USB, Hall-effect, VID/PID
`3151:502D`, Device ID `2255`, протокол RY5088) под Arch Linux / Hyprland.

## Что настроено

| Клавиша | Стало | Где реализовано |
|---------|-------|-----------------|
| Esc (угол, он же левая от 1) | **Esc** (по классике) | прошивка (remap index 1 → Escape) |
| Fn + «е» (физический `T`, в RU «е») | **ё** (HID grave) | прошивка (remap `Fn+T` → `` ` ``) |
| CapsLock | **CapsLock** (заводской) | — (ремап Caps→Esc снят) |
| Колонка (Home/Del/PgUp/PgDn) | **Del/Home/PrtSc/End** | прошивка (remap 85–88) |
| Правый Shift | **обычный Shift** (по умолчанию) | — |
| Правый Alt | **переключение на EN** | Hyprland bind `code:108` |
| Правый Ctrl | **переключение на RU** | Hyprland bind `code:105` |

> Клавиша ё на этой клавиатуре — одна с Esc (угол), поэтому ё вынесена на
> **Fn + «е»** (физический `T`): в русской раскладке даёт «ё», в английской `` ` ``.
> Запасной вариант (hold/double-tap «е») — см. `TASKS.md`.

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
iot_driver remap 1 Escape            # угол (Esc) -> Esc, классика — ВАЖНО: индекс 1, не 0
iot_driver remap "Fn+T" '`'          # Fn+«е» -> grave/ё (в русской раскладке)
iot_driver remap 85 Delete           # Home -> Delete
iot_driver remap 86 Home             # Delete -> Home
iot_driver remap 87 prtsc            # PageUp -> PrtScr
iot_driver remap 88 End              # PageDown -> End
```

Hall Effect (все клавиши): активация **1.0 мм**, отпускание **1.5 мм** — лёгкое срабатывание.

```bash
sudo iot_driver set-actuation 1.0    # точка срабатывания (было 2.0 мм)
sudo iot_driver set-release 1.5      # точка отпускания (было 2.8 мм)
```

Примечания:
- **index 0 — пустышка**: `remap 0 ...` молча не применяется, а физический Esc это **index 1**.
- `remap N N` ≠ no-op: целевое число 0–9 трактуется как имя клавиши-цифры (перезапишет клавишу!). Сначала `reset`.
- Индексы 85–88 (по клавишам): 85=Home, 86=Delete, 87=PageUp, 88=PageDown (физика).
- Fn-слой адресуется префиксом `Fn+Клавиша` (например `Fn+T`) — `iot_driver` умеет.

## Ё: удержание «е» (Mod-Tap) — запасной вариант

Основной способ — `Fn+«е»`. Альтернатива, если захочешь ё без Fn: **удержание «е»
~200 мс → «ё»**. Проверено на живой прошивке (RY5088): семантика Mod-Tap —
**tap = слой 1, hold = слой 0**.

```bash
# 1. Включить Mod-Tap на физическом T (index 32)
sudo iot_driver set-key-trigger 32 --mode mod-tap
sudo iot_driver set-modtap-time 32 200   # порог tap-vs-hold, мс (шаг 10 мс)

# 2. Выходы: удержание (слой 0) = grave/ё, тап (слой 1) = «е»
sudo iot_driver remap T '`'
sudo iot_driver remap "L1+T" T

# 3. Проверка: keymatrix T покажет L0=`, L1=T
sudo iot_driver keymatrix
```

Откат (вернуть обычную «е»):

```bash
sudo iot_driver set-key-trigger 32 --mode normal
sudo iot_driver reset-key T
sudo iot_driver reset-key "L1+T"
```

Замечания:
- `reset-key "L1+T"` обнуляет слой 1 в «ничего» — быстрый тап перестаёт печатать,
  поэтому для Mod-Tap слой 1 возвращается явно (`remap "L1+T" T`).
- Режим `--mode toggle-dots` (двойной тап → ё) **не подходит**: прошивка включает
  автоповтор/залипание выхода до повторного тапа (проверено, см. TASKS.md).
- Fn+«е» при включённом Mod-Tap продолжает работать (Fn-слой выше keymatrix).

## Подсветка (User Picture, режим 13)

Статичная по-зонам схема в стиле TokyoNight заливается в прошивку как userpic
(слот 0, режим User Picture):

| Зона | Цвет |
|------|------|
| Буквы | синий `#7aa2f7` |
| Цифры (1–0) | зелёный `#9ece6a` |
| Столбик справа (Home/Del/PgUp/PgDn) | жёлтый `#e0af68` |
| Вспомогательные (Esc, F-ряд, моды, Enter, Space…) | фиолетовый `#bb9af7` |

Картинка-исходник: `assets/userpic-tokyonight.png` (скейл ×10, заливать с `--nearest`).

```bash
sudo iot_driver userpic --nearest assets/userpic-tokyonight.png -s 0   # режим станет 13
```

Особенности прошивки: при нажатии любой клавиши в этом режиме она кратко
вспыхивает цветом `(0,200,200)` (cyan) — это фича прошивки, не скрипт.
Схема раскладки картинки: индекс клавиши `i` → пиксель `(col=i/6, row=i%6)`,
col-major, 16×6.

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

## Реверс-инжиниринг и внешние ссылки

Протокол этой клавиатуры раскрыт полностью — реверсить её самому не нужно, только
пользоваться готовым:

- **echtzeit-solutions/monsgeek-akko-linux** (same as `iot_driver`) — драйвер и реверс RY5088:
  - `docs/PROTOCOL.md` — протокол подсветки (`SET_LEDPARAM` 0x07/0x87, `SET_USERPIC` 0x0C,
    режимы 13=User Picture, 25=Per-Key; per-LED стриминг `0xE8` — только после MONSMOD-патча прошивки);
  - `data/devices.json` — каталог устройств: AK680 MAX = 4 записи, лэйаут `Common68_K80X68`;
  - `data/key_layouts.json` — полный маппинг имён клавиш по индексам.
- **dot-agi/ry5088-flasher** — флешер и структура прошивки (платформа RY5088: AT32F405 + PAN1080).
- **Соседка AK680MC** (не MAX) — та же платформа RY5088, но лэйаут `Common68_ak680mcc`
  («del end pgup pgdn») — при поиске лэйаутов не путать. Надёжный дискриминатор — dev_id
  прошивки (USB PID 0x502B/0x502D переиспользуется между моделями).

Прецеденты реверса других AJAZZ (платформа Sonix, к RY5088 неприменимы):
- `gohv/EPOMAKER-Ajazz-AK820-Pro` (`ak820-ctl`) — Rust CLI/GUI для AK820 Pro, 20 режимов RGB;
- `not-nullptr/openajazz` — Rust-демон RGB-эффектов для AK820/AK35i;
- SonixQMK: из AJAZZ там только AK33 Rev1/2, проект официально deprecated.

## Диагностика

- `iot_driver info` — VID/PID, Device ID, имя прошивки.
- `hyprctl devices` — текущая раскладка каждой клавиатуры.
- `hyprctl binds | grep -A2 code:108|105` — проверка биндов.

Тестировано на Arch Linux (Hyprland/Wayland), 2026-08-30.