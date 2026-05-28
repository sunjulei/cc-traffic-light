# Claude Traffic Light

![demo](screenshot.png)

为每个 Claude Code 终端窗口生成一盏漫画风红绿灯，一眼看出哪个在忙、哪个在等你。

## 功能

- **红灯** — Claude Code 正在输出（CPU/IO 活跃）
- **绿灯** — Claude Code 空闲，等你输入
- **双击灯** — 自动聚焦到对应终端窗口
- **拖拽** — 随意移动位置
- **系统托盘** — 右键退出，无黑窗口

## 使用

1. 下载 `ClaudeTrafficLight.exe`，双击运行
2. 打开 Claude Code 终端，红绿灯自动出现
3. 托盘图标右键 → Quit 退出

## 构建

```bash
pip install psutil pywin32 pyinstaller
pyinstaller --onefile --windowed --name ClaudeTrafficLight --icon icon.ico --add-data "icon.ico;." claude_traffic_light.py
```

## 检测方式

进程名 `claude.exe` / `Claude Code`，或命令行包含 `claude-code`。

## 许可

MIT
