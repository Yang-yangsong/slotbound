import ctypes
import json
import os
from pathlib import Path
import re
import struct
import sys
import time
import gdb

here = Path(__file__).resolve().parent
sys.path.insert(0, str(here))
from reset_save import purchased_upgrades
from slotbound_profile import KEYS, SYMBOL_KEYS, TOTAL, valid_distribution, valid_symbols
from slotbound_paths import DATA

odds = (here / "slotbound_odds.lua").read_bytes()
section_repair = (here / "slotbound_sections.lua").read_bytes()
receipt = DATA / "loaded.txt"


def configured_weights(variable, keys, validate):
    raw = os.environ.get(variable)
    if raw is None:
        return b"nil"
    values = json.loads(raw)
    if not validate(values):
        raise ValueError(f"Invalid Slotbound weights in {variable}.")
    entries = [f"{key}={value}/{TOTAL}" for key, value in zip(keys, values)]
    return ("{" + ",".join(entries) + "}").encode("ascii")


weights = configured_weights("SLOTBOUND_MOD_WEIGHTS", KEYS, valid_distribution)
symbols = configured_weights("SLOTBOUND_MOD_SYMBOLS", SYMBOL_KEYS, valid_symbols)


def section_history():
    backups = DATA / "backups"
    snapshots = [*backups.glob("save_fallback.dat*"), *backups.glob("reset-*/save_fallback.dat")]
    purchased = set()
    for snapshot in snapshots:
        purchased.update(purchased_upgrades(snapshot.read_bytes()))
    for name in purchased:
        if not re.fullmatch(rb"[a-zA-Z_][a-zA-Z0-9_]*", name):
            raise ValueError(f"Unexpected upgrade identifier: {name!r}")
    return b"{" + b",".join(name + b"=true" for name in sorted(purchased)) + b"}"


history = section_history()
confirmed_unit = b"true" if (DATA / "confirmed-unit-section").is_file() else b"false"
kernel = ctypes.WinDLL("kernel32", use_last_error=True)
pointer, size_t, uint = ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32
kernel.OpenProcess.argtypes = [uint, ctypes.c_int, uint]
kernel.OpenProcess.restype = pointer
kernel.VirtualAllocEx.argtypes = [pointer, pointer, size_t, uint, uint]
kernel.VirtualAllocEx.restype = pointer
kernel.CloseHandle.argtypes = [pointer]
patched = False
replacement_arguments = None

def register(name):
    return int(gdb.parse_and_eval(name))


def verify_breakpoint():
    if not patched:
        raise RuntimeError("Slotbound did not load the expected upgrade module.")


def verify_loaded_arguments():
    inferior = gdb.selected_inferior()
    actual = struct.unpack("<QQ", bytes(inferior.read_memory(register("$rsp") + 0x30, 16)))
    if actual != replacement_arguments:
        raise RuntimeError("Slotbound's Lua loader did not receive the mods.")


def verify_module_loaded():
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if receipt.exists() and receipt.read_text(encoding="ascii") == "Upgrade module loaded":
            print("Slotbound loaded the Campaign, Endless, and upgrade mods.")
            return
        time.sleep(0.1)
    raise RuntimeError("Slotbound did not confirm that the mods initialized.")


class CampaignOdds(gdb.Breakpoint):
    def stop(self):
        global patched, replacement_arguments
        inferior = gdb.selected_inferior()
        try:
            name = gdb.parse_and_eval("(char *)$r9").string(encoding="ascii", errors="replace")
        except (gdb.error, UnicodeError):
            return False
        if name != "@src/ui/upgrade.lua":
            return False
        expected = bytes.fromhex("48 89 54 24 30 4c 89 44 24 38")
        if bytes(inferior.read_memory(register("$pc"), len(expected))) != expected:
            raise RuntimeError("Unsupported Slotbound Lua runtime layout.")

        length = register("$r8")
        assert 100 < length < 1000000
        original = bytes(inferior.read_memory(register("$rdx"), length))
        assert original.startswith(b"\x1bLJ\x02") and b"applyUpgradeEffects" in original
        encoded = ''.join('\\%03d' % b for b in original).encode('ascii')
        receipt.unlink(missing_ok=True)
        receipt_path = b'"' + b"".join(b"\\%03d" % byte for byte in receipt.as_posix().encode("utf-8")) + b'"'
        replacement = (
            b"local wrap=(function()\n" + odds + b"\nend)()\n"
            b"local repair=(function()\n" + section_repair + b"\nend)()\n"
            b"local original=assert(loadstring(\"" + encoded + b"\", '@src/ui/upgrade.lua'))\n"
            b"local upgrade=repair(wrap(original, " + weights + b", " + symbols + b")(...), " + history + b", " + confirmed_unit + b")\n"
            b"local file=io.open(" + receipt_path + b", 'w')\n"
            b"if file then file:write('Upgrade module loaded'); file:close() end\n"
            b"return upgrade\n"
        )
        process = kernel.OpenProcess(0x0008, 0, inferior.pid)
        if not process:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            address = kernel.VirtualAllocEx(process, None, len(replacement), 0x3000, 0x04)
            if not address:
                raise ctypes.WinError(ctypes.get_last_error())
            inferior.write_memory(address, replacement)
        finally:
            kernel.CloseHandle(process)

        gdb.execute(f"set $rdx = {address}")
        gdb.execute(f"set $r8 = {len(replacement)}")
        replacement_arguments = address, len(replacement)
        patched = True
        return True

CampaignOdds("luaL_loadbuffer")
