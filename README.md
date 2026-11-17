# Slotbound 概率控制台

适用于 Windows 上的 Steam 版 Slotbound。可以调整战役与无尽的单位稀有度和老虎机符号权重。工具在启动时加载修改，游戏安装文件保留原版。

## 安装

1. 安装并打开 Steam，确保原版 Slotbound 能启动。
2. 安装 [Python 3.10 或更高版本](https://www.python.org/downloads/windows/)，安装时保留 Tcl/Tk 和 Python Launcher。
3. 安装 [MSYS2](https://www.msys2.org/)，打开 **MSYS2 UCRT64**，按照 [MSYS2 更新说明](https://www.msys2.org/docs/updating/)更新后运行：

   ```sh
   pacman -S --needed mingw-w64-ucrt-x86_64-gdb
   ```

4. 下载并解压此仓库的 ZIP，双击 `Start.cmd`。控制台会从 Steam 库查找游戏，也可以在「路径设置」里直接选 `Slotbound.exe` 和带 Python 支持的 `gdb.exe`。

## 使用

- 「稀有度」与「老虎机符号」各有独立的自动配平。关闭配平后，输入的概率必须合计 100%。
- 勾选「使用自定义符号概率」才修改符号权重。小丑沿用原版 5% 上限。核心、保底和强制符号效果仍可能改变实际结果。
- 「重置天赋并退款」按内置价格表退款，先备份存档。关卡进度继续使用当前存档。改版会把本工具洗点备份里已买过的区域节点计入门槛。
- 「恢复原版并启动」通过 Steam 启动当前存档。改版无尽局在运行期间关闭排行榜提交，成绩记录在本地。
- 配置、备份和启动日志在 `%LOCALAPPDATA%\SlotboundControls`。

在 Windows x64 的 Steam build `26705604` 上测试。Steam 更新后，运行库或天赋价格表可能需要适配。如果改版无法加载，可先用原版启动，查看 `launch.log` 或提交 issue。

本项目是非官方工具。仓库包含控制台代码和天赋价格数据，使用你本地已安装的游戏和 GDB。
