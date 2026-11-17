# Slotbound 概率控制台

适用于 Windows x64 上的 Steam 版 Slotbound。支持调节战役和本地无尽的单位稀有度、老虎机符号权重，以及备份存档和重置天赋。

## 下载和启动

在 [GitHub Releases](https://github.com/Yang-yangsong/slotbound/releases) 下载 `Slotbound-Controls.exe`，打开 Steam 后双击运行。这个文件包含控制台和启动组件，无需另装 Python、GDB 或 MSYS2。它使用你已经安装的 Steam 版 Slotbound。

控制台会自动查找 Steam 库。如果没有找到游戏，在「路径设置」中直接选择 `Slotbound.exe`。

## 使用

- 「稀有度」和「老虎机符号」分别支持自动配平和手动输入。每一组独立合计 100%。
- 勾选「使用自定义符号概率」才改变符号权重。小丑沿用游戏的 5% 上限。核心、保底和强制符号效果仍可能改变实际结果。
- 「重置天赋并退款」先备份存档，再按内置价格表退款。改版会把本工具洗点备份里已买过的区域节点计入门槛。
- 「恢复原版并启动」通过 Steam 启动当前存档。改版无尽局关闭排行榜提交，成绩记录在本地。
- 配置、备份和启动日志在 `%LOCALAPPDATA%\SlotboundControls`。

已在 Steam build `26705604` 上测试。Steam 更新后，运行库或天赋价格表可能需要适配。游戏安装目录保留原版文件。

## 从源码构建

这一节只适用于开发者。准备 Windows x64 的 CPython 3.12 和 Tcl/Tk，以及能从 PATH 调用的 64 位 MinGW GCC。安装 PyInstaller 后运行仓库里的构建脚本。

```powershell
python -m pip install pyinstaller==6.22.3
.\Build.ps1
```

生成的单文件程序位于 `dist/Slotbound-Controls.exe`。此项目是非官方工具，发布文件不包含游戏、Steam 运行库或玩家存档。
