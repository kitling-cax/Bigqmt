"""Single native Windows tray for both BigQMT profiles.

This replaces the previous two PowerShell notification icons.  It is an
operator UI only: all status refreshes are read-only, and it has no order or
cancel command.
"""

from __future__ import annotations

import json
import sys
import threading
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import win32api
import win32con
import win32gui


ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1])).resolve()
if getattr(sys, "frozen", False):
    # The frozen EXE is shipped directly in <project>\tray.
    ROOT = Path(sys.executable).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from kitling_bigqmt.tray_diagnostics import diagnose_tray  # noqa: E402
from kitling_bigqmt.tray_health import check_profile  # noqa: E402


CLASS_NAME = "KitlingBigQMTTrayManager"
WM_TRAY = win32con.WM_USER + 31
ID_REFRESH = 1001
ID_OPEN_SIM = 1002
ID_OPEN_FORMAL = 1003
ID_DIAG_SIM = 1004
ID_DIAG_FORMAL = 1005
ID_EXIT = 1006


class TrayManager:
    def __init__(self) -> None:
        self.hwnd = 0
        self.status: dict[str, dict[str, Any]] = {}
        self._refresh_lock = threading.Lock()

    @staticmethod
    def _port(profile: str) -> int:
        return 17890 if profile == "simulation" else 17891

    def refresh(self) -> None:
        if not self._refresh_lock.acquire(blocking=False):
            return
        try:
            self.status = {
                profile: check_profile(ROOT, profile, dashboard_port=self._port(profile), attempts=1)
                for profile in ("simulation", "production_readonly")
            }
            self._set_tip()
            self._audit("status_refreshed", {key: item.get("overall", "UNKNOWN") for key, item in self.status.items()})
        finally:
            self._refresh_lock.release()

    def _audit(self, event: str, detail: Any) -> None:
        path = ROOT / "runtime_data" / "audit" / "tray_manager.jsonl"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            record = {"event_time": datetime.now(timezone.utc).isoformat(), "event": event, "detail": detail,
                      "orders_enabled": False, "execution_consumer_enabled": False}
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
        except OSError:
            pass

    def _set_tip(self) -> None:
        sim = self.status.get("simulation", {}).get("overall", "PENDING")
        formal = self.status.get("production_readonly", {}).get("overall", "PENDING")
        tip = "BigQMT 托盘｜模拟 %s｜正式只读 %s" % (sim, formal)
        try:
            win32gui.Shell_NotifyIcon(win32gui.NIM_MODIFY, (self.hwnd, 0, win32gui.NIF_TIP, WM_TRAY, tip[:127]))
        except win32gui.error:
            pass

    def _open_dashboard(self, profile: str) -> None:
        route = "/simulation/overview" if profile == "simulation" else "/production-readonly/overview"
        webbrowser.open("http://127.0.0.1:%d%s" % (self._port(profile), route))
        self._audit("dashboard_opened", profile)

    def _show_diagnosis(self, profile: str) -> None:
        report = diagnose_tray(ROOT, profile, dashboard_port=self._port(profile))
        diagnosis = report["diagnosis"]
        health = report["service_health"].get("overall", "UNKNOWN")
        body = "%s\n\n服务状态：%s\n\n报告已保存：\n%s" % (
            diagnosis["explanation"], health,
            ROOT / "runtime_data" / "audit" / profile / "tray_diagnostic_latest.json",
        )
        win32gui.MessageBox(self.hwnd, body, "BigQMT %s 诊断" % profile, win32con.MB_OK | win32con.MB_ICONINFORMATION)
        self._audit("diagnosis_opened", profile)

    def _menu(self) -> None:
        menu = win32gui.CreatePopupMenu()
        sim_state = self.status.get("simulation", {}).get("overall", "PENDING")
        formal_state = self.status.get("production_readonly", {}).get("overall", "PENDING")
        win32gui.AppendMenu(menu, win32con.MF_STRING | win32con.MF_GRAYED, 0, "BigQMT 单一托盘管家")
        win32gui.AppendMenu(menu, win32con.MF_SEPARATOR, 0, "")
        win32gui.AppendMenu(menu, win32con.MF_STRING | win32con.MF_GRAYED, 0, "模拟盘 90000001：%s" % sim_state)
        win32gui.AppendMenu(menu, win32con.MF_STRING, ID_OPEN_SIM, "打开模拟盘看板")
        win32gui.AppendMenu(menu, win32con.MF_STRING, ID_DIAG_SIM, "生成模拟盘诊断")
        win32gui.AppendMenu(menu, win32con.MF_SEPARATOR, 0, "")
        win32gui.AppendMenu(menu, win32con.MF_STRING | win32con.MF_GRAYED, 0, "正式盘 90000002：%s（只读）" % formal_state)
        win32gui.AppendMenu(menu, win32con.MF_STRING, ID_OPEN_FORMAL, "打开正式盘只读看板")
        win32gui.AppendMenu(menu, win32con.MF_STRING, ID_DIAG_FORMAL, "生成正式盘诊断")
        win32gui.AppendMenu(menu, win32con.MF_SEPARATOR, 0, "")
        win32gui.AppendMenu(menu, win32con.MF_STRING, ID_REFRESH, "刷新状态")
        win32gui.AppendMenu(menu, win32con.MF_STRING, ID_EXIT, "退出托盘")
        win32gui.SetForegroundWindow(self.hwnd)
        win32gui.TrackPopupMenu(menu, win32con.TPM_LEFTALIGN | win32con.TPM_BOTTOMALIGN, *win32gui.GetCursorPos(), 0, self.hwnd, None)
        win32gui.PostMessage(self.hwnd, win32con.WM_NULL, 0, 0)

    def _notify(self, hwnd: int, msg: int, wparam: int, lparam: int) -> int:
        if lparam in (win32con.WM_RBUTTONUP, win32con.WM_CONTEXTMENU):
            self._menu()
        elif lparam == win32con.WM_LBUTTONDBLCLK:
            self._open_dashboard("simulation")
        return 0

    def _command(self, hwnd: int, msg: int, wparam: int, lparam: int) -> int:
        command = win32api.LOWORD(wparam)
        if command == ID_REFRESH:
            threading.Thread(target=self.refresh, daemon=True).start()
        elif command == ID_OPEN_SIM:
            self._open_dashboard("simulation")
        elif command == ID_OPEN_FORMAL:
            self._open_dashboard("production_readonly")
        elif command == ID_DIAG_SIM:
            threading.Thread(target=self._show_diagnosis, args=("simulation",), daemon=True).start()
        elif command == ID_DIAG_FORMAL:
            threading.Thread(target=self._show_diagnosis, args=("production_readonly",), daemon=True).start()
        elif command == ID_EXIT:
            win32gui.DestroyWindow(self.hwnd)
        return 0

    def _destroy(self, hwnd: int, msg: int, wparam: int, lparam: int) -> int:
        try:
            win32gui.Shell_NotifyIcon(win32gui.NIM_DELETE, (self.hwnd, 0))
        except win32gui.error:
            pass
        self._audit("tray_manager_stopped", "user_exit")
        win32gui.PostQuitMessage(0)
        return 0

    def run(self) -> int:
        if win32gui.FindWindow(CLASS_NAME, None):
            return 0
        wc = win32gui.WNDCLASS()
        wc.hInstance = win32gui.GetModuleHandle(None)
        wc.lpszClassName = CLASS_NAME
        wc.lpfnWndProc = {WM_TRAY: self._notify, win32con.WM_COMMAND: self._command, win32con.WM_DESTROY: self._destroy}
        class_atom = win32gui.RegisterClass(wc)
        self.hwnd = win32gui.CreateWindow(class_atom, CLASS_NAME, win32con.WS_OVERLAPPED, 0, 0, 0, 0, 0, 0, wc.hInstance, None)
        icon = win32gui.LoadIcon(0, win32con.IDI_APPLICATION)
        win32gui.Shell_NotifyIcon(win32gui.NIM_ADD, (self.hwnd, 0, win32gui.NIF_ICON | win32gui.NIF_MESSAGE | win32gui.NIF_TIP, WM_TRAY, icon, "BigQMT 托盘｜状态加载中"))
        self._audit("tray_manager_started", "single native icon; read-only")
        self.refresh()
        win32gui.PumpMessages()
        return 0


if __name__ == "__main__":
    raise SystemExit(TrayManager().run())
