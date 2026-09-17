"""Native one-account BigQMT tray, packaged as one EXE per account.

This UI performs only read-only health and diagnostic operations.  It cannot
submit or cancel an order, regardless of profile.
"""

from __future__ import annotations

import argparse
import ctypes
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


def _root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent.parent
    return Path(__file__).resolve().parents[1]


ROOT = _root()
sys.path.insert(0, str(ROOT / "src"))
from kitling_bigqmt.tray_diagnostics import diagnose_tray  # noqa: E402
from kitling_bigqmt.tray_health import check_profile  # noqa: E402
from kitling_bigqmt.host_agent_client import HostAgentClient  # noqa: E402
from kitling_bigqmt.coordinator_endpoint import resolve_coordinator  # noqa: E402
from kitling_bigqmt.host_agent_account_policy import resolve_account_policy  # noqa: E402


WM_TRAY = win32con.WM_USER + 51
ID_OPEN_DASHBOARD, ID_REFRESH, ID_DIAGNOSE, ID_EXIT = 2001, 2002, 2003, 2004
_USER32 = ctypes.windll.user32


def _profile_icon_path(profile: str) -> Path:
    """Return the profile-specific icon placed beside the account EXE."""
    name = (
        "BigQMT_Simulation_90000001.ico"
        if profile == "simulation"
        else "BigQMT_Production_ReadOnly_90000002.ico"
    )
    return ROOT / "tray" / name


def _load_profile_icon(profile: str) -> int:
    """Load the real account icon, falling back only when the file is absent."""
    icon_path = _profile_icon_path(profile)
    if icon_path.is_file():
        try:
            return win32gui.LoadImage(
                0,
                str(icon_path),
                win32con.IMAGE_ICON,
                32,
                32,
                win32con.LR_LOADFROMFILE | win32con.LR_DEFAULTSIZE,
            )
        except win32gui.error:
            pass
    return win32gui.LoadIcon(0, win32con.IDI_APPLICATION)


class AccountTray:
    def __init__(self, profile: str) -> None:
        self.profile = profile
        self.account = "90000001" if profile == "simulation" else "90000002"
        self.title = "BigQMT 模拟盘 %s" % self.account if profile == "simulation" else "BigQMT 正式只读 %s" % self.account
        self.port = 17890 if profile == "simulation" else 17891
        self.class_name = "KitlingBigQMTTray-" + profile
        self.hwnd = 0
        self.icon = None
        self.health: dict[str, Any] = {"overall": "PENDING"}
        endpoint, host_id = resolve_coordinator(ROOT)
        self.coordinator = HostAgentClient(endpoint, host_id)
        self.policy = resolve_account_policy(self.profile, self.account)

    def _audit(self, event: str, detail: Any) -> None:
        path = ROOT / "runtime_data" / "audit" / self.profile / "native_tray.jsonl"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            record = {"event_time": datetime.now(timezone.utc).isoformat(), "event": event, "detail": detail,
                      "orders_enabled": False, "execution_consumer_enabled": False}
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
        except OSError:
            pass

    def refresh(self) -> None:
        self.health = check_profile(ROOT, self.profile, dashboard_port=self.port, attempts=1)
        # Never block the UI on the control plane. This is a read-only
        # heartbeat; failures are recorded locally and cannot affect QMT.
        threading.Thread(target=self._send_heartbeat, daemon=True).start()
        state = str(self.health.get("overall", "UNKNOWN"))
        # Do not call NIM_MODIFY here.  pywin32 versions differ in the
        # accepted NOTIFYICONDATA tuple and can raise a fatal PyHANDLE error.
        # The icon remains stable; current status is visible in the context
        # menu, audit log and Coordinator heartbeat.
        self._audit("status_refreshed", state)

    def _send_heartbeat(self) -> None:
        try:
            services = {"qmt": str(self.health.get("qmt", "UNKNOWN")),
                        "redis": str(self.health.get("redis", "UNKNOWN")),
                        "bridge": str(self.health.get("bridge", "UNKNOWN")),
                        "tray": "UP"}
            self.coordinator.heartbeat(services, account_ids=[self.account])
            self._audit("coordinator_heartbeat", "accepted")
        except Exception as exc:  # control-plane outage must not stop tray
            self._audit("coordinator_heartbeat", {"status": "unavailable", "error": type(exc).__name__})

    def _poll_intents(self) -> None:
        try:
            preview = self.coordinator.readonly_intent_preview(self.account)
            self._audit("coordinator_intent_preview", {
                "account_id": preview.account_id,
                "host_id": preview.host_id,
                "intent_count": len(preview.intents),
                "orders_enabled": preview.orders_enabled,
            })
        except Exception as exc:  # empty preview is the only accepted outcome
            self._audit("coordinator_intent_preview", {
                "status": "unavailable_or_rejected", "error": type(exc).__name__,
            })

    def _open_dashboard(self) -> None:
        route = "/simulation/overview" if self.profile == "simulation" else "/production-readonly/overview"
        webbrowser.open("http://127.0.0.1:%d%s" % (self.port, route))
        self._audit("dashboard_opened", "read_only")

    def _diagnose(self) -> None:
        report = diagnose_tray(ROOT, self.profile, dashboard_port=self.port)
        diagnosis = report["diagnosis"]
        body = "%s\n\n服务状态：%s\n订单：锁定\n\n报告：\n%s" % (
            diagnosis["explanation"], report["service_health"].get("overall", "UNKNOWN"),
            ROOT / "runtime_data" / "audit" / self.profile / "tray_diagnostic_latest.json",
        )
        win32gui.MessageBox(self.hwnd, body, self.title + " 诊断", win32con.MB_OK | win32con.MB_ICONINFORMATION)
        self._audit("diagnosis_opened", diagnosis["code"])

    def _menu(self) -> None:
        menu = win32gui.CreatePopupMenu()
        state = str(self.health.get("overall", "PENDING"))
        win32gui.AppendMenu(menu, win32con.MF_STRING | win32con.MF_GRAYED, 0, self.title)
        win32gui.AppendMenu(menu, win32con.MF_STRING | win32con.MF_GRAYED, 0, "状态：%s｜订单锁定" % state)
        win32gui.AppendMenu(menu, win32con.MF_SEPARATOR, 0, "")
        win32gui.AppendMenu(menu, win32con.MF_STRING, ID_OPEN_DASHBOARD, "打开看板")
        win32gui.AppendMenu(menu, win32con.MF_STRING, ID_REFRESH, "刷新状态")
        win32gui.AppendMenu(menu, win32con.MF_STRING, ID_DIAGNOSE, "生成诊断报告")
        win32gui.AppendMenu(menu, win32con.MF_SEPARATOR, 0, "")
        win32gui.AppendMenu(menu, win32con.MF_STRING, ID_EXIT, "退出托盘")
        win32gui.SetForegroundWindow(self.hwnd)
        win32gui.TrackPopupMenu(menu, win32con.TPM_LEFTALIGN | win32con.TPM_BOTTOMALIGN, *win32gui.GetCursorPos(), 0, self.hwnd, None)
        win32gui.PostMessage(self.hwnd, win32con.WM_NULL, 0, 0)

    def _notify(self, hwnd: int, msg: int, wparam: int, lparam: int) -> int:
        if lparam in (win32con.WM_RBUTTONUP, win32con.WM_CONTEXTMENU):
            self._menu()
        elif lparam == win32con.WM_LBUTTONDBLCLK:
            self._open_dashboard()
        return 0

    def _command(self, hwnd: int, msg: int, wparam: int, lparam: int) -> int:
        command = win32api.LOWORD(wparam)
        if command == ID_OPEN_DASHBOARD:
            self._open_dashboard()
        elif command == ID_REFRESH:
            self.refresh()
        elif command == ID_DIAGNOSE:
            self._diagnose()
        elif command == ID_EXIT:
            win32gui.DestroyWindow(self.hwnd)
        return 0

    def _timer(self, hwnd: int, msg: int, wparam: int, lparam: int) -> int:
        self.refresh()
        threading.Thread(target=self._poll_intents, daemon=True).start()
        return 0

    def _destroy(self, hwnd: int, msg: int, wparam: int, lparam: int) -> int:
        _USER32.KillTimer(self.hwnd, 1)
        try:
            win32gui.Shell_NotifyIcon(win32gui.NIM_DELETE, (self.hwnd, 0))
        except win32gui.error:
            pass
        self._audit("tray_stopped", "user_exit")
        win32gui.PostQuitMessage(0)
        return 0

    def run(self) -> int:
        if win32gui.FindWindow(self.class_name, None):
            return 0
        wc = win32gui.WNDCLASS()
        wc.hInstance = win32gui.GetModuleHandle(None)
        wc.lpszClassName = self.class_name
        wc.lpfnWndProc = {WM_TRAY: self._notify, win32con.WM_COMMAND: self._command, win32con.WM_TIMER: self._timer, win32con.WM_DESTROY: self._destroy}
        atom = win32gui.RegisterClass(wc)
        self.hwnd = win32gui.CreateWindow(atom, self.class_name, win32con.WS_OVERLAPPED, 0, 0, 0, 0, 0, 0, wc.hInstance, None)
        self.icon = _load_profile_icon(self.profile)
        win32gui.Shell_NotifyIcon(win32gui.NIM_ADD, (self.hwnd, self.icon, win32gui.NIF_ICON | win32gui.NIF_MESSAGE | win32gui.NIF_TIP, WM_TRAY, self.icon, self.title + "｜状态加载中"))
        self._audit("tray_started", "native_one_account_exe; read_only")
        self.refresh()
        _USER32.SetTimer(self.hwnd, 1, 30000, 0)
        win32gui.PumpMessages()
        return 0


def main(profile: str | None = None) -> int:
    if profile is None:
        parser = argparse.ArgumentParser()
        parser.add_argument("--profile", choices=("simulation", "production_readonly"), required=True)
        profile = parser.parse_args().profile
    return AccountTray(profile).run()


if __name__ == "__main__":
    raise SystemExit(main())
