import ctypes
import os
from pathlib import Path
import subprocess
import tempfile
import time

from reset_save import purchased_upgrades
from slotbound_paths import APP_ID, DATA
from slotbound_profile import KEYS, SYMBOL_KEYS, TOTAL, valid_distribution, valid_symbols


ASSETS = Path(__file__).resolve().parent
RECEIPT = DATA / "loaded.txt"
LOADED = "Upgrade module loaded"


def lua_weights(keys, values):
    if values is None:
        return b"nil"
    entries = [f"{key}={value}/{TOTAL}" for key, value in zip(keys, values)]
    return ("{" + ",".join(entries) + "}").encode("ascii")


def lua_string(value):
    return b'"' + b"".join(b"\\%03d" % byte for byte in value.encode("utf-8")) + b'"'


def history():
    backups = DATA / "backups"
    snapshots = [*backups.glob("save_fallback.dat*"), *backups.glob("reset-*/save_fallback.dat")]
    owned = set()
    for snapshot in snapshots:
        owned.update(purchased_upgrades(snapshot.read_bytes()))
    entries = [b"[" + lua_string(name.decode("utf-8")) + b"]=true" for name in sorted(owned)]
    return b"{" + b",".join(entries) + b"}"


def make_script(values, symbols):
    odds = (ASSETS / "slotbound_odds.lua").read_bytes()
    sections = (ASSETS / "slotbound_sections.lua").read_bytes()
    confirmed = b"true" if (DATA / "confirmed-unit-section").is_file() else b"false"
    prefix = (
        b"local wrap=(function()\n" + odds + b"\nend)()\n"
        b"local repair=(function()\n" + sections + b"\nend)()\n"
        b'local original=assert(loadstring("'
    )
    suffix = (
        b'", "@src/ui/upgrade.lua"))\n'
        b"local upgrade=repair(wrap(original, " + lua_weights(KEYS, values) + b", "
        + lua_weights(SYMBOL_KEYS, symbols) + b")(...), " + history() + b", " + confirmed + b")\n"
        b"local file=io.open(" + lua_string(RECEIPT.as_posix()) + b", 'w')\n"
        b"if file then file:write('Upgrade module loaded'); file:close() end\n"
        b"return upgrade\n"
    )
    return prefix, suffix


def launch(game, values, symbols):
    if not valid_distribution(values) or (symbols is not None and not valid_symbols(symbols)):
        raise ValueError("概率配置无效。")
    helper = ASSETS / "slotbound-launch.exe"
    if not helper.is_file():
        raise RuntimeError("找不到启动组件。请重新下载完整版本，或按 README 构建源码。")
    DATA.mkdir(parents=True, exist_ok=True)
    RECEIPT.unlink(missing_ok=True)
    env = {**os.environ, "SteamAppId": APP_ID, "SteamGameId": APP_ID}
    log = DATA / "launch.log"
    # Keep the bundled Python DLL directory out of the external game's search path.
    kernel = ctypes.windll.kernel32
    directory = ctypes.create_unicode_buffer(32768)
    kernel.GetDllDirectoryW(len(directory), directory)
    with tempfile.TemporaryDirectory(dir=DATA) as cache, log.open("wb") as output:
        folder = Path(cache)
        prefix, suffix = folder / "prefix", folder / "suffix"
        first, last = make_script(values, symbols)
        prefix.write_bytes(first)
        suffix.write_bytes(last)
        kernel.SetDllDirectoryW(None)
        try:
            process = subprocess.Popen(
                [helper, game, prefix, suffix], cwd=game.parent, env=env,
                stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        finally:
            kernel.SetDllDirectoryW(directory.value or None)
        try:
            code = process.wait(timeout=32)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            raise RuntimeError(f"启动超时。请查看 {log}") from None
    if code:
        raise RuntimeError(f"改版启动失败。请查看 {log}")
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        if RECEIPT.exists() and RECEIPT.read_text(encoding="ascii") == LOADED:
            return
        time.sleep(0.1)
    raise RuntimeError(f"游戏未确认加载改版。请查看 {log}")
