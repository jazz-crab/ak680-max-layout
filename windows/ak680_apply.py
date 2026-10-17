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
  1. base-layer ремапы: 1->Esc, 85->Delete, 86->Home, 87->PrintScr, 88->End
  2. Fn-слой: Fn+T -> ` (grave)
  3. Hall Effect: активация 1.0mm (raw 100), отпускание 1.5mm (raw 150), все 90 позиций
  4. подсветка: userpic TokyoNight в слот 0 + режим LED 13 (UserPicture)

Режимы:
  --read-only   только прочитать и напечатать текущее состояние (+ сохранить бэкап)
  --verify      прочитать и сравнить с целевым состоянием
  --yes         реально писать (без него — dry-run)
  --no-userpic  не трогать подсветку
"""
import argparse, json, os, sys, time

import hid
from PIL import Image

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
USERPIC_BYTES = 126 * 3

KEY = {"Escape": 0x29, "Delete": 0x4C, "Home": 0x4A, "PrintScr": 0x46, "End": 0x4D, "grave": 0x35}

BASE_REMAPS = [(1, KEY["Escape"]), (85, KEY["Delete"]), (86, KEY["Home"]),
               (87, KEY["PrintScr"]), (88, KEY["End"])]
FN_REMAPS = [(32, KEY["grave"])]          # Fn + физический T (index 32)
ACTUATION_MM, RELEASE_MM = 1.0, 1.5
USERPIC_SLOT = 0


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
        # set_led_with_option(mode=13, brightness=4, speed=0, r=0,g=200,b=200, dazzle=False, slot)
        data = bytes([13, 4 - 0, 4, (slot << 4) & 0xF0, 0, 200, 200])
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--read-only", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--yes", action="store_true", help="реально писать")
    ap.add_argument("--no-userpic", action="store_true")
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument("--image", default=os.path.normpath(os.path.join(here, "..", "assets", "userpic-tokyonight.png")))
    ap.add_argument("--backup-dir", default=os.getcwd(),
                    help="куда класть backup-<ts>.json (по умолчанию текущий каталог; в репо не коммитить)")
    args = ap.parse_args()

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

    print("\nПлан:")
    print(f"  base layer: " + ", ".join(f"{i}→0x{c:02X}" for i, c in BASE_REMAPS))
    print(f"  Fn(Win):    " + ", ".join(f"{i}→0x{c:02X}" for i, c in FN_REMAPS))
    print(f"  активация {ACTUATION_MM}мм (raw {target_act}) / отпускание {RELEASE_MM}мм (raw {target_rel}), {KEY_COUNT} позиций")
    if not args.no_userpic:
        print(f"  подсветка: userpic слот {USERPIC_SLOT} из {args.image} + режим LED 13")

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

    if not args.no_userpic:
        print("== 4/4. Подсветка (userpic + режим 13) ==")
        img = Image.open(args.image).convert("RGB")
        small = img.resize((LAYOUT_COLS, LAYOUT_ROWS), Image.NEAREST)
        data = bytearray()
        for pos in range(LAYOUT_COLS * LAYOUT_ROWS):
            x, y = pos // LAYOUT_ROWS, pos % LAYOUT_ROWS     # col-major, 6 строк
            data += bytes(small.getpixel((x, y)))
        kb.set_userpic(USERPIC_SLOT, bytes(data))
        kb.set_led_userpic(USERPIC_SLOT)
        print(f"  {args.image} ({img.size[0]}x{img.size[1]}) -> {LAYOUT_COLS}x{LAYOUT_ROWS}, слот {USERPIC_SLOT}, режим 13")

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
    kb2.close()
    kb.close()
    print("\nГотово.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
