import os
from pathlib import Path
import re
import shutil
import winreg


DATA = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "SlotboundControls"
SETTINGS = DATA / "paths.txt"
APP_ID = "4459590"


def steam_roots():
    registry_paths = (
        (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Valve\Steam", "InstallPath"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Valve\Steam", "InstallPath"),
    )
    for hive, key, value in registry_paths:
        try:
            with winreg.OpenKey(hive, key) as handle:
                yield Path(winreg.QueryValueEx(handle, value)[0])
        except OSError:
            pass
    for variable in ("ProgramFiles(x86)", "ProgramFiles"):
        if directory := os.environ.get(variable):
            yield Path(directory) / "Steam"


def find_game(roots=None):
    for root in steam_roots() if roots is None else roots:
        libraries = [root]
        index = root / "steamapps" / "libraryfolders.vdf"
        if index.is_file():
            content = index.read_text(encoding="utf-8-sig", errors="replace")
            for name in re.findall(r'"path"\s*"((?:[^"\\]|\\.)*)"', content):
                libraries.append(Path(name.replace("\\\\", "\\")))
        for library in libraries:
            apps = library / "steamapps"
            manifest = apps / f"appmanifest_{APP_ID}.acf"
            directory = "Slotbound"
            if manifest.is_file():
                label = re.search(r'"installdir"\s*"([^"]+)"', manifest.read_text(encoding="utf-8-sig"))
                if label:
                    directory = label[1]
            game = apps / "common" / directory / "Slotbound.exe"
            if game.is_file():
                return game
    return None


def find_gdb():
    candidates = (
        shutil.which("gdb.exe"),
        str(Path(os.sys.executable).with_name("gdb.exe")),
        str(Path(os.environ.get("SystemDrive", "C:") + "/msys64/ucrt64/bin/gdb.exe")),
    )
    return next((Path(path) for path in candidates if path and Path(path).is_file()), None)


def selected_paths():
    if SETTINGS.is_file():
        lines = SETTINGS.read_text(encoding="utf-8").splitlines()
        if len(lines) == 2:
            return tuple(Path(line) if line else None for line in lines)
    return find_game(), find_gdb()


def save_paths(game, gdb):
    DATA.mkdir(parents=True, exist_ok=True)
    SETTINGS.write_text(f"{game or ''}\n{gdb or ''}\n", encoding="utf-8")
