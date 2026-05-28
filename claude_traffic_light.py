"""
Desktop traffic light for monitoring Claude Code activity.
- Red light: Claude Code is actively responding
- Green light: Claude Code is idle/waiting for input
- Double-click: brings the corresponding terminal window to focus
- Drag to move anywhere on screen
- System tray icon with right-click menu to quit
"""

import os
import sys
import math
import ctypes
import ctypes.wintypes as wintypes
import tkinter as tk
from collections import deque
import psutil
import win32gui
import win32con
import win32process
import win32api


def _resource_path(name):
    """Get path to bundled resource (works for both dev and pyinstaller)."""
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)

# --- Configuration ---
POLL_MS = 400
CPU_DELTA_THRESHOLD = 0.05
WIN_SIZE = 20
RED_IF_ACTIVE = 4
GREEN_IF_IDLE = 2
MARGIN = 10

# Visual — manga / comic style
LR = 13
GAP = 5
HOUSING_PAD = 8
BRACKET_W = 16
BRACKET_H = 5
OUTLINE_W = 3
HALFTONE_R = 2

RED_ON = "#ff2222"
RED_OFF = "#4a1515"
GREEN_ON = "#22dd44"
GREEN_OFF = "#154020"
HOUSING_BG = "#f5f0e8"
HOUSING_OUTLINE = "#1a1a1a"
BRACKET_COLOR = "#1a1a1a"
LABEL_COLOR = "#1a1a1a"
BG_TRANSPARENT = "#e8e0d0"

# --- Win32 constants for Shell_NotifyIcon ---
NIM_ADD = 0x00
NIM_DELETE = 0x02
NIF_MESSAGE = 0x01
NIF_ICON = 0x02
NIF_TIP = 0x04
WM_TRAYICON = win32con.WM_USER + 1
IDI_APPLICATION = 32512

shell32 = ctypes.windll.shell32
user32 = ctypes.windll.user32


class NOTIFYICONDATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_uint),
        ("hWnd", wintypes.HWND),
        ("uID", ctypes.c_uint),
        ("uFlags", ctypes.c_uint),
        ("uCallbackMessage", ctypes.c_uint),
        ("hIcon", wintypes.HICON),
        ("szTip", ctypes.c_wchar * 128),
        ("dwState", ctypes.c_uint),
        ("dwStateMask", ctypes.c_uint),
        ("szInfo", ctypes.c_wchar * 256),
        ("uTimeoutOrVersion", ctypes.c_uint),
        ("szInfoTitle", ctypes.c_wchar * 64),
        ("dwInfoFlags", ctypes.c_uint),
        ("guidItem", ctypes.c_byte * 16),
        ("hBalloonIcon", wintypes.HICON),
    ]


# --- System tray icon ---

class TrayIcon:
    def __init__(self, tooltip, quit_cb):
        self._quit_cb = quit_cb
        self._nid = None
        self._hwnd = None
        self._create_window(tooltip)

    def _create_window(self, tooltip):
        wc = win32gui.WNDCLASS()
        wc.hInstance = win32api.GetModuleHandle(None)
        wc.lpszClassName = "ClaudeTrafficLightTray"
        wc.lpfnWndProc = self._wnd_proc
        class_atom = win32gui.RegisterClass(wc)

        self._hwnd = win32gui.CreateWindow(
            class_atom, "ClaudeTrafficLightTray",
            0, 0, 0, 0, 0, 0, 0, wc.hInstance, None,
        )

        icon_path = _resource_path("icon.ico")
        if os.path.exists(icon_path):
            hicon = user32.LoadImageW(
                None, icon_path, 1, 0, 0, 0x00000010  # IMAGE_ICON, LR_LOADFROMFILE
            )
        else:
            hicon = user32.LoadIconW(None, IDI_APPLICATION)

        self._nid = NOTIFYICONDATA()
        self._nid.cbSize = ctypes.sizeof(NOTIFYICONDATA)
        self._nid.hWnd = self._hwnd
        self._nid.uID = 1
        self._nid.uFlags = NIF_ICON | NIF_MESSAGE | NIF_TIP
        self._nid.uCallbackMessage = WM_TRAYICON
        self._nid.hIcon = hicon
        self._nid.szTip = tooltip

        shell32.Shell_NotifyIconW(NIM_ADD, self._nid)

    def _wnd_proc(self, hwnd, msg, wparam, lparam):
        if msg == WM_TRAYICON:
            if lparam == win32con.WM_RBUTTONUP:
                self._show_menu()
            elif lparam == win32con.WM_LBUTTONDBLCLK:
                self._quit_cb()
        elif msg == win32con.WM_COMMAND:
            if win32gui.LOWORD(wparam) == 1:
                self._quit_cb()
        elif msg == win32con.WM_DESTROY:
            self._remove()
            win32gui.PostQuitMessage(0)
        return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)

    def _show_menu(self):
        menu = win32gui.CreatePopupMenu()
        win32gui.AppendMenu(menu, win32con.MF_STRING, 1, "Quit")
        win32gui.SetMenuDefaultItem(menu, 1, False)

        pt = win32gui.GetCursorPos()
        win32gui.SetForegroundWindow(self._hwnd)
        win32gui.TrackPopupMenu(
            menu, win32con.TPM_RIGHTBUTTON,
            pt[0], pt[1], 0, self._hwnd, None,
        )
        win32gui.PostMessage(self._hwnd, win32con.WM_NULL, 0, 0)
        win32gui.DestroyMenu(menu)

    def pump(self):
        """Process pending Win32 messages. Call from tkinter event loop."""
        msg = wintypes.MSG()
        while user32.PeekMessageW(ctypes.byref(msg), 0, 0, 0, 1):
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def _remove(self):
        if self._nid:
            shell32.Shell_NotifyIconW(NIM_DELETE, self._nid)
            self._nid = None

    def destroy(self):
        self._remove()
        if self._hwnd:
            win32gui.DestroyWindow(self._hwnd)
            self._hwnd = None


# --- Process & window discovery ---

def _enum_windows_by_pid(pid):
    result = []
    def _cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        _, wpid = win32process.GetWindowThreadProcessId(hwnd)
        if wpid != pid:
            return
        try:
            title = win32gui.GetWindowText(hwnd)
        except Exception:
            title = ""
        try:
            cls = win32gui.GetClassName(hwnd)
        except Exception:
            cls = ""
        result.append((hwnd, title, cls))
    try:
        win32gui.EnumWindows(_cb, None)
    except Exception:
        pass
    return result


def _real_window(pid):
    candidates = []
    for hwnd, _, cls in _enum_windows_by_pid(pid):
        if cls == "PseudoConsoleWindow":
            continue
        try:
            l, t, r, b = win32gui.GetWindowRect(hwnd)
            if r - l > 10 and b - t > 10:
                candidates.append(hwnd)
        except Exception:
            pass
    if not candidates:
        return None
    candidates.sort()
    return candidates[0]


_wt_child_cache = {}
_wt_child_cache_time = 0

def _build_wt_child_map():
    """Map every descendant PID of each Windows Terminal to its WT window.
    Cached for 6 seconds.
    """
    global _wt_child_cache, _wt_child_cache_time
    import time
    now = time.monotonic()
    if now - _wt_child_cache_time < 6:
        return _wt_child_cache

    mapping = {}
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            if proc.name().lower() not in ("windowsterminal.exe", "windowsterminal"):
                continue
            wt_hwnd = _real_window(proc.pid)
            if not wt_hwnd:
                continue
            stack = [proc]
            while stack:
                cur = stack.pop()
                mapping[cur.pid] = wt_hwnd
                try:
                    stack.extend(cur.children())
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    _wt_child_cache = mapping
    _wt_child_cache_time = now
    return mapping


def _find_wt_hwnd():
    """Return the first Windows Terminal window (fallback)."""
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            if proc.name().lower() in ("windowsterminal.exe", "windowsterminal"):
                h = _real_window(proc.pid)
                if h:
                    return h
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return None


def _get_terminal_hwnd(pid):
    try:
        proc = psutil.Process(pid)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return None

    ancestors = []
    p = proc
    for _ in range(20):
        try:
            parent = p.parent()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            break
        if parent is None:
            break
        try:
            pname = parent.name().lower()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            break
        ancestors.append((parent.pid, pname))
        p = parent

    for apid, aname in ancestors:
        wins = _enum_windows_by_pid(apid)
        pseudo_hwnd = None
        real_candidates = []
        for hwnd, _, cls in wins:
            if cls == "PseudoConsoleWindow":
                pseudo_hwnd = hwnd
                continue
            try:
                l, t, r, b = win32gui.GetWindowRect(hwnd)
                if r - l > 10 and b - t > 10:
                    real_candidates.append(hwnd)
            except Exception:
                continue
        if real_candidates:
            real_candidates.sort()
            return real_candidates[0]
        if pseudo_hwnd is not None:
            wt_map = _build_wt_child_map()
            if apid in wt_map:
                return wt_map[apid]
            if pid in wt_map:
                return wt_map[pid]
            return pseudo_hwnd

    wt_map = _build_wt_child_map()
    if pid in wt_map:
        return wt_map[pid]

    return _find_wt_hwnd()


def _is_claude_proc(info):
    try:
        name = (info["name"] or "").lower()
        cmdline = info.get("cmdline") or []
        cmdline_str = " ".join(cmdline).lower()
        if name == "claude.exe":
            return True
        if name == "claude code":
            return True
        if "claude-code" in cmdline_str:
            return True
        return False
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False


def discover_groups():
    """Return {terminal_hwnd: [claude_pids]}."""
    groups = {}
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        if not _is_claude_proc(proc.info):
            continue
        try:
            pid = proc.info["pid"]
            hwnd = _get_terminal_hwnd(pid)
            if hwnd is None:
                continue
            groups.setdefault(hwnd, []).append(pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return groups


# --- Window focus ---

def window_ok(hwnd):
    return hwnd and win32gui.IsWindow(hwnd)


def focus_window(hwnd):
    if not window_ok(hwnd):
        return
    try:
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        fg = win32gui.GetForegroundWindow()
        fg_tid = win32process.GetWindowThreadProcessId(fg)[0]
        cur_tid = win32api.GetCurrentThreadId()
        if fg_tid != cur_tid:
            win32process.AttachThreadInput(cur_tid, fg_tid, True)
        win32gui.SetForegroundWindow(hwnd)
        if fg_tid != cur_tid:
            win32process.AttachThreadInput(cur_tid, fg_tid, False)
    except Exception:
        try:
            win32gui.BringWindowToTop(hwnd)
        except Exception:
            pass


# --- Traffic light widget ---

ANIM_MS = 80


def _round_rect(canvas, x0, y0, x1, y1, r, **kw):
    pts = [
        x0+r, y0, x1-r, y0, x1, y0, x1, y0+r,
        x1, y1-r, x1, y1, x1-r, y1, x0+r, y1,
        x0, y1, x0, y1-r, x0, y0+r, x0, y0,
    ]
    return canvas.create_polygon(pts, smooth=True, **kw)


def _make_halftone(canvas, cx, cy, r, spacing, color):
    dots = []
    for dx in range(-r, r + 1, spacing):
        for dy in range(-r, r + 1, spacing):
            if dx*dx + dy*dy <= r*r:
                d = HALFTONE_R
                dots.append(canvas.create_oval(
                    cx+dx-d, cy+dy-d, cx+dx+d, cy+dy+d,
                    fill=color, outline=""))
    return dots


def _set_color(canvas, items, color):
    for i in items:
        canvas.itemconfig(i, fill=color)


class TrafficLight:
    def __init__(self, master, key, hwnd, pids, name, on_done):
        self.master = master
        self._key = key
        self.hwnd = hwnd
        self.pids = list(pids)
        self.on_done = on_done
        self._window = deque(maxlen=WIN_SIZE)
        self._dead_count = 0
        self._poll_timer = None
        self._anim_timer = None
        self._prev_cpu = {}
        self._prev_io = {}
        self._drag_data = None
        self._is_red = False
        self._phase = 0
        self._halftone_r = []
        self._halftone_g = []
        self._stars = []
        self._zzz = []
        self._bang = None

        self._name = name[:16] if len(name) > 16 else name

        self.win = tk.Toplevel(master)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.configure(bg=BG_TRANSPARENT)

        diam = LR * 2
        self._w = diam + HOUSING_PAD * 2 + 8
        housing_h = diam * 2 + GAP + HOUSING_PAD * 2 + 4
        label_h = 20
        self._h = BRACKET_H + housing_h + label_h
        cx = self._w // 2

        self.canvas = tk.Canvas(
            self.win, width=self._w, height=self._h,
            bg=BG_TRANSPARENT, highlightthickness=0
        )
        self.canvas.pack()

        # Top bracket
        bx0 = cx - BRACKET_W // 2
        self.canvas.create_rectangle(
            bx0, 0, bx0 + BRACKET_W, BRACKET_H,
            fill=BRACKET_COLOR, outline=HOUSING_OUTLINE, width=1)

        # Housing body
        hx0, hy0 = 1, BRACKET_H
        hx1, hy1 = self._w - 1, BRACKET_H + housing_h
        self._hy1 = hy1
        _round_rect(self.canvas, hx0, hy0, hx1, hy1, 7,
                    fill=HOUSING_BG, outline=HOUSING_OUTLINE, width=OUTLINE_W)

        # Lights
        self._lcx = cx
        r_y0 = hy0 + HOUSING_PAD + 4
        g_y0 = r_y0 + diam + GAP
        self._r_cy = r_y0 + LR
        self._g_cy = g_y0 + LR
        self._r_y0 = r_y0
        self._g_y0 = g_y0
        self._diam = diam

        self._red = self.canvas.create_oval(
            cx - LR, r_y0, cx + LR, r_y0 + diam,
            fill=RED_OFF, outline=HOUSING_OUTLINE, width=OUTLINE_W)
        self._green = self.canvas.create_oval(
            cx - LR, g_y0, cx + LR, g_y0 + diam,
            fill=GREEN_OFF, outline=HOUSING_OUTLINE, width=OUTLINE_W)

        self._halftone_r = _make_halftone(
            self.canvas, cx, self._r_cy, LR - 2, 5, HOUSING_OUTLINE)
        self._halftone_g = _make_halftone(
            self.canvas, cx, self._g_cy, LR - 2, 5, HOUSING_OUTLINE)

        # Comic FX
        for angle_deg in range(0, 360, 45):
            a = math.radians(angle_deg)
            r0 = LR + 3
            r1 = LR + 10
            x0 = cx + r0 * math.cos(a)
            y0 = self._r_cy + r0 * math.sin(a)
            x1 = cx + r1 * math.cos(a)
            y1 = self._r_cy + r1 * math.sin(a)
            self._stars.append(self.canvas.create_line(
                x0, y0, x1, y1,
                fill="", width=2, capstyle="round"))
        self._bang = self.canvas.create_text(
            cx + LR + 8, self._r_cy - 4, text="!",
            fill="", font=("Arial", 10, "bold"))
        self._zzz.append(self.canvas.create_text(
            cx + LR + 6, self._g_cy - 6, text="z",
            fill=LABEL_COLOR, font=("Arial", 7, "italic")))
        self._zzz.append(self.canvas.create_text(
            cx + LR + 10, self._g_cy - 12, text="z",
            fill=LABEL_COLOR, font=("Arial", 6, "italic")))

        # Label
        self.canvas.create_text(
            cx, hy1 + 3, text=self._name, fill=LABEL_COLOR,
            font=("Consolas", 8, "bold"), anchor="n",
        )

        self.canvas.bind("<Double-Button-1>", self._dblclick)
        self.win.bind("<Double-Button-1>", self._dblclick)
        self.canvas.bind("<ButtonPress-1>", self._drag_start)
        self.canvas.bind("<B1-Motion>", self._drag_move)
        self.canvas.bind("<ButtonRelease-1>", self._drag_end)
        self.win.bind("<ButtonPress-1>", self._drag_start)
        self.win.bind("<B1-Motion>", self._drag_move)
        self.win.bind("<ButtonRelease-1>", self._drag_end)
        self.canvas.config(cursor="hand2")
        self.win.config(cursor="hand2")

        for pid in self.pids:
            self._init_metrics(pid)

        self._poll_tick()
        self._anim_tick()

    def _init_metrics(self, pid):
        try:
            ct = psutil.Process(pid).cpu_times()
            self._prev_cpu[pid] = (ct.user, ct.system)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        try:
            io = psutil.Process(pid).io_counters()
            self._prev_io[pid] = (io.read_bytes, io.write_bytes)
        except (psutil.NoSuchProcess, psutil.AccessDenied, AttributeError):
            pass

    def _is_active_tick(self, pid):
        cpu_active = False
        io_active = False
        try:
            ct = psutil.Process(pid).cpu_times()
            prev = self._prev_cpu.get(pid)
            self._prev_cpu[pid] = (ct.user, ct.system)
            if prev:
                delta = (ct.user - prev[0]) + (ct.system - prev[1])
                if delta > CPU_DELTA_THRESHOLD:
                    cpu_active = True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        try:
            io = psutil.Process(pid).io_counters()
            prev_io = self._prev_io.get(pid)
            self._prev_io[pid] = (io.read_bytes, io.write_bytes)
            if prev_io:
                w_delta = io.write_bytes - prev_io[1]
                if w_delta > 4096:
                    io_active = True
        except (psutil.NoSuchProcess, psutil.AccessDenied, AttributeError):
            pass
        return cpu_active or io_active

    def _dblclick(self, _=None):
        focus_window(self.hwnd)

    def _drag_start(self, event):
        self._drag_data = {"x": event.x, "y": event.y}

    def _drag_move(self, event):
        if self._drag_data is None:
            return
        dx = event.x - self._drag_data["x"]
        dy = event.y - self._drag_data["y"]
        x = self.win.winfo_x() + dx
        y = self.win.winfo_y() + dy
        self.win.geometry(f"+{x}+{y}")

    def _drag_end(self, _):
        self._drag_data = None

    def _poll_tick(self):
        if not self.win.winfo_exists():
            return

        alive = []
        any_active = False
        for pid in self.pids:
            try:
                proc = psutil.Process(pid)
                st = proc.status()
                if st in (psutil.STATUS_ZOMBIE, psutil.STATUS_DEAD):
                    continue
                alive.append(pid)
                if self._is_active_tick(pid):
                    any_active = True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        if not alive:
            self._dead_count += 1
            if self._dead_count >= 8:
                self.destroy()
                return
        else:
            self._dead_count = 0
            self.pids = alive
            for pid in alive:
                if pid not in self._prev_cpu:
                    self._init_metrics(pid)

        if not window_ok(self.hwnd):
            self._dead_count += 1
            if self._dead_count >= 8:
                self.destroy()
                return

        self._window.append(any_active)
        active_count = sum(self._window)

        if active_count >= RED_IF_ACTIVE:
            self._is_red = True
        elif active_count <= GREEN_IF_IDLE:
            self._is_red = False

        self._poll_timer = self.win.after(POLL_MS, self._poll_tick)

    def _anim_tick(self):
        if not self.win.winfo_exists():
            return

        self._phase += 1

        if self._is_red:
            self.canvas.itemconfig(self._red, fill=RED_ON)
            self.canvas.itemconfig(self._green, fill=GREEN_OFF)
            _set_color(self.canvas, self._halftone_r, "")
            _set_color(self.canvas, self._halftone_g, HOUSING_OUTLINE)
            for i, star in enumerate(self._stars):
                a = math.radians(i * 45)
                jitter = (self._phase % 3) - 1
                r1 = LR + 9 + (self._phase % 3)
                cx = self._lcx
                x1 = cx + r1 * math.cos(a) + jitter
                y1 = self._r_cy + r1 * math.sin(a)
                self.canvas.coords(star,
                    cx + (LR+3)*math.cos(a)+jitter,
                    self._r_cy + (LR+3)*math.sin(a),
                    x1, y1)
                self.canvas.itemconfig(star, fill=HOUSING_OUTLINE)
            if self._phase % 6 < 3:
                self.canvas.itemconfig(self._bang, fill=RED_ON)
            else:
                self.canvas.itemconfig(self._bang, fill="")
            _set_color(self.canvas, self._zzz, "")
        else:
            self.canvas.itemconfig(self._red, fill=RED_OFF)
            self.canvas.itemconfig(self._green, fill=GREEN_ON)
            _set_color(self.canvas, self._halftone_r, HOUSING_OUTLINE)
            _set_color(self.canvas, self._halftone_g, "")
            for star in self._stars:
                self.canvas.itemconfig(star, fill="")
            self.canvas.itemconfig(self._bang, fill="")
            if self._phase % 8 < 5:
                _set_color(self.canvas, self._zzz, LABEL_COLOR)
            else:
                _set_color(self.canvas, self._zzz, "")

        self._anim_timer = self.win.after(ANIM_MS, self._anim_tick)

    def destroy(self):
        for t in (self._poll_timer, self._anim_timer):
            if t:
                try:
                    self.win.after_cancel(t)
                except Exception:
                    pass
        try:
            self.win.destroy()
        except Exception:
            pass
        self.on_done(self._key, self.pids)


# --- Main ---

def main():
    root = tk.Tk()
    root.withdraw()

    lights = {}
    slot_map = {}
    used_slots = []
    name_seq = {}
    name_map = {}
    pos_map = {}
    pid_pos = {}

    LIGHT_H = 100

    def quit_app():
        tray.destroy()
        for tl in list(lights.values()):
            tl.destroy()
        root.destroy()

    tray = TrayIcon("Claude Traffic Light", quit_cb=quit_app)

    def _alloc_slot(key):
        if key in slot_map:
            return slot_map[key]
        sw = root.winfo_screenwidth()
        x = sw - 70 - MARGIN
        y = MARGIN
        while any(s <= y < e for s, e in used_slots):
            y += LIGHT_H + MARGIN
        used_slots.append((y, y + LIGHT_H))
        slot_map[key] = (x, y, LIGHT_H)
        return slot_map[key]

    def _free_slot(key):
        if key in slot_map:
            x, y, h = slot_map.pop(key)
            used_slots[:] = [(s, e) for s, e in used_slots if s != y]

    def on_done(hwnd, pids=None):
        tl = lights.pop(hwnd, None)
        _free_slot(hwnd)
        if tl and pids:
            try:
                pos = (tl.win.winfo_x(), tl.win.winfo_y())
                for pid in pids:
                    pid_pos[pid] = pos
            except Exception:
                pass
        if not window_ok(hwnd):
            name_map.pop(hwnd, None)
            pos_map.pop(hwnd, None)

    def discover():
        tray.pump()
        groups = discover_groups()

        for hwnd in list(lights):
            if hwnd not in groups:
                lights[hwnd].destroy()

        for hwnd, pids in groups.items():
            if hwnd in lights:
                lights[hwnd].pids = list(pids)
                for pid in pids:
                    if pid not in lights[hwnd]._prev_cpu:
                        lights[hwnd]._init_metrics(pid)
                    pid_pos[pid] = (lights[hwnd].win.winfo_x(), lights[hwnd].win.winfo_y())
                continue

            if hwnd in name_map:
                name = name_map[hwnd]
            else:
                try:
                    _, wpid = win32process.GetWindowThreadProcessId(hwnd)
                    raw_name = psutil.Process(wpid).name()
                    base = raw_name.replace(".exe", "").replace(".EXE", "")
                    base = {
                        "WindowsTerminal": "终端",
                        "windowsterminal": "终端",
                        "idea64": "idea64",
                        "cmd": "cmd",
                        "powershell": "powershell",
                        "pwsh": "powershell",
                    }.get(base, base)
                except Exception:
                    base = "未知"

                seq = name_seq.get(base, 1)
                name_seq[base] = seq + 1
                name = f"{base}-{seq}"
                name_map[hwnd] = name

            tl = TrafficLight(root, hwnd, hwnd, pids, name, on_done)
            lights[hwnd] = tl

            pos = None
            for pid in pids:
                if pid in pid_pos:
                    pos = pid_pos[pid]
                    break
            if pos is None and hwnd in pos_map:
                pos = pos_map[hwnd]
            if pos is None:
                x, y, _ = _alloc_slot(hwnd)
                pos = (x, y)
            x, y = pos
            pos_map[hwnd] = pos
            for pid in pids:
                pid_pos[pid] = pos
            tl.win.geometry(f"{tl._w}x{tl._h}+{x}+{y}")

        root.after(2000, discover)

    discover()

    try:
        root.mainloop()
    except KeyboardInterrupt:
        quit_app()


if __name__ == "__main__":
    main()
