#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AK680 MAX (AJAZZ, RY5088 v306, VID:PID 3151:502D) — заливка firmware-конфига из
репозитория jazz-crab/ak680-max-layout (branch ak680-max, README.md).

Работает ПОД WINDOWS через hidapi (штатный HID-интерфейс клавиатуры, интерфейс 2,
usage page 0xFFFF / usage 0x02). Драйвер iot_driver для этого не нужен, права
администратора не нужны, клавиатура продолжает работать.

Протокол (см. monsgeek-akko-linux docs/PROTOCOL.md):
  feature report 65 байт: [report_id=0][cmd][payload 63][checksum @buf[8]]
    checksum Bit7 = 255 - sum(buf[1:8])   (в payload это индекс 6)
    checksum Bit8 = 255 - sum(buf[1:9])   (в payload это индекс 7; LED 0x07)
  Ответ: buf[0]=report_id, дальше payload. Часть команд отвечает echo (payload[0]==cmd),
  страничные — без echo (просто 64 байта данных).

Что делает (ровно как README.md репозитория):
  1. base-layer ремапы: 3 (Caps) -> Esc, 1 (физический Esc) -> ` (grave: в EN это `,
     в RU — ё), 85 -> Delete, 86 -> Home, 87 -> PrintScr, 88 -> End
  2. Fn-слой: Fn+T -> ` (grave) — запасной способ напечатать ё
  3. Hall Effect: активация 1.0mm (raw 100), отпускание 1.5mm (raw 150), все 90 позиций
  4. подсветка: userpic TokyoNight, раскрашенный ПО КЛАВИШАМ (через таблицу матрицы),
     в слот 0 + режим LED 13

Режимы:
  --read-only   только прочитать и напечатать текущее состояние (+ сохранить бэкап)
  --verify      прочитать и сравнить с целевым состоянием (включая подсветку)
  --yes         реально писать (без него — dry-run)
  --no-userpic  не трогать подсветку
  --image FILE  залить свою картинку вместо схемы TokyoNight (15x6, порядок матрицы)
  --write-png DIR  сохранить userpic-tokyonight.png (15x6, данные) и
                   keyboard-tokyonight.png (человеческое превью физической раскладки)
"""
import argparse, json, os, sys, time

import hid
from PIL import Image, ImageDraw, ImageFont

VID, PID = 0x3151, 0x502D
REPORT_SIZE = 65
INPUT_REPORT_SIZE = 64
PRECISION = 100          # v306 (raw 0x0306 = 774 >= 768) -> 0.01mm на единицу

CMD_SET_RESET = 0x01
CMD_SET_LEDPARAM = 0x07
CMD_SET_KEYMATRIX = 0x0A
CMD_SET_USERPIC = 0x0C
CMD_SET_FN = 0x10
CMD_SET_MULTI_MAGNETISM = 0x65
CMD_GET_PROFILE = 0x84
CMD_GET_LEDPARAM = 0x87
CMD_GET_KEYMATRIX = 0x8A
CMD_GET_USERPIC = 0x8C
CMD_GET_USB_VERSION = 0x8F
CMD_GET_FN = 0x90
CMD_GET_MULTI_MAGNETISM = 0xE5

MAG_PRESS, MAG_LIFT, MAG_MODE = 0x00, 0x01, 0x07

KEY_COUNT = 90           # matrix extent этой платы (device_matrices.json: последняя занятая позиция 89)
LAYOUT_COLS = 15         # USERPIC: 6 строк, колонок = 89/6+1
LAYOUT_ROWS = 6
USERPIC_BYTES = 126 * 3  # слот userpic: 21x6 максимум, у этой платы занято 15x6

KEY = {"Escape": 0x29, "Delete": 0x4C, "Home": 0x4A, "PrintScr": 0x46, "End": 0x4D,
       "grave": 0x35}

# base-слой: позиция матрицы -> HID usage.
#   1  = физический Esc/угол -> ` (в русской раскладке это ё)
#   3  = физический Caps     -> Esc (CapsLock не нужен)
#   85..88 = правый столбец  -> Delete / Home / PrintScreen / End
#            (PrtSc и End стоят в исходном порядке: 87 = PrtSc, 88 = End)
BASE_REMAPS = [(3, KEY["Escape"]), (1, KEY["grave"]), (85, KEY["Delete"]),
               (86, KEY["Home"]), (87, KEY["PrintScr"]), (88, KEY["End"])]
FN_REMAPS = [(32, KEY["grave"])]          # Fn + физический T (index 32) -> ё
ACTUATION_MM, RELEASE_MM = 1.0, 1.5
USERPIC_SLOT = 0


# --------------------------------------------------------------------------- #
# подсветка: userpic — это НЕ фотография клавиатуры
# --------------------------------------------------------------------------- #
# Прошивка раскладывает userpic по позициям электрической матрицы: байты
# [3*i : 3*i+3] — цвет клавиши на позиции i (картинка 6 строк, x = i // 6,
# y = i % 6, то есть column-major). Ряды матрицы — не физические ряды клавиатуры.
#
# Поэтому нарисованная «как клавиатура» картинка 15x6 попадает на соседние
# клавиши: в старой схеме Enter, Backspace, `\` и стрелки получали цвет правого
# столбца, а сам правый столбец (позиции 85..89) оказывался чёрным.
#
# Ниже — заводские HID usage по позициям: data/device_matrices.json,
# 12625:20525:2255 / lэйаут Common68_K80X68 (0 = клавиши нет).
MATRIX_USAGE = [
    0, 41, 43, 57, 225, 224, 0, 30, 20, 4,
    0, 0, 0, 31, 26, 22, 29, 227, 0, 32,
    8, 7, 27, 226, 0, 33, 21, 9, 6, 0,
    0, 34, 23, 10, 25, 0, 0, 35, 28, 11,
    5, 44, 0, 36, 24, 13, 17, 0, 0, 37,
    12, 14, 16, 0, 0, 38, 18, 15, 54, 230,
    0, 39, 19, 51, 55, 0, 0, 45, 47, 52,
    56, 228, 0, 46, 48, 0, 229, 80, 0, 42,
    49, 40, 82, 81, 0, 74, 76, 75, 78, 79,
] + [0] * (LAYOUT_COLS * LAYOUT_ROWS - 90)

# Цвета ДЛЯ КЛАВИАТУРЫ. Это НЕ hex-коды TokyoNight, а СОЧНЫЕ (=насыщенные)
# варианты тех же зон: пастельные #ff9e64 / #e0af68 / #f7768e / #bb9af7 на
# подсветке вымываются (у тёплых много синего — он яркий и добавляет белизны,
# у фиолетового синий в максимуме). Поэтому у оранжевого и красного B = 0,
# фиолетовый сдвинут в красную сторону. Превью рисуется отдельной палитрой
# PREVIEW (пастельной) — картинка должна выглядеть как TokyoNight.
TOKYO = {
    "blue":    (0x7A, 0xA2, 0xF7),   # синий      — A..Z, вся пунктуация, `
    "orange":  (0xFF, 0x4C, 0x00),   # красно-оранжевый, чуть светлее выбранного — 1..0, - =, Space, стрелки
    "red":     (0xFF, 0x00, 0x12),   # красный, чуть мягче, синего вполовину — Enter, Backspace, Del, Esc, Win, PrtSc, Fn
    "purple":  (0xCC, 0x33, 0xE8),   # фиолетовый, чуть краснее — Tab, Home/End, Shift/Ctrl/Alt
}

# Яркость зоны на железе (1.0 = как есть). Оранжевый выбран на глаз из
# калибровочной полосы (12 вариантов на цифровом ряду): вариант "-" =
# raw (140, 14, 0). На полной яркости он вымывался в беж/розовый. Попытка
# «бледнее» через синий канал дала розовый, поэтому чуть светлее сделано
# только яркостью: raw (148, 17, 0), B по-прежнему 0.
# Красный тоже чуть приглушён (0.88) и получил каплю синего — юзер попросил
# «чуть менее ярким, чуть розовато-синего»; после этого сказал, что розоват,
# поэтому синего оставлено вполовину: raw (224, 0, 13).
LED_LEVEL = {"orange": 0.58, "red": 0.88}

# Цвета ДЛЯ ПРЕВЬЮ (пастельный TokyoNight) — только картинка, в прошивку не идут.
PREVIEW = {
    "blue":    (0x7A, 0xA2, 0xF7),
    "orange":  (0xFF, 0x9E, 0x64),
    "red":     (0xF7, 0x76, 0x8E),
    "purple":  (0xBB, 0x9A, 0xF7),
}

# Компенсация каналов.
# На этой плате светодиоды разной эффективности: при одинаковом байте зелёный
# светит заметно ярче красного, синий — чуть ярче. Измерено шкалами
# (calibrate_colors.py): жёлтый (R=G по восприятию) наступает при G ≈ 38% от R,
# маджента — при B ≈ 85% от R. Отсюда «белый» = (255, 98, 120): если писать
# сырые байты, любой пастельный цвет уезжает в болотно-зелёный, а фиолетовый —
# в синий. Поэтому цвет пересчитывается так, чтобы ВОСПРИНИМАЕМОЕ отношение
# R:G:B совпало с задуманным (и ни один канал не вылезал за 255).
LED_GAIN = (0.384, 1.0, 0.469)   # воспринимаемая яркость канала на единицу байта


def to_device(rgb, level=1.0):
    """Задуманный цвет -> байты для прошивки с учётом дисбаланса каналов."""
    ch = [c / k for c, k in zip(rgb, LED_GAIN)]
    scale = 255.0 * level / max(ch)
    return tuple(max(0, min(255, round(c * scale))) for c in ch)


def zone_name(usage):
    """Зона клавиши по её ДЕЙСТВИЮ (usage уже с учётом base-ремапа)."""
    if 0x04 <= usage <= 0x1D:                    # A..Z
        return "blue"
    if 0x1E <= usage <= 0x27 or usage in (0x2D, 0x2E):   # 1..0, - =
        return "orange"
    if usage in (0x2F, 0x30, 0x31, 0x33, 0x34, 0x36, 0x37, 0x38, 0x35):
        return "blue"                            # [ ] \ ; ' , . / и `
    if usage in (0x28, 0x2A, 0x29):              # Enter, Backspace, Esc (на месте Caps)
        return "red"
    if usage in (0x4C, 0xE3):                    # Delete, Win
        return "red"
    if usage in (0x4A, 0x4D):                    # Home, End
        return "purple"
    if usage == 0x46:                            # PrintScreen
        return "red"
    if usage == 0x4B or usage in (0x4E, 0x4F, 0x50, 0x51, 0x52):   # PgUp/PgDn, стрелки
        return "orange"
    if usage == 0x2C:                            # Space
        return "orange"
    return "purple"                              # Tab, Space, модификаторы, Fn


def zone_color(usage):
    """Цвет клавиши на клавиатуре (сочный)."""
    return TOKYO[zone_name(usage)]


def preview_color(usage):
    """Цвет той же зоны на картинке (пастельный TokyoNight)."""
    return PREVIEW[zone_name(usage)]


BASE_USAGE = dict(BASE_REMAPS)     # позиция -> usage на base-слое после ремапа

# Fn — единственная клавиша без HID usage в матрице (позиция 65, нижний ряд
# между правым Alt и правым Ctrl), поэтому прошивка её не красит. Адрес проверен
# на железе 2026-10-26: при заливке этой позиции Fn загорается. Красим её напрямую
# красным, как остальные «служебные» клавиши (по просьбе юзера).
FN_POS = 65
FN_USAGE = KEY["Escape"]           # red


def build_userpic():
    """15x6 в порядке матрицы: цвет клавиши попадает ровно на свою позицию."""
    data = bytearray(USERPIC_BYTES)
    for pos in range(LAYOUT_COLS * LAYOUT_ROWS):
        usage = BASE_USAGE.get(pos, MATRIX_USAGE[pos])
        if not usage:
            if pos == FN_POS:
                data[pos * 3:pos * 3 + 3] = bytes(to_device(zone_color(FN_USAGE),
                                                            LED_LEVEL.get(zone_name(FN_USAGE), 1.0)))
            continue                              # пустая позиция — не горит
        data[pos * 3:pos * 3 + 3] = bytes(to_device(zone_color(usage),
                                                    LED_LEVEL.get(zone_name(usage), 1.0)))
    return bytes(data)


# Физическая раскладка 65% — ТОЛЬКО для превью-картинки: (usage, подпись, ширина).
# Подписи — то, что клавиша ДЕЛАЕТ после ремапа (угол = ё, Caps = Esc).
PHYS_LAYOUT = [
    [(0x35, "`", 1), (0x1E, "1", 1), (0x1F, "2", 1), (0x20, "3", 1), (0x21, "4", 1),
     (0x22, "5", 1), (0x23, "6", 1), (0x24, "7", 1), (0x25, "8", 1), (0x26, "9", 1),
     (0x27, "0", 1), (0x2D, "-", 1), (0x2E, "=", 1), (0x2A, "Bksp", 2), (0x4C, "Del", 1)],
    [(0x2B, "Tab", 1.5), (0x14, "Q", 1), (0x1A, "W", 1), (0x08, "E", 1), (0x15, "R", 1),
     (0x17, "T", 1), (0x1C, "Y", 1), (0x18, "U", 1), (0x0C, "I", 1), (0x12, "O", 1),
     (0x13, "P", 1), (0x2F, "[", 1), (0x30, "]", 1), (0x31, "\\", 1.5), (0x4A, "Home", 1)],
    [(0x29, "Esc", 1.75), (0x04, "A", 1), (0x16, "S", 1), (0x07, "D", 1), (0x09, "F", 1),
     (0x0A, "G", 1), (0x0B, "H", 1), (0x0D, "J", 1), (0x0E, "K", 1), (0x0F, "L", 1),
     (0x33, ";", 1), (0x34, "'", 1), (0x28, "Enter", 2.25), (0x46, "PrtSc", 1)],
    [(0xE1, "Shift", 2.25), (0x1D, "Z", 1), (0x1B, "X", 1), (0x06, "C", 1), (0x19, "V", 1),
     (0x05, "B", 1), (0x11, "N", 1), (0x10, "M", 1), (0x36, ",", 1), (0x37, ".", 1),
     (0x38, "/", 1), (0xE6, "Shift", 1.75), (0x52, "Up", 1), (0x4D, "End", 1)],
    [(0xE0, "Ctrl", 1.25), (0xE3, "Win", 1.25), (0xE2, "Alt", 1.25), (0x2C, "Space", 5.5),
     (0xE5, "Alt", 1.25), (None, "Fn", 1.25), (0xE4, "Ctrl", 1.25),
     (0x50, "Left", 1), (0x51, "Down", 1), (0x4F, "Right", 1)],
]

BG = (0x1A, 0x1B, 0x26)
LEGEND = [
    ((0x35,), "letters, punctuation"),
    ((0x1E,), "digits, Space, arrows"),
    ((0x28,), "Enter, Bksp, Del, Esc, Win, PrtSc, Fn"),
    ((0x2B,), "Home, End, Tab, modifiers"),
]


def load_font(filename, size):
    """Шрифт для превью: ищем рядом со скриптом, в assets/fonts, затем в системе."""
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(here, "fonts", filename),
        os.path.join(here, filename),
        os.path.join(os.path.dirname(here), "assets", "fonts", filename),
    ]
    candidates += [filename, "consola.ttf", "segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"]
    for name in candidates:
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default()


def write_pngs(directory):
    """userpic-tokyonight.png (15x6, ровно данные) + keyboard-tokyonight.png (превью).

    В userpic-файл идут БАЙТЫ ДЛЯ ПРОШИВКИ (сочные цвета + компенсация каналов),
    а превью рисуется пастельной палитрой TokyoNight (PREVIEW) — это картинка
    «как задумано», а не точная копия байтов.
    """
    os.makedirs(directory, exist_ok=True)
    data = build_userpic()

    img = Image.new("RGB", (LAYOUT_COLS, LAYOUT_ROWS))
    for pos in range(LAYOUT_COLS * LAYOUT_ROWS):
        img.putpixel((pos // LAYOUT_ROWS, pos % LAYOUT_ROWS), tuple(data[pos * 3:pos * 3 + 3]))
    img.save(os.path.join(directory, "userpic-tokyonight.png"))

    u = 44                                       # px на 1u
    pad, gap = 14, 4
    cols = max(sum(w for _, _, w in row) for row in PHYS_LAYOUT)
    width = int(cols * u) + pad * 2 + 8
    board_h = len(PHYS_LAYOUT) * u
    title_h = 34
    legend_row_h = 26
    legend_cols = 2                             # JetBrains Mono шире — по две колонки
    legend_h = legend_row_h * ((len(LEGEND) + legend_cols - 1) // legend_cols) + 8
    canvas = Image.new("RGB", (width, int(pad * 2 + board_h + title_h + legend_h)), BG)
    draw = ImageDraw.Draw(canvas)
    font = load_font("JetBrainsMono-Regular.ttf", 12)
    font_title = load_font("JetBrainsMono-Bold.ttf", 17)
    draw.text((pad, pad - 2), "AJAZZ AK680 MAX RGB",
              fill=(0xC0, 0xCA, 0xF5), font=font_title)
    top = pad + title_h
    for row_i, row in enumerate(PHYS_LAYOUT):
        x = 0.0
        for usage, label, w in row:
            x0 = pad + x * u
            y0 = top + row_i * u
            color = preview_color(usage or 0x28)      # Fn (без usage) — красная, как на железе
            draw.rounded_rectangle([x0 + gap, y0 + gap,
                                    x0 + w * u - gap, y0 + u - gap],
                                   radius=6, fill=color)
            if label:
                tw = draw.textlength(label, font=font)
                draw.text((x0 + w * u / 2 - tw / 2, y0 + u / 2 - 7), label,
                          fill=BG, font=font)
            x += w
    # легенда: что какой цвет значит
    lw = (width - pad * 2) // legend_cols
    ly = top + board_h + 8
    for i, (usages, text) in enumerate(LEGEND):
        cx = pad + (i % legend_cols) * lw
        cy = ly + (i // legend_cols) * legend_row_h
        draw.rounded_rectangle([cx, cy, cx + 16, cy + 16], radius=4,
                               fill=preview_color(usages[0]))
        draw.text((cx + 22, cy + 1), text, fill=(0xC0, 0xCA, 0xF5), font=font)
    canvas.save(os.path.join(directory, "keyboard-tokyonight.png"))
    return directory


# --------------------------------------------------------------------------- #
# протокол
# --------------------------------------------------------------------------- #
def build(cmd, data=b"", bit8=False):
    buf = bytearray(REPORT_SIZE)
    buf[0] = 0
    buf[1] = cmd
    n = min(len(data), REPORT_SIZE - 2)
    buf[2:2 + n] = data[:n]
    if bit8:
        buf[9] = (255 - (sum(buf[1:9]) & 0xFF)) & 0xFF
    else:
        buf[8] = (255 - (sum(buf[1:8]) & 0xFF)) & 0xFF
    return bytes(buf)


class Keyboard:
    def __init__(self, verbose=True):
        dev = None
        for d in hid.enumerate(VID, PID):
            if d.get("usage_page") == 0xFFFF and d.get("usage") == 0x02:
                dev = d
                break
        if dev is None:
            raise SystemExit("Не найден конфигурационный HID-интерфейс AK680 MAX "
                             "(VID 3151 / PID 502D / usage_page 0xFFFF / usage 0x02).")
        self.path = dev["path"]
        self.h = hid.device()
        self.h.open_path(self.path)
        self.verbose = verbose

    def close(self):
        try:
            self.h.close()
        except Exception:
            pass

    # --- низкий уровень ---
    def _send(self, cmd, data=b"", bit8=False):
        self.h.send_feature_report(build(cmd, data, bit8))

    def _read(self, tries=4, gap=0.05):
        last = None
        for _ in range(tries):
            try:
                last = bytes(self.h.get_feature_report(0, REPORT_SIZE))
                return last
            except Exception:
                time.sleep(gap)
        return last

    def send(self, cmd, data=b"", bit8=False, delay=0.03):
        self._send(cmd, data, bit8)
        time.sleep(delay)

    def query_echo(self, cmd, data=b"", tries=8, gap=0.06):
        for _ in range(tries):
            self._send(cmd, data)
            time.sleep(gap)
            r = self._read(tries=2, gap=gap)
            if r and r[1] == cmd:
                return r[1:]
        return None

    def query_page(self, cmd, data=b"", tries=8, gap=0.06):
        for _ in range(tries):
            self._send(cmd, data)
            time.sleep(gap)
            r = self._read(tries=2, gap=gap)
            if r is not None and len(r[1:]) == INPUT_REPORT_SIZE:
                return r[1:]
        return None

    # --- командные обёртки ---
    def info(self):
        r = self.query_echo(CMD_GET_USB_VERSION)
        if not r:
            return None
        dev_id = int.from_bytes(r[1:5], "little")
        ver = int.from_bytes(r[7:9], "little")
        return {"device_id": dev_id, "version_raw": ver, "version": f"v{ver >> 8}{ver & 0xFF:02d}"}

    def active_profile(self):
        r = self.query_echo(CMD_GET_PROFILE)
        return r[1] if r else 0

    def get_keymatrix(self, profile, layer, pages=6):
        out = b""
        for p in range(pages):
            pg = self.query_page(CMD_GET_KEYMATRIX, bytes([profile, 0xFF, p, layer]))
            if pg is None:
                return None
            out += pg
        return out

    def get_keymatrix_entry(self, profile, layer, idx):
        """Прочитать одно 4-байтовое поле (только нужная страница)."""
        page = (idx * 4) // INPUT_REPORT_SIZE
        pg = self.query_page(CMD_GET_KEYMATRIX, bytes([profile, 0xFF, page, layer]))
        if pg is None:
            return None
        off = (idx * 4) % INPUT_REPORT_SIZE
        return pg[off:off + 4]

    def get_fn(self, profile, sysmode=0, pages=6):
        out = b""
        for p in range(pages):
            pg = self.query_page(CMD_GET_FN, bytes([sysmode, profile, 0xFF, p]))
            if pg is None:
                return None
            out += pg
        return out

    def get_fn_entry(self, profile, idx, sysmode=0):
        page = (idx * 4) // INPUT_REPORT_SIZE
        pg = self.query_page(CMD_GET_FN, bytes([sysmode, profile, 0xFF, page]))
        if pg is None:
            return None
        off = (idx * 4) % INPUT_REPORT_SIZE
        return pg[off:off + 4]

    def get_magnetism(self, sub, pages=3):
        out = b""
        for p in range(pages):
            pg = self.query_page(CMD_GET_MULTI_MAGNETISM, bytes([sub, 0x01, p]))
            if pg is None:
                return None
            out += pg
        return out

    def get_led(self):
        r = self.query_echo(CMD_GET_LEDPARAM)
        return r

    def get_userpic(self, slot, blocks=6):
        out = b""
        for b in range(blocks):
            pg = self.query_page(CMD_GET_USERPIC, bytes([slot, 0xFF, b]))
            if pg is None:
                return None
            out += pg
        return out[:USERPIC_BYTES]

    # --- запись ---
    def set_keymatrix(self, profile, idx, hid_code, layer=0, enabled=1):
        data = bytes([profile, idx, 0, 0, enabled, layer, 0, 0, 0, hid_code, 0])
        self.send(CMD_SET_KEYMATRIX, data)

    def set_fn(self, profile, idx, hid_code, fn_sys=0):
        data = bytes([fn_sys, profile, idx, 0, 0, 0, 0, 0, 0, hid_code, 0])
        self.send(CMD_SET_FN, data)

    def set_keymatrix_verified(self, profile, idx, hid_code, layer=0, tries=8):
        """Пишем и сразу читаем назад: прошивка иногда «глотает» подряд идущие записи."""
        for _ in range(tries):
            self.set_keymatrix(profile, idx, hid_code, layer=layer)
            time.sleep(0.15)
            e = self.get_keymatrix_entry(profile, layer, idx)
            if e is not None and len(e) == 4 and e[2] == hid_code:
                return True
        return False

    def set_fn_verified(self, profile, idx, hid_code, fn_sys=0, tries=8):
        for _ in range(tries):
            self.set_fn(profile, idx, hid_code, fn_sys=fn_sys)
            time.sleep(0.15)
            e = self.get_fn_entry(profile, idx, sysmode=fn_sys)
            if e is not None and len(e) == 4 and e[2] == hid_code:
                return True
        return False

    def set_magnetism(self, sub, values_u16, key_count=KEY_COUNT):
        raw = b"".join(int(v).to_bytes(2, "little") for v in values_u16[:key_count])
        pages = max(1, (len(raw) + 55) // 56)
        for page in range(pages):
            chunk = raw[page * 56:(page + 1) * 56]
            is_last = 1 if page == pages - 1 else 0
            data = bytes([sub, 0x01, page, is_last, 0, 0, 0]) + chunk
            self.send(CMD_SET_MULTI_MAGNETISM, data, delay=0.25 if is_last else 0.03)

    def set_userpic(self, slot, data):
        slot_data = bytes(data[:USERPIC_BYTES]).ljust(USERPIC_BYTES, b"\x00")
        pages = (USERPIC_BYTES + 55) // 56
        for page in range(pages):
            chunk = slot_data[page * 56:(page + 1) * 56]
            payload = bytes([slot, 0xFF, page, len(chunk), 1 if page == pages - 1 else 0, 0, 0]) + chunk
            self.send(CMD_SET_USERPIC, payload, delay=0.012)

    def set_led_userpic(self, slot):
        # [mode, инверт. скорость, яркость, option, r, g, b]; в режиме 13 цвет
        # (0,200,200) — это цвет вспышки при нажатии, его задаёт прошивка.
        data = bytes([13, 4, 4, (slot << 4) & 0xF0, 0, 200, 200])
        self.send(CMD_SET_LEDPARAM, data, bit8=True)


# --------------------------------------------------------------------------- #
# состояние / бэкап
# --------------------------------------------------------------------------- #
def read_state(kb, profile, want_userpic=False):
    st = {"profile": profile}
    st["info"] = kb.info()
    st["keymatrix"] = {f"layer{l}": (kb.get_keymatrix(profile, l) or b"").hex() for l in range(4)}
    st["fn_win"] = (kb.get_fn(profile, 0) or b"").hex()
    led = kb.get_led()
    st["led"] = led.hex() if led else None
    press = kb.get_magnetism(MAG_PRESS)
    lift = kb.get_magnetism(MAG_LIFT)
    mode = kb.get_magnetism(MAG_MODE)
    st["actuation_raw"] = [int.from_bytes(press[i:i + 2], "little") for i in range(0, min(len(press), KEY_COUNT * 2), 2)] if press else None
    st["release_raw"] = [int.from_bytes(lift[i:i + 2], "little") for i in range(0, min(len(lift), KEY_COUNT * 2), 2)] if lift else None
    st["mode_raw"] = list(mode[:KEY_COUNT]) if mode else None
    if want_userpic:
        up = kb.get_userpic(USERPIC_SLOT)
        st["userpic_slot0"] = up.hex() if up else None
    return st


def entries(blob, n=KEY_COUNT):
    return [blob[i * 4:i * 4 + 4] for i in range(n)] if blob else []


def print_state(st):
    print(f"  device_id={st['info']['device_id']} firmware={st['info']['version']} profile={st['profile']}")
    print(f"  LED: {(st['led'] or '')[:20]}")
    for l in range(4):
        e = entries(bytes.fromhex(st["keymatrix"][f"layer{l}"]))
        changed = [(i, e[i][2]) for i in range(len(e)) if e[i] != b"\x00\x00\x00\x00"]
        print(f"  keymatrix layer{l}: {len(changed)} непустых")
    fn = entries(bytes.fromhex(st["fn_win"]))
    print(f"  Fn(Win): {sum(1 for x in fn if x != b'\x00'*4)} непустых;  Fn+T(idx32)={fn[32].hex()}")
    if st["actuation_raw"]:
        print(f"  активация: raw={sorted(set(st['actuation_raw']))} ({sorted(set(st['actuation_raw']))[0] / PRECISION}мм)")
    if st["release_raw"]:
        print(f"  отпускание: raw={sorted(set(st['release_raw']))} ({sorted(set(st['release_raw']))[0] / PRECISION}мм)")


def target_userpic(image=None):
    if not image:
        return build_userpic()
    img = Image.open(image).convert("RGB").resize((LAYOUT_COLS, LAYOUT_ROWS), Image.NEAREST)
    data = bytearray(USERPIC_BYTES)
    for pos in range(LAYOUT_COLS * LAYOUT_ROWS):
        x, y = pos // LAYOUT_ROWS, pos % LAYOUT_ROWS     # column-major, 6 строк
        data[pos * 3:pos * 3 + 3] = bytes(img.getpixel((x, y)))
    return bytes(data)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--read-only", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--yes", action="store_true", help="реально писать")
    ap.add_argument("--no-userpic", action="store_true")
    ap.add_argument("--image", default=None,
                    help="своя картинка 15x6 в порядке матрицы (по умолчанию — схема TokyoNight)")
    ap.add_argument("--write-png", default=None, metavar="DIR",
                    help="сохранить userpic-tokyonight.png (данные) и keyboard-tokyonight.png (превью)")
    ap.add_argument("--backup-dir", default=os.path.dirname(os.path.abspath(__file__)))
    args = ap.parse_args()

    if args.write_png:
        write_pngs(args.write_png)
        print(f"PNG записаны в {args.write_png}")

    kb = Keyboard()
    profile = kb.active_profile()
    print(f"AK680 MAX найден: {kb.path}")
    info = kb.info()
    print(f"device_id={info['device_id']} firmware={info['version']} (precision {PRECISION} → шаг {1 / PRECISION}мм)")

    st = read_state(kb, profile, want_userpic=True)
    ts = time.strftime("%Y%m%d-%H%M%S")
    bpath = os.path.join(args.backup_dir, f"backup-{ts}.json")
    with open(bpath, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=1)
    print(f"\nТекущее состояние (бэкап: {bpath}):")
    print_state(st)

    if args.read_only:
        kb.close(); return 0

    target_act = round(ACTUATION_MM * PRECISION)
    target_rel = round(RELEASE_MM * PRECISION)
    want_pic = None if args.no_userpic else target_userpic(args.image)

    print("\nПлан:")
    print("  base layer: " + ", ".join(f"{i}→0x{c:02X}" for i, c in BASE_REMAPS))
    print("  Fn(Win):    " + ", ".join(f"{i}→0x{c:02X}" for i, c in FN_REMAPS))
    print(f"  активация {ACTUATION_MM}мм (raw {target_act}) / отпускание {RELEASE_MM}мм (raw {target_rel}), {KEY_COUNT} позиций")
    if want_pic:
        total = sum(1 for i in range(0, len(want_pic), 3) if want_pic[i:i + 3] != b"\x00\x00\x00")
        src = args.image if args.image else "схема TokyoNight по клавишам"
        print(f"  подсветка: {src} → userpic слот {USERPIC_SLOT} ({total} клавиш) + режим LED 13")

    if args.verify:
        ok = True
        e = entries(bytes.fromhex(st["keymatrix"]["layer0"]))
        for i, c in BASE_REMAPS:
            got = e[i][2] if i < len(e) else None
            good = got == c
            ok &= good
            print(f"  base[{i}] = 0x{got:02X} ожидалось 0x{c:02X}: {'OK' if good else 'НЕ СОВПАЛО'}")
        fn = entries(bytes.fromhex(st["fn_win"]))
        for i, c in FN_REMAPS:
            got = fn[i][2] if i < len(fn) else None
            good = got == c
            ok &= good
            print(f"  Fn[{i}] = 0x{got:02X} ожидалось 0x{c:02X}: {'OK' if good else 'НЕ СОВПАЛО'}")
        for name, arr, want in (("активация", st["actuation_raw"], target_act), ("отпускание", st["release_raw"], target_rel)):
            good = arr is not None and all(v == want for v in arr)
            ok &= good
            print(f"  {name}: {sorted(set(arr or []))} ожидалось [{want}]: {'OK' if good else 'НЕ СОВПАЛО'}")
        if want_pic:
            got_pic = kb.get_userpic(USERPIC_SLOT)
            good = got_pic == want_pic
            ok &= good
            n_ok = sum(1 for i in range(0, len(want_pic), 3) if want_pic[i:i + 3] != b"\x00\x00\x00")
            print(f"  подсветка (userpic слот {USERPIC_SLOT}, {n_ok} клавиш): {'OK' if good else 'НЕ СОВПАЛО'}")
            led = st["led"] or ""
            good = led[2:4] == "0d"          # led[0] = эхо команды 0x87, дальше режим
            ok &= good
            print(f"  режим LED = 13 (UserPicture): {'OK' if good else 'НЕ СОВПАЛО (' + led[:4] + ')'}")
        kb.close()
        return 0 if ok else 1

    if not args.yes:
        print("\nDRY-RUN: ничего не записано. Добавь --yes чтобы залить.")
        kb.close(); return 0

    print("\n== 1/4. base-layer ремапы ==")
    for i, c in BASE_REMAPS:
        ok = kb.set_keymatrix_verified(profile, i, c, layer=0)
        print(f"  {i} -> 0x{c:02X}  {'OK' if ok else 'НЕ ПОДТВЕРДИЛОСЬ'}")
    time.sleep(0.2)

    print("== 2/4. Fn-слой (Fn+T -> `) ==")
    for i, c in FN_REMAPS:
        ok = kb.set_fn_verified(profile, i, c, fn_sys=0)
        print(f"  Fn[{i}] -> 0x{c:02X}  {'OK' if ok else 'НЕ ПОДТВЕРДИЛОСЬ'}")
    time.sleep(0.2)

    print("== 3/4. Hall Effect ==")
    kb.set_magnetism(MAG_PRESS, [target_act] * KEY_COUNT)
    print(f"  активация {ACTUATION_MM}мм (raw {target_act})")
    kb.set_magnetism(MAG_LIFT, [target_rel] * KEY_COUNT)
    print(f"  отпускание {RELEASE_MM}мм (raw {target_rel})")

    if want_pic:
        print("== 4/4. Подсветка (userpic по клавишам + режим 13) ==")
        kb.set_userpic(USERPIC_SLOT, want_pic)
        kb.set_led_userpic(USERPIC_SLOT)
        print(f"  15x6, слот {USERPIC_SLOT}, режим 13")

    print("\n== Проверка (чтение с устройства) ==")
    kb2 = Keyboard()
    st2 = read_state(kb2, profile, want_userpic=False)
    print_state(st2)
    e = entries(bytes.fromhex(st2["keymatrix"]["layer0"]))
    fn = entries(bytes.fromhex(st2["fn_win"]))
    for i, c in BASE_REMAPS:
        print(f"  base[{i}] = 0x{e[i][2]:02X} (ожидалось 0x{c:02X}) {'OK' if e[i][2] == c else 'НЕ СОВПАЛО'}")
    for i, c in FN_REMAPS:
        print(f"  Fn[{i}] = 0x{fn[i][2]:02X} (ожидалось 0x{c:02X}) {'OK' if fn[i][2] == c else 'НЕ СОВПАЛО'}")
    print(f"  активация: {sorted(set(st2['actuation_raw'] or []))} (ожидалось [{target_act}])")
    print(f"  отпускание: {sorted(set(st2['release_raw'] or []))} (ожидалось [{target_rel}])")
    if want_pic:
        got_pic = kb2.get_userpic(USERPIC_SLOT)
        print(f"  подсветка: {'OK (побайтово совпало)' if got_pic == want_pic else 'НЕ СОВПАЛО'}")
    kb2.close()
    kb.close()
    print("\nГотово.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
