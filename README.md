# Claude Traffic Light

> 当 Claude Code 在思考人生的时候，你需要一盏红绿灯来提醒自己：别急，它在努力。

## 这是什么？

一个 Windows 桌面小工具，为每个 Claude Code 终端窗口生成一个漫画风红绿灯：

- **红灯亮了** — Claude Code 正在疯狂输出（CPU 飙升中，请勿打扰天才）
- **绿灯亮了** — Claude Code 在等你输入（它已经想好了，就等你了）
- **双击灯** — 自动聚焦到对应的终端窗口（比 Alt+Tab 优雅多了）
- **拖拽移动** — 随便拖，不会跟终端窗口绑定（自由是灯的基本权利）
- **右下角托盘** — 右键可以退出（或者你也可以直接关机）

## 为什么？

因为你开了 5 个终端同时跑 Claude Code，每次都要逐个切过去看哪个还在转圈。有了红绿灯，一目了然。

**你不再需要盯着终端了。盯着灯就好。**

## 使用方式

1. 下载 `ClaudeTrafficLight.exe`
2. 双击运行（没有黑窗口，纯后台）
3. 打开 Claude Code 终端，红绿灯自动出现
4. 右下角托盘图标右键 → Quit 退出

## 构建

```bash
pip install psutil pywin32 pyinstaller
pyinstaller --onefile --windowed --name ClaudeTrafficLight --icon icon.ico --add-data "icon.ico;." claude_traffic_light.py
```

产物在 `dist/ClaudeTrafficLight.exe`。

## 检测逻辑

- 进程名是 `claude.exe`
- 进程名是 `Claude Code`
- 命令行包含 `claude-code`

## 红绿灯判定

滑动窗口算法：最近 20 次采样（每次 400ms）中，活跃次数 ≥ 4 次亮红灯，≤ 2 次亮绿灯。采样信号：CPU 时间增量 > 0.05s 或 IO 写入增量 > 4KB。

## 已知限制

- 仅支持 Windows
- 一个终端窗口一盏灯（同一窗口多个 Tab 共享）
- 不支持 macOS / Linux（PR welcome，但我不抱希望）

## 许可

MIT — 随便用，灯不收费。
