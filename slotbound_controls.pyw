import ctypes
import os
from pathlib import Path
import queue
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from reset_save import reset_profile
from slotbound_profile import (
    DEFAULT, SYMBOL_DEFAULT, JOKER_MAX, TOTAL, apportion, format_percent,
    limit_joker, percent_units, read_profile, redistribute, save_profile,
    valid_distribution, valid_symbols,
)

from slotbound_paths import selected_game, save_game, find_game
from launch_mod import launch

HIDDEN = subprocess.CREATE_NO_WINDOW
LABELS = ("普通", "高级", "稀有", "传说", "棱彩")
SYMBOL_LABELS = ("盾牌", "弓", "法杖", "马头", "尖帽", "王冠", "小丑")
COLORS = ("#c7c4bd", "#83d9a4", "#8eb3ff", "#ffbb68", "#dca1f0")
BG = "#13101a"
PANEL = "#201a2a"
FIELD = "#30263d"
INK = "#f2ecf6"
MUTED = "#b1a5bf"
GOLD = "#efbb72"
ERROR = "#ffa6ae"
FONT = "Microsoft YaHei UI"


def process_running(name):
    result = subprocess.run(
        ["tasklist", "/FI", f"IMAGENAME eq {name}", "/FO", "CSV", "/NH"],
        stdin=subprocess.DEVNULL, capture_output=True, creationflags=HIDDEN,
        check=True, timeout=10,
    )
    return f'"{name.lower()}"'.encode("ascii") in result.stdout.lower()


def game_running():
    return process_running("Slotbound.exe")


def close_game(game):
    command = (
        "$ErrorActionPreference='Stop'; "
        "$p=Get-Process Slotbound -ErrorAction SilentlyContinue; "
        "if ($p) { "
        "if (@($p).Count -ne 1 -or $p.Path -ne $env:SLOTBOUND_TOOL_EXE) { exit 2 }; "
        "if (!$p.CloseMainWindow() -or !$p.WaitForExit(10000)) { exit 3 } "
        "}"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
        env={**os.environ, "SLOTBOUND_TOOL_EXE": str(game)},
        stdin=subprocess.DEVNULL, creationflags=HIDDEN, capture_output=True, timeout=15,
    )
    if result.returncode or game_running():
        raise RuntimeError("游戏仍在运行。请在游戏里保存并退出后再试。")


def start_mod(values, symbols, game):
    save_profile(values, symbols)
    if not process_running("steam.exe"):
        raise RuntimeError("配置已保存。请打开 Steam，再启动改版。")
    launch(game, values, symbols)
    return "改版已启动。战役与无尽使用已保存的配置。"


def label(parent, text, size, color=INK, bg=BG, bold=False, **kwargs):
    return tk.Label(parent, text=text, bg=bg, fg=color,
                    font=(FONT, size, "bold" if bold else "normal"), **kwargs)


def button(parent, text, action, primary=False):
    return tk.Button(parent, text=text, command=action, bg=GOLD if primary else FIELD,
                     fg=BG if primary else INK, disabledforeground="#8f839b",
                     activebackground="#ffd393" if primary else "#42344f",
                     activeforeground=BG if primary else INK, font=(FONT, 10, "bold"),
                     relief="flat", padx=12, pady=7, cursor="hand2")


class OddsEditor:
    def __init__(self, parent, defaults, values, changed, is_symbol=False):
        self.is_symbol = is_symbol
        self.defaults = defaults
        self.labels = SYMBOL_LABELS if is_symbol else LABELS
        self.colors = (*COLORS[:4], "#aeb0fb", "#f0d292", "#dca1f0") if is_symbol else COLORS
        self.validate = valid_symbols if is_symbol else valid_distribution
        self.changed = changed
        self.syncing = False
        self.enabled = True
        self.values = list(values)
        self.inputs = []
        self.sliders = []
        self.entries = []
        self.automatic = tk.BooleanVar(value=True)
        self.total = tk.StringVar()
        card = tk.Frame(parent, bg=PANEL, padx=16, pady=12)
        self.frame = card
        card.columnconfigure(1, weight=1)
        self.auto_button = ttk.Checkbutton(card, text="自动配平", variable=self.automatic,
                                           command=self.toggle_balance, style="Odds.TCheckbutton")
        self.auto_button.grid(row=0, column=2, columnspan=2, sticky="e")
        note = "小丑沿用游戏的 5% 上限" if is_symbol else "拖动滑杆，或输入百分比后按 Enter"
        label(card, note, 9, color=MUTED, bg=PANEL).grid(row=0, column=0, columnspan=2, sticky="w")
        self.chart = tk.Canvas(card, bg=FIELD, height=9, highlightthickness=0)
        self.chart.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(10, 7))
        self.chart.bind("<Configure>", lambda _event: self.redraw())

        for index, (name, color) in enumerate(zip(self.labels, self.colors)):
            row = index + 2
            label(card, name, 10, color=color, bold=True, bg=PANEL).grid(row=row, column=0, sticky="w")
            slider = ttk.Scale(card, from_=0, to=self.max_units(index) / 100,
                               style="Odds.Horizontal.TScale",
                               command=lambda value, i=index: self.move(i, value))
            slider.grid(row=row, column=1, padx=(14, 12), pady=5, sticky="ew")
            value = tk.StringVar(value=format_percent(self.values[index]))
            entry = tk.Entry(card, textvariable=value, width=7, justify="right",
                             bg=FIELD, fg=INK, insertbackground=INK, relief="flat",
                             font=(FONT, 10), highlightthickness=1, highlightbackground=FIELD,
                             highlightcolor=GOLD)
            entry.grid(row=row, column=2, ipady=3)
            entry.bind("<Return>", lambda _event, i=index: self.commit(i))
            entry.bind("<FocusOut>", lambda _event, i=index: self.commit(i))
            value.trace_add("write", lambda *_args: self.refresh())
            label(card, "%", 9, color=MUTED, bg=PANEL).grid(row=row, column=3, padx=(6, 0))
            self.inputs.append(value)
            self.sliders.append(slider)
            self.entries.append(entry)

        footer = len(self.labels) + 2
        self.total_label = label(card, "", 11, bold=True, bg=PANEL, textvariable=self.total)
        self.total_label.grid(row=footer, column=0, columnspan=2, sticky="w", pady=(7, 0))
        self.recommended = button(card, "填入参考值", lambda: self.display(self.defaults))
        self.recommended.grid(row=footer, column=2, columnspan=2, sticky="e", pady=(7, 0))
        self.display(values)

    def max_units(self, index):
        return JOKER_MAX if self.is_symbol and index == len(self.labels) - 1 else TOTAL

    def parsed(self):
        values = [percent_units(item.get()) for item in self.inputs]
        if self.is_symbol and values[-1] > JOKER_MAX:
            raise ValueError("小丑上限为 5%。")
        return values

    def valid(self):
        try:
            return self.validate(self.parsed())
        except ValueError:
            return False

    def display(self, values):
        self.syncing = True
        self.values = list(values)
        for text, slider, amount in zip(self.inputs, self.sliders, values):
            text.set(format_percent(amount))
            slider.set(amount / 100)
        self.syncing = False
        self.refresh()

    def redraw(self):
        try:
            values = self.parsed()
        except ValueError:
            values = self.values
        width = self.chart.winfo_width()
        denominator = max(TOTAL, sum(values))
        self.chart.delete("slice")
        cumulative = 0
        for value, color in zip(values, self.colors):
            start = width * cumulative / denominator
            cumulative += value
            if value:
                self.chart.create_rectangle(start, 0, width * cumulative / denominator, 9,
                                            fill=color, width=0, tags="slice")

    def refresh(self):
        if self.syncing or not hasattr(self, "total_label"):
            return
        try:
            total = sum(self.parsed())
            text = f"合计  {format_percent(total)}%"
        except ValueError as error:
            total = None
            text = str(error)
        self.total.set(text)
        self.total_label.configure(fg=GOLD if total == TOTAL else ERROR)
        self.redraw()
        self.changed()

    def move(self, index, raw):
        if not self.syncing and self.enabled and len(self.inputs) == len(self.labels):
            self.change(index, round(float(raw) * 100))

    def commit(self, index):
        if self.syncing or not self.enabled:
            return
        try:
            amount = percent_units(self.inputs[index].get())
        except ValueError:
            return
        if amount <= self.max_units(index):
            self.change(index, amount)

    def change(self, index, amount):
        if amount == self.values[index]:
            return
        if self.automatic.get():
            cap = JOKER_MAX if self.is_symbol else None
            self.display(redistribute(self.values, index, amount, cap))
        else:
            self.values[index] = amount
            self.syncing = True
            self.inputs[index].set(format_percent(amount))
            self.sliders[index].set(amount / 100)
            self.syncing = False
            self.refresh()

    def toggle_balance(self):
        if not self.automatic.get():
            return
        try:
            values = self.parsed()
        except ValueError:
            values = self.values
        values = apportion(values, TOTAL)
        self.display(limit_joker(values) if self.is_symbol else values)

    def set_enabled(self, enabled):
        self.enabled = enabled
        state = "normal" if enabled else "disabled"
        for widget in (self.recommended, self.auto_button, *self.entries, *self.sliders):
            widget.configure(state=state)


class Controls:
    def __init__(self, root):
        self.root = root
        self.busy = False
        self.results = queue.Queue()
        self.game = selected_game()
        notice = "原版启动继续使用当前存档。"
        try:
            rarity, symbols = read_profile()
        except (OSError, ValueError) as error:
            rarity, symbols = list(DEFAULT), None
            notice = f"{error} 已填入参考值。"
        self.symbol_on = tk.BooleanVar(value=symbols is not None)
        self.status = tk.StringVar(value=notice)

        root.title("Slotbound 概率控制台")
        root.configure(bg=BG)
        root.minsize(635, 655)
        root.columnconfigure(0, weight=1)
        styles = ttk.Style()
        styles.theme_use("clam")
        styles.configure("Odds.Horizontal.TScale", background=PANEL, troughcolor=FIELD,
                         bordercolor=FIELD, lightcolor=GOLD, darkcolor=GOLD,
                         sliderlength=16, sliderthickness=13)
        styles.configure("Odds.TCheckbutton", background=PANEL, foreground=INK,
                         font=(FONT, 10), indicatorcolor=FIELD)
        styles.map("Odds.TCheckbutton", background=[("active", PANEL)],
                   indicatorcolor=[("selected", GOLD)])
        styles.configure("Odds.TNotebook", background=BG, borderwidth=0)
        styles.configure("Odds.TNotebook.Tab", background=FIELD, foreground=MUTED,
                         padding=(15, 7), font=(FONT, 10, "bold"))
        styles.map("Odds.TNotebook.Tab", background=[("selected", PANEL)],
                   foreground=[("selected", GOLD)])

        main = tk.Frame(root, bg=BG, padx=24, pady=20)
        main.grid(sticky="nsew")
        main.columnconfigure(0, weight=1)
        label(main, "Slotbound", 25, bold=True).grid(row=0, column=0, sticky="w")
        self.settings_button = button(main, "路径设置", self.settings)
        self.settings_button.grid(row=0, column=1, sticky="e")
        label(main, "概率控制台  /  战役与无尽", 10, color=MUTED).grid(
            row=1, column=0, sticky="w", pady=(0, 12))

        notebook = ttk.Notebook(main, style="Odds.TNotebook")
        notebook.grid(row=2, column=0, columnspan=2, sticky="ew")
        self.rarity = OddsEditor(notebook, DEFAULT, rarity, self.update_launch)
        notebook.add(self.rarity.frame, text="稀有度")
        symbol_page = tk.Frame(notebook, bg=PANEL)
        symbol_page.columnconfigure(0, weight=1)
        notebook.add(symbol_page, text="老虎机符号")
        self.symbol_check = ttk.Checkbutton(
            symbol_page, text="使用自定义符号概率", variable=self.symbol_on,
            command=self.update_launch, style="Odds.TCheckbutton")
        self.symbol_check.grid(row=0, column=0, sticky="w", padx=16, pady=(9, 0))
        self.symbols = OddsEditor(symbol_page, SYMBOL_DEFAULT, symbols or SYMBOL_DEFAULT,
                                  self.update_launch, is_symbol=True)
        self.symbols.frame.grid(row=1, column=0, sticky="ew")

        self.launch = button(main, "保存配置并启动改版", self.launch_mod, primary=True)
        self.launch.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(14, 8))
        tools = tk.Frame(main, bg=BG)
        tools.grid(row=4, column=0, columnspan=2, sticky="ew")
        tools.columnconfigure((0, 1), weight=1, uniform="tools")
        self.reset = button(tools, "重置天赋并退款", self.reset_talents)
        self.reset.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.vanilla = button(tools, "恢复原版并启动", self.launch_vanilla)
        self.vanilla.grid(row=0, column=1, sticky="ew", padx=(4, 0))
        self.status_label = label(main, "", 9, color=MUTED, textvariable=self.status,
                                  justify="left", wraplength=535)
        self.status_label.grid(row=5, column=0, columnspan=2, sticky="w", pady=(10, 0))
        self.update_launch()
        root.after(100, self.check_result)

    def update_launch(self):
        if not hasattr(self, "launch"):
            return
        self.symbols.set_enabled(self.symbol_on.get() and not self.busy)
        valid = self.rarity.valid() and (not self.symbol_on.get() or self.symbols.valid())
        self.launch.configure(state="normal" if valid and not self.busy else "disabled")

    def show_status(self, text, error=False):
        self.status.set(text)
        self.status_label.configure(fg=ERROR if error else MUTED)

    def settings(self):
        dialog = tk.Toplevel(self.root, bg=BG)
        dialog.title("路径设置")
        dialog.transient(self.root)
        dialog.grab_set()
        body = tk.Frame(dialog, bg=BG, padx=18, pady=16)
        body.pack(fill="both", expand=True)
        variable = tk.StringVar(value=str(self.game or ""))

        def choose():
            chosen = filedialog.askopenfilename(parent=dialog, title="选择 Slotbound.exe",
                                                filetypes=[("Slotbound.exe", "Slotbound.exe")])
            if chosen:
                variable.set(chosen)

        label(body, "Slotbound.exe", 10).grid(row=0, column=0, sticky="w")
        ttk.Entry(body, textvariable=variable, width=58).grid(row=1, column=0, pady=(3, 9))
        button(body, "浏览", choose).grid(row=1, column=1)

        def detect():
            value = find_game()
            if value is not None:
                variable.set(str(value))
            else:
                messagebox.showinfo("路径设置", "没有找到游戏，请手动选择 Slotbound.exe。", parent=dialog)

        def save():
            game = Path(variable.get().strip())
            if not game.is_file() or game.name.lower() != "slotbound.exe":
                messagebox.showerror("路径设置", "请选择有效的 Slotbound.exe。", parent=dialog)
                return
            save_game(game)
            self.game = game
            self.show_status("已保存路径设置。")
            dialog.destroy()

        button(body, "自动查找", detect).grid(row=2, column=0, sticky="w")
        button(body, "保存", save, primary=True).grid(row=2, column=1)


    def begin(self, action, label):
        if self.busy:
            return
        try:
            running = game_running()
        except (OSError, subprocess.SubprocessError) as error:
            self.show_status(f"无法检查游戏状态：{error}", error=True)
            return
        if running and not self.game:
            self.show_status("请先设置游戏路径，或手动退出游戏。", error=True)
            return
        if running and not messagebox.askokcancel(
            label, "Slotbound 正在运行。请确认游戏进度已保存，再退出游戏并继续。", parent=self.root
        ):
            return
        self.busy = True
        self.set_enabled(False)
        self.show_status(f"正在{label}…")

        def run():
            try:
                if running:
                    close_game(self.game)
                if game_running():
                    raise RuntimeError("请先退出当前运行的 Slotbound。")
                self.results.put((action(), False))
            except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
                self.results.put((str(error), True))

        threading.Thread(target=run, daemon=True).start()

    def set_enabled(self, enabled):
        state = "normal" if enabled else "disabled"
        for widget in (self.reset, self.vanilla, self.settings_button, self.symbol_check):
            widget.configure(state=state)
        for editor in (self.rarity, self.symbols):
            editor.set_enabled(enabled)
        self.update_launch()

    def check_result(self):
        try:
            message, error = self.results.get_nowait()
        except queue.Empty:
            pass
        else:
            self.busy = False
            self.set_enabled(True)
            self.show_status(message, error)
        self.root.after(100, self.check_result)

    def launch_mod(self):
        if not self.game or not self.game.is_file():
            self.settings()
            return
        if self.rarity.valid() and (not self.symbol_on.get() or self.symbols.valid()):
            values = self.rarity.parsed()
            symbols = self.symbols.parsed() if self.symbol_on.get() else None
            self.begin(lambda: start_mod(values, symbols, self.game), "启动改版")

    def launch_vanilla(self):
        def original():
            os.startfile("steam://rungameid/4459590")
            return "已通过 Steam 打开原版。自定义配置保留在控制台。"
        self.begin(original, "启动原版")

    def reset_talents(self):
        def refund():
            count, total, balance, _backup = reset_profile()
            if count:
                return f"已备份存档，重置 {count} 项天赋，退回 {total} 枚。余额 {balance} 枚。"
            return f"当前没有已购买的天赋。余额 {balance} 枚。"
        self.begin(refund, "重置天赋")


if __name__ == "__main__":
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
    kernel.CreateMutexW.restype = ctypes.c_void_p
    mutex = kernel.CreateMutexW(None, False, r"Local\SlotboundProbabilityControls")
    already_open = ctypes.get_last_error() == 183
    root = tk.Tk()
    if already_open:
        root.withdraw()
        messagebox.showinfo("Slotbound", "概率控制台已经打开。", parent=root)
        root.destroy()
    else:
        Controls(root)
        root.mainloop()
