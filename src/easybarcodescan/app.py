import base64
import ctypes
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import urllib.parse
from ctypes import wintypes
from dataclasses import asdict, dataclass
from datetime import datetime
from io import BytesIO
from pathlib import Path

import tkinter as tk
from curl_cffi import requests
from .global_hotkey import HotkeyError, HotkeyPermissionError, add_hotkey, get_default_hotkey, remove_hotkey
from .version import APP_VERSION
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageGrab, ImageOps, ImageTk
from .zbar_compat import prepare_zbar_environment

prepare_zbar_environment()

from pyzbar.pyzbar import decode
from tkinter import messagebox, ttk


_DIALOG_PARENT = None
_MESSAGEBOX_SHOWINFO = messagebox.showinfo
_MESSAGEBOX_SHOWWARNING = messagebox.showwarning
_MESSAGEBOX_SHOWERROR = messagebox.showerror
_MESSAGEBOX_ASKYESNO = messagebox.askyesno


def set_dialog_parent(parent) -> None:
    global _DIALOG_PARENT
    _DIALOG_PARENT = parent


def get_dialog_parent():
    root = _DIALOG_PARENT
    if root is None:
        return None
    try:
        if not root.winfo_exists():
            return None
        focused_widget = root.focus_get()
        if focused_widget is not None:
            focused_window = focused_widget.winfo_toplevel()
            if focused_window and focused_window.winfo_exists():
                return focused_window
    except Exception:
        pass
    return root


def prepare_dialog_options(options: dict) -> dict:
    if "parent" not in options or options.get("parent") is None:
        parent = get_dialog_parent()
        if parent is not None:
            options["parent"] = parent

    parent = options.get("parent")
    if parent is not None:
        try:
            parent.attributes("-topmost", True)
        except Exception:
            pass
        try:
            parent.lift()
            parent.focus_force()
        except Exception:
            pass
    return options


def show_info_dialog(title=None, message=None, **options):
    return _MESSAGEBOX_SHOWINFO(title, message, **prepare_dialog_options(options))


def show_warning_dialog(title=None, message=None, **options):
    return _MESSAGEBOX_SHOWWARNING(title, message, **prepare_dialog_options(options))


def show_error_dialog(title=None, message=None, **options):
    return _MESSAGEBOX_SHOWERROR(title, message, **prepare_dialog_options(options))


def ask_yes_no_dialog(title=None, message=None, **options):
    return _MESSAGEBOX_ASKYESNO(title, message, **prepare_dialog_options(options))


messagebox.showinfo = show_info_dialog
messagebox.showwarning = show_warning_dialog
messagebox.showerror = show_error_dialog
messagebox.askyesno = ask_yes_no_dialog


if platform.system() == "Windows":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


APP_NAME = "EasyBarcodeScan"
API_URL = "https://bff.gds.org.cn/gds/searching-api/ProductService/ProductListByGTIN"
MAX_HISTORY_ITEMS = 200
TOKEN_EXPIRY_SKEW_SECONDS = 30
PASSWORD_KEYCHAIN_SERVICE = f"{APP_NAME}.credential"
OSS_BASE_URL = "https://oss.gds.org.cn"
IS_PACKAGED_APP = bool(getattr(sys, "frozen", False))
ENABLE_CONSOLE_DEBUG = not IS_PACKAGED_APP
PROJECT_ROOT = Path(__file__).resolve().parents[2]
MACOS_SCREEN_CAPTURE_BIN = "/usr/sbin/screencapture"
MACOS_SETUP_NOTICE = (
    "macOS 首次使用前请先开启系统权限：\n"
    "1. 打开“系统设置 → 隐私与安全性 → 屏幕录制”，允许当前启动器或 EasyBarcodeScan.app。\n"
    "2. 打开“系统设置 → 隐私与安全性 → 输入监控”，允许当前启动器或 EasyBarcodeScan.app。\n"
    "3. 打开“系统设置 → 隐私与安全性 → 辅助功能”，允许当前启动器或 EasyBarcodeScan.app。\n"
    "4. 如果是从 Terminal、iTerm、VS Code 或 PyCharm 启动，请授权对应启动器；如果是打包后的 .app，请授权 EasyBarcodeScan.app。\n"
    "5. 授权后请完全退出并重新打开本程序。\n\n"
    "macOS 默认快捷键：Control + Shift + A。\n"
    "如果你此前使用过 Command + Shift + A，部分终端/IDE 可能会优先拦截它。"
)


def get_app_data_dir() -> Path:
    if platform.system() == "Darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    if platform.system() == "Windows":
        app_data = os.environ.get("APPDATA")
        if app_data:
            return Path(app_data) / APP_NAME
    return Path.home() / ".config" / APP_NAME


def get_config_file_path() -> Path:
    if IS_PACKAGED_APP:
        return get_app_data_dir() / "config.json"
    return PROJECT_ROOT / "config" / "config.json"


def get_legacy_config_candidates(config_file_path: Path) -> list[Path]:
    candidates = []
    if IS_PACKAGED_APP:
        candidates.append(Path.cwd() / "config.json")
        candidates.append(Path(sys.executable).resolve().parent / "config.json")
        candidates.append(Path.cwd() / "config" / "config.json")
    else:
        candidates.append(Path.cwd() / "config.json")
        candidates.append(Path.cwd() / "config" / "config.json")
        candidates.append(PROJECT_ROOT / "config.json")
        candidates.append(Path(__file__).resolve().parent / "config.json")
    unique_paths = []
    seen = set()
    for path in candidates:
        resolved = str(path.resolve())
        if resolved in seen:
            continue
        seen.add(resolved)
        if path.resolve() != config_file_path.resolve():
            unique_paths.append(path)
    return unique_paths


def build_picture_url(item_data: dict) -> str:
    raw_path = str(
        item_data.get("picture_filename")
        or item_data.get("pictureFilename")
        or item_data.get("picture_url")
        or ""
    ).strip()
    if not raw_path:
        return ""
    if raw_path.startswith("http://") or raw_path.startswith("https://"):
        return raw_path
    if not raw_path.startswith("/"):
        raw_path = "/" + raw_path
    return f"{OSS_BASE_URL}{raw_path}"


def build_picture_candidates(picture_url: str) -> list[str]:
    raw_url = str(picture_url or "").strip()
    if not raw_url:
        return []

    if raw_url.startswith("/"):
        raw_url = f"{OSS_BASE_URL}{raw_url}"

    parsed = urllib.parse.urlsplit(raw_url)
    if not parsed.scheme:
        raw_url = f"{OSS_BASE_URL.rstrip('/')}/{raw_url.lstrip('/')}"
        parsed = urllib.parse.urlsplit(raw_url)

    candidates = []
    seen = set()

    def add_url(url: str) -> None:
        cleaned = str(url or "").strip()
        if not cleaned or cleaned in seen:
            return
        seen.add(cleaned)
        candidates.append(cleaned)

    def build_url_with_path(path: str, use_https: bool | None = None) -> str:
        target_scheme = parsed.scheme
        if use_https is True:
            target_scheme = "https"
        elif use_https is False:
            target_scheme = "http"
        return urllib.parse.urlunsplit((target_scheme, parsed.netloc, path, parsed.query, parsed.fragment))

    base_path = parsed.path or "/"
    add_url(build_url_with_path(base_path))

    encoded_path = urllib.parse.quote(base_path, safe="/%._-")
    if encoded_path != base_path:
        add_url(build_url_with_path(encoded_path))

    path_dir, _, filename = base_path.rpartition("/")
    if filename:
        if filename.startswith("m") and len(filename) > 1:
            alt_filename = filename[1:]
        else:
            alt_filename = f"m{filename}"
        alt_path = f"{path_dir}/{alt_filename}" if path_dir else f"/{alt_filename}"
        add_url(build_url_with_path(alt_path))

        encoded_alt_path = urllib.parse.quote(alt_path, safe="/%._-")
        if encoded_alt_path != alt_path:
            add_url(build_url_with_path(encoded_alt_path))

    if parsed.scheme.lower() == "http":
        for candidate in list(candidates):
            parsed_candidate = urllib.parse.urlsplit(candidate)
            https_candidate = urllib.parse.urlunsplit(
                ("https", parsed_candidate.netloc, parsed_candidate.path, parsed_candidate.query, parsed_candidate.fragment)
            )
            add_url(https_candidate)

    return candidates


HOTKEY_MODIFIER_ORDER = ("command", "ctrl", "alt", "shift")
HOTKEY_MODIFIER_KEYS = {
    "control_l": "ctrl",
    "control_r": "ctrl",
    "shift_l": "shift",
    "shift_r": "shift",
    "alt_l": "alt",
    "alt_r": "alt",
    "option_l": "alt",
    "option_r": "alt",
    "meta_l": "command",
    "meta_r": "command",
    "command": "command",
    "command_l": "command",
    "command_r": "command",
    "super_l": "command",
    "super_r": "command",
}
HOTKEY_TOKEN_ALIASES = {
    "cmd": "command",
    "ctl": "ctrl",
    "control": "ctrl",
    "option": "alt",
    "return": "enter",
    "escape": "esc",
}
HOTKEY_DISPLAY_NAMES = {
    "command": "Command",
    "ctrl": "Ctrl",
    "alt": "Alt",
    "shift": "Shift",
    "esc": "Esc",
    "tab": "Tab",
    "enter": "Enter",
    "space": "Space",
    "delete": "Delete",
    "backspace": "Backspace",
    "left": "Left",
    "right": "Right",
    "up": "Up",
    "down": "Down",
}
HOTKEY_SPECIAL_KEYS = {
    "space": "space",
    "tab": "tab",
    "iso_left_tab": "tab",
    "return": "enter",
    "enter": "enter",
    "kp_enter": "enter",
    "escape": "esc",
    "esc": "esc",
    "left": "left",
    "right": "right",
    "up": "up",
    "down": "down",
    "delete": "delete",
    "backspace": "backspace",
}


def normalize_optional_text(value) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    if text.lower() in {"none", "null"}:
        return ""
    return text


def pick_first_text(data: dict, *keys: str, default: str = "") -> str:
    if not isinstance(data, dict):
        return default
    for key in keys:
        text = normalize_optional_text(data.get(key))
        if text:
            return text
    return default


def get_product_name_text(item_data: dict, default: str = "未知") -> str:
    return pick_first_text(
        item_data,
        "keyword",
        "RegulatedProductName",
        "regulatedProductName",
        "ProductName",
        "productName",
        "product_name",
        default=default,
    )


def debug_console(message: str, payload=None) -> None:
    if not ENABLE_CONSOLE_DEBUG:
        return
    try:
        timestamp = datetime.now().strftime("%H:%M:%S")
        if payload is None:
            print(f"[{APP_NAME} {timestamp}] {message}", flush=True)
            return

        if isinstance(payload, (dict, list, tuple)):
            payload_text = json.dumps(payload, ensure_ascii=False, default=str)
        else:
            payload_text = str(payload)
        if len(payload_text) > 5000:
            payload_text = payload_text[:5000] + " ...(truncated)"
        print(f"[{APP_NAME} {timestamp}] {message} | {payload_text}", flush=True)
    except Exception:
        pass


@dataclass
class HistoryRecord:
    query_time: str
    barcode: str
    product_name: str
    brand: str
    firm_name: str
    specification: str
    category: str
    picture_url: str

    @classmethod
    def from_item(cls, item_data: dict, barcode: str) -> "HistoryRecord":
        return cls(
            query_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            barcode=barcode,
            product_name=get_product_name_text(item_data),
            brand=normalize_optional_text(item_data.get("brandcn")) or "未知",
            firm_name=normalize_optional_text(item_data.get("firm_name")) or "未知",
            specification=normalize_optional_text(item_data.get("specification")) or "未知",
            category=normalize_optional_text(item_data.get("gpcname")) or "未知",
            picture_url=build_picture_url(item_data),
        )


class BarcodeScannerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        set_dialog_parent(self.root)
        self.root.title(APP_NAME)
        if platform.system() != "Darwin":
            self.root.attributes("-topmost", True)
        self.root.configure(bg="#ebf2ff")
        self.root.report_callback_exception = self.handle_tk_callback_exception

        self.style = ttk.Style()
        self.setup_styles()
        self.disable_primary_selection_bindings()
        self.center_window(self.root, 660, 500)
        min_root_w, min_root_h = self.scale_window_size(self.root, 620, 460)
        self.root.minsize(min_root_w, min_root_h)

        self.config_file_path = get_config_file_path()
        self.config = self.load_config()
        self.current_hotkey = self.get_initial_hotkey()
        self.token = self.config.get("token", "")
        self.remember_password = bool(self.config.get("remember_password", False))
        self.saved_username = str(self.config.get("saved_username", ""))
        self.saved_password_encrypted = str(self.config.get("saved_password_encrypted", ""))
        self.saved_password = ""
        self.history_records = self.load_history_from_config(self.config.get("history_records", []))
        self.token_expired_on_startup = bool(self.token and self.is_token_expired(self.token))
        if self.token_expired_on_startup:
            self.token = ""

        self.migrate_legacy_password_storage()
        if self.remember_password and self.saved_username:
            self.saved_password = self.load_saved_password_secure(self.saved_username)

        self.is_snipping = False
        self.hotkey_handler = None
        self.hotkey_status_message = ""
        self.macos_setup_notice_scheduled = False
        self.local_hotkey_sequences: list[str] = []
        self.login_session = None
        self.auth_env = {}
        self.pending_login_username = ""
        self.pending_login_password = ""
        self.pending_remember_password = False

        self.is_querying = False
        self.scan_session_counter = 0
        self.active_scan_session_id: int | None = None
        self.query_total = 0
        self.query_done = 0

        self.history_window = None
        self.history_tree = None
        self.last_summary_var = tk.StringVar(value="最近一次扫描：暂无")
        self.result_window = None
        self.result_products = []
        self.result_index = 0
        self.result_count_var = tk.StringVar(value="")
        self.result_product_name_var = tk.StringVar(value="")
        self.result_field_vars = {}
        self.result_field_rows = {}
        self.result_detail_wrap = None
        self.result_name_value_label = None
        self.result_image_cache = {}
        self.result_current_full_image = None
        self.result_current_picture_url = ""
        self.image_preview_window = None
        self.image_preview_canvas = None
        self.image_preview_state = {}

        self.build_home_ui()
        self.register_application_shortcuts()
        self.update_local_hotkey_binding()
        self.bind_hotkey_async()
        self.update_status_labels()
        self.check_trigger()
        if self.token_expired_on_startup:
            self.save_config()
            self.last_summary_var.set("最近一次扫描：登录已过期，请重新登录")
            self.root.after(200, lambda: messagebox.showwarning("登录状态", "检测到登录已过期，请重新登录。"))

        self.root.protocol("WM_DELETE_WINDOW", self.hide_main_window)

    def get_initial_hotkey(self) -> str:
        configured_hotkey = self.normalize_hotkey_text(str(self.config.get("hotkey", "") or ""))
        default_hotkey = get_default_hotkey()
        if platform.system() == "Darwin" and configured_hotkey in (
            "",
            "ctrl+alt+a",
            "ctrl + alt + a",
            "command+shift+a",
            "command + shift + a",
        ):
            self.config["hotkey"] = default_hotkey
            return default_hotkey
        return configured_hotkey or default_hotkey

    def setup_styles(self) -> None:
        preferred_theme = "vista" if "vista" in self.style.theme_names() else "clam"
        self.style.theme_use(preferred_theme)

        self.style.configure("Primary.TButton", font=("微软雅黑", 10, "bold"), padding=(14, 6))
        self.style.configure("Secondary.TButton", font=("微软雅黑", 10), padding=(12, 6))
        self.style.configure("Danger.TButton", font=("微软雅黑", 10), padding=(12, 6))
        self.style.configure("Login.TEntry", font=("微软雅黑", 10), padding=6)
        self.style.configure("Login.TButton", font=("微软雅黑", 10, "bold"), padding=(12, 9))
        self.style.configure("Login.TCheckbutton", font=("微软雅黑", 9))
        self.style.configure("History.Treeview", rowheight=26, font=("微软雅黑", 10))
        self.style.configure("History.Treeview.Heading", font=("微软雅黑", 10, "bold"))

    def register_application_shortcuts(self) -> None:
        if platform.system() == "Darwin":
            try:
                self.root.createcommand("tk::mac::ReopenApplication", self.show_main_window)
            except Exception:
                pass
            try:
                self.root.bind_all("<Command-q>", lambda _event: self.quit_application())
            except Exception:
                pass
            return

        try:
            self.root.bind_all("<Control-q>", lambda _event: self.quit_application())
        except Exception:
            pass

    @staticmethod
    def get_quit_shortcut_text() -> str:
        if platform.system() == "Darwin":
            return "Command + Q"
        return "Ctrl + Q"

    @staticmethod
    def sort_hotkey_modifiers(modifiers) -> list[str]:
        ordered: list[str] = []
        seen: set[str] = set()
        for token in HOTKEY_MODIFIER_ORDER:
            if token in modifiers and token not in seen:
                ordered.append(token)
                seen.add(token)
        for token in modifiers:
            if token not in seen:
                ordered.append(token)
                seen.add(token)
        return ordered

    @staticmethod
    def normalize_hotkey_text(hotkey: str) -> str:
        raw_tokens = [part.strip().lower() for part in str(hotkey or "").replace("＋", "+").split("+") if part.strip()]
        if not raw_tokens:
            return ""

        normalized_tokens: list[str] = []
        for token in raw_tokens:
            token = HOTKEY_TOKEN_ALIASES.get(token, token)
            if re.fullmatch(r"f\d{1,2}", token):
                token = token.lower()
            normalized_tokens.append(token)

        if len(normalized_tokens) == 1:
            return normalized_tokens[0]

        key_token = normalized_tokens[-1]
        modifier_tokens = BarcodeScannerApp.sort_hotkey_modifiers(normalized_tokens[:-1])
        return "+".join(modifier_tokens + [key_token])

    @staticmethod
    def get_hotkey_display_text(hotkey: str) -> str:
        normalized_hotkey = BarcodeScannerApp.normalize_hotkey_text(hotkey)
        if not normalized_hotkey:
            return ""

        display_parts: list[str] = []
        for token in normalized_hotkey.split("+"):
            if len(token) == 1 and token.isalnum():
                display_parts.append(token.upper())
                continue
            if re.fullmatch(r"f\d{1,2}", token):
                display_parts.append(token.upper())
                continue
            display_parts.append(HOTKEY_DISPLAY_NAMES.get(token, token.title()))
        return " + ".join(display_parts)

    @staticmethod
    def get_hotkey_modifier_token(keysym: str) -> str | None:
        token = HOTKEY_MODIFIER_KEYS.get(str(keysym or "").strip().lower())
        if token == "command" and platform.system() != "Darwin":
            return None
        return token

    def get_hotkey_modifiers_from_state(self, state: int, active_modifiers: list[str]) -> list[str]:
        modifiers = set(active_modifiers)
        if state & 0x0004:
            modifiers.add("ctrl")
        if state & 0x0001:
            modifiers.add("shift")
        if state & 0x0008:
            modifiers.add("alt")
        if platform.system() == "Darwin" and state & (0x0010 | 0x0040 | 0x0080):
            modifiers.add("command")
        return self.sort_hotkey_modifiers(modifiers)

    @staticmethod
    def normalize_hotkey_key_token(keysym: str) -> str | None:
        raw_key = str(keysym or "").strip()
        if not raw_key:
            return None

        lower_key = raw_key.lower()
        if lower_key in HOTKEY_MODIFIER_KEYS:
            return None
        if len(raw_key) == 1 and raw_key.isalnum():
            return raw_key.lower()
        if lower_key.startswith("kp_"):
            keypad_key = lower_key[3:]
            if len(keypad_key) == 1 and keypad_key.isdigit():
                return keypad_key
        mapped_key = HOTKEY_SPECIAL_KEYS.get(lower_key)
        if mapped_key:
            return mapped_key
        if re.fullmatch(r"f\d{1,2}", lower_key):
            try:
                if 1 <= int(lower_key[1:]) <= 19:
                    return lower_key
            except Exception:
                return None
        return None

    def get_hotkey_modifier_preview_text(self, modifiers: list[str]) -> str:
        if not modifiers:
            return "请按新的快捷键"
        preview = [HOTKEY_DISPLAY_NAMES.get(token, token.title()) for token in self.sort_hotkey_modifiers(modifiers)]
        return " + ".join(preview + ["..."])

    def build_hotkey_from_key_event(self, keysym: str, state: int, active_modifiers: list[str]) -> str | None:
        key_token = self.normalize_hotkey_key_token(keysym)
        if not key_token:
            return None
        modifier_tokens = self.get_hotkey_modifiers_from_state(state, active_modifiers)
        return self.normalize_hotkey_text("+".join(modifier_tokens + [key_token]))

    def capture_hotkey_from_keyboard(self) -> str | None:
        dialog = tk.Toplevel(self.root)
        dialog.title("修改快捷键")
        dialog.configure(bg="#f8fafc")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        self.center_window(dialog, 430, 220)

        result = {"value": None}
        active_modifiers: list[str] = []
        preview_var = tk.StringVar(value="请按新的快捷键")
        tip_var = tk.StringVar(
            value="支持字母、数字、F1-F19、方向键、ESC、TAB、ENTER、SPACE、DELETE。"
        )

        tk.Label(
            dialog,
            text="请直接按新的快捷键组合，识别后会自动保存。",
            font=("微软雅黑", 10, "bold"),
            bg="#f8fafc",
            fg="#0f172a",
            justify="left",
        ).pack(anchor="w", padx=18, pady=(16, 6))
        tk.Label(
            dialog,
            text=f"当前快捷键：{self.get_hotkey_display_text(self.current_hotkey)}",
            font=("微软雅黑", 9),
            bg="#f8fafc",
            fg="#64748b",
            justify="left",
        ).pack(anchor="w", padx=18)

        capture_box = tk.Frame(
            dialog,
            bg="#ffffff",
            bd=1,
            relief="solid",
            highlightbackground="#cbd5e1",
            highlightcolor="#2563eb",
            highlightthickness=1,
            takefocus=1,
        )
        capture_box.pack(fill="x", padx=18, pady=(14, 8))
        tk.Label(
            capture_box,
            textvariable=preview_var,
            font=("微软雅黑", 15, "bold"),
            bg="#ffffff",
            fg="#1d4ed8",
            pady=18,
        ).pack(fill="x")
        tk.Label(
            dialog,
            textvariable=tip_var,
            font=("微软雅黑", 9),
            bg="#f8fafc",
            fg="#475569",
            wraplength=394,
            justify="left",
        ).pack(anchor="w", padx=18)

        button_frame = tk.Frame(dialog, bg="#f8fafc")
        button_frame.pack(fill="x", padx=18, pady=(14, 14))

        def close_dialog() -> None:
            try:
                dialog.grab_release()
            except Exception:
                pass
            dialog.destroy()

        def cancel_dialog() -> None:
            result["value"] = None
            close_dialog()

        ttk.Button(button_frame, text="取消", style="Secondary.TButton", command=cancel_dialog).pack(side="right")

        def on_key_press(event) -> str:
            keysym = str(getattr(event, "keysym", "") or "")
            modifier_token = self.get_hotkey_modifier_token(keysym)
            if modifier_token:
                if modifier_token not in active_modifiers:
                    active_modifiers.append(modifier_token)
                preview_var.set(self.get_hotkey_modifier_preview_text(active_modifiers))
                tip_var.set("已识别修饰键，请继续按主键完成组合。")
                return "break"

            hotkey = self.build_hotkey_from_key_event(keysym, int(getattr(event, "state", 0) or 0), active_modifiers)
            if not hotkey:
                preview_var.set("不支持的按键")
                tip_var.set("请改用字母、数字、F1-F19、方向键、ESC、TAB、ENTER、SPACE、DELETE。")
                return "break"

            result["value"] = hotkey
            preview_var.set(self.get_hotkey_display_text(hotkey))
            tip_var.set("已识别，正在保存快捷键……")
            dialog.after(120, close_dialog)
            return "break"

        def on_key_release(event) -> str:
            modifier_token = self.get_hotkey_modifier_token(str(getattr(event, "keysym", "") or ""))
            if modifier_token in active_modifiers:
                active_modifiers.remove(modifier_token)
            if result["value"] is None:
                preview_var.set(self.get_hotkey_modifier_preview_text(active_modifiers))
            return "break"

        dialog.protocol("WM_DELETE_WINDOW", cancel_dialog)
        dialog.bind("<Button-1>", lambda _event: capture_box.focus_set(), add="+")
        capture_box.bind("<Button-1>", lambda _event: capture_box.focus_set())
        capture_box.bind("<KeyPress>", on_key_press)
        capture_box.bind("<KeyRelease>", on_key_release)

        self.bring_window_front(dialog, self.root)
        dialog.grab_set()
        capture_box.focus_set()
        dialog.wait_window()
        return result["value"]

    def restore_hotkey_binding(self, hotkey: str, should_bind: bool, fallback_status_message: str) -> None:
        self.current_hotkey = hotkey
        self.hotkey_handler = None
        self.hotkey_status_message = fallback_status_message
        if should_bind:
            try:
                self.hotkey_handler = add_hotkey(hotkey, self.trigger_snip)
                self.hotkey_status_message = "已启用"
            except HotkeyPermissionError as error:
                self.hotkey_status_message = f"未启用：{error}"
            except HotkeyError as error:
                debug_console("恢复快捷键失败", {"hotkey": hotkey, "error": str(error)})
        self.update_local_hotkey_binding()
        self.update_status_labels()

    def update_local_hotkey_binding(self) -> None:
        if platform.system() != "Darwin":
            return

        target_widgets = self.get_local_hotkey_target_widgets()
        for sequence in self.local_hotkey_sequences:
            for widget in target_widgets:
                try:
                    widget.unbind(sequence)
                except Exception:
                    pass
        self.local_hotkey_sequences = []

        sequences = self.get_tk_hotkey_sequences(self.current_hotkey)
        if not sequences:
            return

        for sequence in sequences:
            for widget in target_widgets:
                try:
                    widget.bind(sequence, self.handle_local_hotkey)
                except Exception:
                    pass
        self.local_hotkey_sequences = sequences

    def get_local_hotkey_target_widgets(self) -> list[tk.Misc]:
        widgets: list[tk.Misc] = []
        seen_widget_ids: set[str] = set()

        def add_widget(widget) -> None:
            if widget is None:
                return
            try:
                if not widget.winfo_exists():
                    return
                widget_id = str(widget)
            except Exception:
                return
            if widget_id in seen_widget_ids:
                return
            seen_widget_ids.add(widget_id)
            widgets.append(widget)

        add_widget(self.root)
        for attr_name in (
            "history_window",
            "result_window",
            "image_preview_window",
            "login_win",
        ):
            add_widget(getattr(self, attr_name, None))
        for attr_name in ("entry_user", "entry_pwd", "entry_cap"):
            add_widget(getattr(self, attr_name, None))
        return widgets

    @staticmethod
    def get_tk_hotkey_sequences(hotkey: str) -> list[str]:
        raw_tokens = [part.strip().lower() for part in str(hotkey or "").split("+") if part.strip()]
        if not raw_tokens:
            return []

        key_token = raw_tokens[-1]
        modifier_tokens = raw_tokens[:-1]
        modifier_map = {
            "cmd": "Command",
            "command": "Command",
            "shift": "Shift",
            "ctrl": "Control",
            "control": "Control",
            "alt": "Option",
            "option": "Option",
        }
        modifiers: list[str] = []
        for token in modifier_tokens:
            mapped = modifier_map.get(token)
            if mapped and mapped not in modifiers:
                modifiers.append(mapped)

        key_variants: list[str] = []
        if len(key_token) == 1 and key_token.isalpha():
            key_variants = [key_token.lower(), key_token.upper()]
        elif len(key_token) == 1 and key_token.isdigit():
            key_variants = [key_token]
        elif re.fullmatch(r"f\d{1,2}", key_token):
            key_variants = [key_token.upper()]
        else:
            special_map = {
                "space": "space",
                "tab": "Tab",
                "enter": "Return",
                "return": "Return",
                "esc": "Escape",
                "escape": "Escape",
                "left": "Left",
                "right": "Right",
                "up": "Up",
                "down": "Down",
                "delete": "Delete",
                "backspace": "BackSpace",
            }
            mapped_key = special_map.get(key_token)
            if mapped_key:
                key_variants = [mapped_key]

        sequences: list[str] = []
        for key_variant in key_variants:
            sequences.append("<" + "-".join(modifiers + [key_variant]) + ">")
        return sequences

    def handle_local_hotkey(self, _event=None):
        self.trigger_snip()
        return "break"

    def handle_tk_callback_exception(self, exc_type, exc_value, exc_traceback) -> None:
        error_text = str(exc_value)
        if (
            "PRIMARY selection" in error_text
            or "selection doesn't exist" in error_text
            or 'form "STRING" not defined' in error_text
            or 'format "STRING" not defined' in error_text
        ):
            if platform.system() == "Darwin" and hasattr(self, "last_summary_var"):
                self.last_summary_var.set(
                    "最近一次扫描：快捷键被当前输入框或启动器接管，请开启“辅助功能”权限，必要时修改快捷键。"
                )
            debug_console("忽略 macOS Tk PRIMARY 选择区异常", error_text)
            return

        try:
            traceback.print_exception(exc_type, exc_value, exc_traceback)
        except Exception:
            pass

    def disable_primary_selection_bindings(self) -> None:
        if platform.system() != "Darwin":
            return

        def ignore_primary_selection(_event=None):
            return "break"

        for widget_class in ("Entry", "TEntry", "Text", "Spinbox", "TSpinbox", "Combobox", "TCombobox"):
            for sequence in ("<<PasteSelection>>", "<Button-2>", "<ButtonRelease-2>", "<B2-Motion>"):
                try:
                    self.root.bind_class(widget_class, sequence, ignore_primary_selection)
                except Exception:
                    pass

    def build_home_ui(self) -> None:
        main_frame = tk.Frame(self.root, bg="#ebf2ff")
        main_frame.pack(fill="both", expand=True, padx=22, pady=(16, 14))

        title_frame = tk.Frame(main_frame, bg="#ebf2ff")
        title_frame.pack(fill="x")
        tk.Label(
            title_frame,
            text=APP_NAME,
            font=("微软雅黑", 24, "bold"),
            bg="#ebf2ff",
            fg="#1e3a8a",
        ).pack(anchor="w")
        tk.Label(
            title_frame,
            text="条码扫描工具",
            font=("微软雅黑", 10),
            bg="#ebf2ff",
            fg="#486088",
        ).pack(anchor="w", pady=(2, 0))

        status_card = tk.Frame(main_frame, bg="#ffffff", bd=1, relief="solid")
        status_card.pack(fill="x", pady=(14, 10))
        self.hotkey_label = tk.Label(status_card, font=("微软雅黑", 10), bg="#ffffff", fg="#111827")
        self.hotkey_label.pack(anchor="w", padx=16, pady=(10, 2))
        self.token_label = tk.Label(status_card, font=("微软雅黑", 10, "bold"), bg="#ffffff")
        self.token_label.pack(anchor="w", padx=16, pady=(0, 10))

        if platform.system() == "Darwin":
            macos_card = tk.Frame(main_frame, bg="#fff7ed", bd=1, relief="solid")
            macos_card.pack(fill="x", pady=(0, 10))
            tk.Label(
                macos_card,
                text="macOS 前置设置：需开启“屏幕录制”和“输入监控”，授权后重启程序。",
                font=("微软雅黑", 9),
                bg="#fff7ed",
                fg="#9a3412",
                wraplength=588,
                justify="left",
            ).pack(side="left", anchor="w", padx=14, pady=8, expand=True, fill="x")
            ttk.Button(
                macos_card,
                text="查看说明",
                style="Secondary.TButton",
                command=self.show_macos_setup_notice,
            ).pack(side="right", padx=(0, 12), pady=8)

        result_card = tk.Frame(main_frame, bg="#ffffff", bd=1, relief="solid")
        result_card.pack(fill="x")
        tk.Label(
            result_card,
            text="扫描状态",
            font=("微软雅黑", 10, "bold"),
            bg="#ffffff",
            fg="#1f2937",
        ).pack(anchor="w", padx=16, pady=(10, 2))
        self.summary_label = tk.Label(
            result_card,
            textvariable=self.last_summary_var,
            font=("微软雅黑", 10),
            bg="#ffffff",
            fg="#374151",
            wraplength=588,
            justify="left",
        )
        self.summary_label.pack(anchor="w", padx=16, pady=(0, 10))

        btn_frame = tk.Frame(main_frame, bg="#ebf2ff")
        btn_frame.pack(fill="x", pady=(14, 8))
        self.auth_btn = ttk.Button(btn_frame, text="登录", style="Primary.TButton", command=self.handle_auth_action)
        self.auth_btn.grid(
            row=0, column=0, padx=5, sticky="ew"
        )
        ttk.Button(btn_frame, text="开始截图", style="Secondary.TButton", command=self.manual_start_snip).grid(
            row=0, column=1, padx=5, sticky="ew"
        )
        ttk.Button(btn_frame, text="修改快捷键", style="Secondary.TButton", command=self.change_hotkey).grid(
            row=0, column=2, padx=5, sticky="ew"
        )
        ttk.Button(btn_frame, text="历史记录", style="Secondary.TButton", command=self.open_history).grid(
            row=0, column=3, padx=5, sticky="ew"
        )
        ttk.Button(btn_frame, text="清空历史", style="Danger.TButton", command=self.clear_history).grid(
            row=0, column=4, padx=5, sticky="ew"
        )
        ttk.Button(btn_frame, text="退出程序", style="Danger.TButton", command=self.quit_application).grid(
            row=0, column=5, padx=5, sticky="ew"
        )
        for column_index in range(6):
            btn_frame.grid_columnconfigure(column_index, weight=1)

        tk.Label(
            main_frame,
            text=self.get_scan_tip_text(),
            font=("微软雅黑", 9),
            bg="#ebf2ff",
            fg="#64748b",
        ).pack(anchor="w", pady=(4, 8))
        tk.Label(
            main_frame,
            text=f"点叉号只会隐藏到后台，程序仍可全局监听；如需完全退出，请按 {self.get_quit_shortcut_text()} 或点击“退出程序”。",
            font=("微软雅黑", 9),
            bg="#ebf2ff",
            fg="#64748b",
            wraplength=588,
            justify="left",
        ).pack(anchor="w", pady=(0, 6))
        tk.Label(
            main_frame,
            text="by Ryan",
            font=("微软雅黑", 8),
            bg="#ebf2ff",
            fg="#94a3b8",
        ).pack(anchor="e", pady=(2, 0))

        self.root.bind("<Configure>", self.on_home_resize)

    @staticmethod
    def get_scan_tip_text() -> str:
        if platform.system() == "Darwin":
            return "提示：按快捷键后使用 macOS 系统截图框选条码区域，按 ESC 可取消。"
        return "提示：按快捷键框选条码区域，按 ESC 取消截屏。"

    def show_macos_setup_notice(self) -> None:
        if platform.system() != "Darwin":
            return
        messagebox.showinfo("macOS 使用前设置", MACOS_SETUP_NOTICE)

    def show_macos_setup_notice_if_needed(self) -> None:
        return

    def hide_main_window(self) -> None:
        if self.is_snipping:
            self.last_summary_var.set("最近一次扫描：正在截图中，截图结束后仍会继续后台监听。")
            return
        try:
            self.root.withdraw()
        except Exception:
            return
        hotkey_display = self.get_hotkey_display_text(self.current_hotkey) or self.current_hotkey.upper()
        self.last_summary_var.set(
            f"最近一次扫描：主窗口已隐藏到后台，仍可按 {hotkey_display} 截图；完全退出请按 {self.get_quit_shortcut_text()}。"
        )

    def show_main_window(self, *_args) -> None:
        try:
            if not self.root.winfo_exists():
                return
        except Exception:
            return
        self.bring_window_front(self.root)
        try:
            self.root.focus_force()
        except Exception:
            pass

    def on_home_resize(self, _event=None) -> None:
        if not hasattr(self, "summary_label"):
            return
        if not (self.summary_label and self.summary_label.winfo_exists()):
            return
        width = self.summary_label.winfo_width()
        if width <= 40:
            return
        self.summary_label.config(wraplength=max(220, width - 6))

    def update_status_labels(self) -> None:
        hotkey_display = self.get_hotkey_display_text(self.current_hotkey) or self.current_hotkey.upper()
        hotkey_text = f"当前快捷键：{hotkey_display}"
        if self.hotkey_status_message:
            hotkey_text = f"{hotkey_text}（{self.hotkey_status_message}）"
        self.hotkey_label.config(text=hotkey_text)
        if self.token:
            if self.is_token_expired(self.token):
                self.token_label.config(text="登录状态：已过期（请登录）", fg="#d93025")
            else:
                self.token_label.config(text="登录状态：已登录", fg="#0f9d58")
        else:
            self.token_label.config(text="登录状态：未登录（请先登录）", fg="#d93025")

        if hasattr(self, "auth_btn") and self.auth_btn:
            if self.token and not self.is_token_expired(self.token):
                self.auth_btn.config(text="退出登录")
            else:
                self.auth_btn.config(text="登录")

    def bring_window_front(self, window, parent=None) -> None:
        if window is None:
            return
        try:
            if not window.winfo_exists():
                return
        except Exception:
            return

        target_parent = parent
        if target_parent is None and window is not self.root and not self.is_window_hidden(self.root):
            target_parent = self.root

        try:
            if target_parent is not None and target_parent is not window:
                window.transient(target_parent)
        except Exception:
            pass
        try:
            if str(window.state()) in ("iconic", "withdrawn"):
                window.deiconify()
        except Exception:
            pass
        try:
            window.attributes("-topmost", True)
            if platform.system() == "Darwin":
                window.after(200, lambda current_window=window: self._set_window_topmost(current_window, False))
        except Exception:
            pass
        try:
            window.lift()
            window.focus_force()
        except Exception:
            pass

    @staticmethod
    def _set_window_topmost(window, enabled: bool) -> None:
        try:
            if window and window.winfo_exists():
                window.attributes("-topmost", enabled)
        except Exception:
            pass

    @staticmethod
    def is_window_hidden(window) -> bool:
        try:
            return str(window.state()) in ("iconic", "withdrawn")
        except Exception:
            return False

    def collect_open_windows_for_capture(self) -> list[tuple[tk.Toplevel, str]]:
        windows: list[tuple[tk.Toplevel, str]] = []
        candidates = [
            self.image_preview_window,
            self.result_window,
            self.history_window,
            getattr(self, "login_win", None),
            self.root,
        ]
        for window in candidates:
            if window is None:
                continue
            try:
                if not window.winfo_exists():
                    continue
                windows.append((window, str(window.state())))
            except Exception:
                continue
        return windows

    def prepare_macos_capture_windows(self) -> list[tuple[tk.Toplevel, str]]:
        snapshots = self.collect_open_windows_for_capture()
        for window, _state in snapshots:
            try:
                window.attributes("-topmost", False)
            except Exception:
                pass
            try:
                window.withdraw()
            except Exception:
                pass
        try:
            self.root.update()
        except Exception:
            pass
        time.sleep(0.18)
        return snapshots

    def restore_macos_capture_windows(self, snapshots: list[tuple[tk.Toplevel, str]]) -> None:
        for window, state in reversed(snapshots):
            try:
                if not window.winfo_exists():
                    continue
            except Exception:
                continue
            if state == "withdrawn":
                continue
            if state == "iconic":
                try:
                    window.iconify()
                except Exception:
                    pass
                continue
            try:
                window.deiconify()
            except Exception:
                pass
            self.bring_window_front(window, self.root)

    def handle_auth_action(self) -> None:
        if self.token and not self.is_token_expired(self.token):
            self.clear_login_info()
            return

        if self.token and self.is_token_expired(self.token):
            self.mark_token_expired("登录已过期，请重新登录。", notify=False)

        self.show_login_window()

    def manual_start_snip(self) -> None:
        if self.is_querying:
            messagebox.showwarning("提示", "当前正在查询中，请稍候再截图。")
            return
        self.start_snip()

    @staticmethod
    def parse_jwt_payload(token: str) -> dict | None:
        if not token or token.count(".") != 2:
            return None
        try:
            payload_part = token.split(".")[1]
            payload_part += "=" * (-len(payload_part) % 4)
            payload_bytes = base64.urlsafe_b64decode(payload_part.encode("utf-8"))
            payload_obj = json.loads(payload_bytes.decode("utf-8"))
            if isinstance(payload_obj, dict):
                return payload_obj
        except Exception:
            return None
        return None

    def get_token_expire_at(self, token: str) -> datetime | None:
        payload = self.parse_jwt_payload(token)
        if not payload:
            return None
        exp = payload.get("exp")
        if exp is None:
            return None
        try:
            return datetime.fromtimestamp(int(exp))
        except Exception:
            return None

    def is_token_expired(self, token: str) -> bool:
        expire_at = self.get_token_expire_at(token)
        if not expire_at:
            return False
        return datetime.now().timestamp() >= (expire_at.timestamp() - TOKEN_EXPIRY_SKEW_SECONDS)

    @staticmethod
    def is_token_invalid_response(data: dict) -> bool:
        if not isinstance(data, dict):
            return False
        code = data.get("Code")
        if code in (401, 403):
            return True
        message_parts = [
            str(data.get("Msg", "")),
            str(data.get("Message", "")),
            str(data.get("Error", "")),
        ]
        message_text = " ".join(message_parts).lower()
        token_keywords = ("token", "expired", "invalid", "过期", "失效", "未授权", "授权失败")
        return any(keyword in message_text for keyword in token_keywords)

    def mark_token_expired(self, reason: str = "登录已过期，请重新登录。", notify: bool = True) -> None:
        had_token = bool(self.token)
        self.token = ""
        self.update_status_labels()
        self.last_summary_var.set("最近一次扫描：登录已过期，请重新登录")
        self.save_config()
        if notify and (had_token or reason):
            messagebox.showwarning("登录失效", reason)

    def clear_login_info(self) -> None:
        if not messagebox.askyesno("退出登录", "确定退出登录并清除登录信息吗？"):
            return

        previous_username = self.saved_username
        if previous_username:
            self.clear_saved_password_secure(previous_username)

        self.token = ""
        self.remember_password = False
        self.saved_username = ""
        self.saved_password = ""
        self.saved_password_encrypted = ""
        self.pending_login_username = ""
        self.pending_login_password = ""
        self.pending_remember_password = False

        self.save_config()
        self.update_status_labels()
        self.last_summary_var.set("最近一次扫描：已退出登录，请重新登录")

        if hasattr(self, "remember_pwd_var"):
            self.remember_pwd_var.set(False)
        if hasattr(self, "entry_user") and self.entry_user and self.entry_user.winfo_exists():
            self.entry_user.delete(0, "end")
        if hasattr(self, "entry_pwd") and self.entry_pwd and self.entry_pwd.winfo_exists():
            self.entry_pwd.delete(0, "end")

        messagebox.showinfo("已退出", "登录信息已清除。")

    @staticmethod
    def get_password_storage_backend() -> str:
        system_name = platform.system()
        if system_name == "Windows":
            return "dpapi"
        if system_name == "Darwin":
            return "keychain"
        return "unsupported"

    @staticmethod
    def _dpapi_encrypt_bytes(raw_bytes: bytes) -> bytes | None:
        if platform.system() != "Windows" or not raw_bytes:
            return None
        try:
            class DATA_BLOB(ctypes.Structure):
                _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]

            crypt32 = ctypes.windll.crypt32
            kernel32 = ctypes.windll.kernel32
            in_buffer = ctypes.create_string_buffer(raw_bytes, len(raw_bytes))
            in_blob = DATA_BLOB(len(raw_bytes), ctypes.cast(in_buffer, ctypes.POINTER(ctypes.c_byte)))
            out_blob = DATA_BLOB()

            if not crypt32.CryptProtectData(
                ctypes.byref(in_blob),
                APP_NAME,
                None,
                None,
                None,
                0,
                ctypes.byref(out_blob),
            ):
                return None

            try:
                return ctypes.string_at(out_blob.pbData, out_blob.cbData)
            finally:
                kernel32.LocalFree(out_blob.pbData)
        except Exception:
            return None

    @staticmethod
    def _dpapi_decrypt_bytes(encrypted_bytes: bytes) -> bytes | None:
        if platform.system() != "Windows" or not encrypted_bytes:
            return None
        try:
            class DATA_BLOB(ctypes.Structure):
                _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]

            crypt32 = ctypes.windll.crypt32
            kernel32 = ctypes.windll.kernel32
            in_buffer = ctypes.create_string_buffer(encrypted_bytes, len(encrypted_bytes))
            in_blob = DATA_BLOB(len(encrypted_bytes), ctypes.cast(in_buffer, ctypes.POINTER(ctypes.c_byte)))
            out_blob = DATA_BLOB()

            if not crypt32.CryptUnprotectData(
                ctypes.byref(in_blob),
                None,
                None,
                None,
                None,
                0,
                ctypes.byref(out_blob),
            ):
                return None

            try:
                return ctypes.string_at(out_blob.pbData, out_blob.cbData)
            finally:
                kernel32.LocalFree(out_blob.pbData)
        except Exception:
            return None

    @staticmethod
    def _save_to_macos_keychain(username: str, password: str) -> bool:
        if platform.system() != "Darwin":
            return False
        if not username or not password:
            return False
        try:
            result = subprocess.run(
                ["security", "add-generic-password", "-a", username, "-s", PASSWORD_KEYCHAIN_SERVICE, "-w", password, "-U"],
                capture_output=True,
                text=True,
                check=False,
            )
            return result.returncode == 0
        except Exception:
            return False

    @staticmethod
    def _load_from_macos_keychain(username: str) -> str:
        if platform.system() != "Darwin" or not username:
            return ""
        try:
            result = subprocess.run(
                ["security", "find-generic-password", "-a", username, "-s", PASSWORD_KEYCHAIN_SERVICE, "-w"],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                return ""
            return result.stdout.strip()
        except Exception:
            return ""

    @staticmethod
    def _delete_from_macos_keychain(username: str) -> None:
        if platform.system() != "Darwin" or not username:
            return
        try:
            subprocess.run(
                ["security", "delete-generic-password", "-a", username, "-s", PASSWORD_KEYCHAIN_SERVICE],
                capture_output=True,
                text=True,
                check=False,
            )
        except Exception:
            pass

    def store_saved_password_secure(self, username: str, password: str) -> bool:
        backend = self.get_password_storage_backend()
        if backend == "dpapi":
            encrypted = self._dpapi_encrypt_bytes(password.encode("utf-8"))
            if not encrypted:
                return False
            self.saved_password_encrypted = base64.b64encode(encrypted).decode("utf-8")
            return True
        if backend == "keychain":
            return self._save_to_macos_keychain(username, password)
        return False

    def load_saved_password_secure(self, username: str) -> str:
        backend = self.get_password_storage_backend()
        if backend == "dpapi":
            if not self.saved_password_encrypted:
                return ""
            try:
                encrypted = base64.b64decode(self.saved_password_encrypted.encode("utf-8"))
            except Exception:
                return ""
            decrypted = self._dpapi_decrypt_bytes(encrypted)
            if not decrypted:
                return ""
            return decrypted.decode("utf-8", errors="ignore")
        if backend == "keychain":
            return self._load_from_macos_keychain(username)
        return ""

    def clear_saved_password_secure(self, username: str = "") -> None:
        backend = self.get_password_storage_backend()
        if backend == "dpapi":
            self.saved_password_encrypted = ""
            return
        if backend == "keychain":
            self._delete_from_macos_keychain(username)

    def migrate_legacy_password_storage(self) -> None:
        old_plain_password = str(self.config.get("saved_password", ""))
        has_legacy_field = "saved_password" in self.config
        migrated = False
        if old_plain_password and self.remember_password and self.saved_username:
            migrated = self.store_saved_password_secure(self.saved_username, old_plain_password)
        if has_legacy_field:
            self.config.pop("saved_password", None)
        if has_legacy_field or migrated:
            self.save_config()

    @staticmethod
    def get_dpi_scale(win: tk.Toplevel) -> float:
        try:
            pixels_per_inch = float(win.winfo_fpixels("1i"))
            scale = pixels_per_inch / 96.0
            return max(1.0, min(scale, 2.0))
        except Exception:
            return 1.0

    @classmethod
    def scale_window_size(cls, win: tk.Toplevel, width: int, height: int) -> tuple[int, int]:
        dpi_scale = cls.get_dpi_scale(win)
        adaptive_scale = 1.0 + min(max(dpi_scale - 1.0, 0.0), 0.35) * 0.35
        scaled_w = int(width * adaptive_scale)
        scaled_h = int(height * adaptive_scale)
        return max(360, scaled_w), max(300, scaled_h)

    @classmethod
    def center_window(cls, win: tk.Toplevel, width: int, height: int) -> None:
        win.withdraw()
        win.update_idletasks()
        screen_width = win.winfo_screenwidth()
        screen_height = win.winfo_screenheight()
        scaled_w, scaled_h = cls.scale_window_size(win, width, height)
        safe_w = min(scaled_w, max(360, int(screen_width * 0.90)))
        safe_h = min(scaled_h, max(300, int(screen_height * 0.88)))
        width = max(380, safe_w)
        height = max(320, safe_h)
        x = (screen_width - width) // 2
        y = (screen_height - height) // 2
        win.geometry(f"{width}x{height}+{x}+{y}")
        win.deiconify()
        win.update()

    def load_config(self) -> dict:
        candidate_paths = [self.config_file_path] + get_legacy_config_candidates(self.config_file_path)

        for candidate_path in candidate_paths:
            if not candidate_path.exists():
                continue
            try:
                with open(candidate_path, "r", encoding="utf-8") as file:
                    loaded = json.load(file)
                if not isinstance(loaded, dict):
                    continue

                if candidate_path.resolve() != self.config_file_path.resolve():
                    try:
                        self.config_file_path.parent.mkdir(parents=True, exist_ok=True)
                        with open(self.config_file_path, "w", encoding="utf-8") as new_file:
                            json.dump(loaded, new_file, ensure_ascii=False, indent=4)
                        debug_console(
                            "配置迁移完成",
                            {"from": str(candidate_path), "to": str(self.config_file_path)},
                        )
                    except Exception as migrate_error:
                        debug_console(
                            "配置迁移失败",
                            {"from": str(candidate_path), "to": str(self.config_file_path), "error": str(migrate_error)},
                        )
                return loaded
            except Exception:
                continue

        return {
            "hotkey": get_default_hotkey(),
            "token": "",
            "history_records": [],
            "remember_password": False,
            "saved_username": "",
            "saved_password_encrypted": "",
            "macos_setup_notice_shown": False,
        }

    @staticmethod
    def load_history_from_config(raw_records: list) -> list:
        if not isinstance(raw_records, list):
            return []

        parsed_records = []
        for item in raw_records:
            if not isinstance(item, dict):
                continue
            parsed_records.append(
                HistoryRecord(
                    query_time=str(item.get("query_time", "")),
                    barcode=str(item.get("barcode", "")),
                    product_name=normalize_optional_text(item.get("product_name")) or "未知",
                    brand=normalize_optional_text(item.get("brand")) or "未知",
                    firm_name=normalize_optional_text(item.get("firm_name")) or "未知",
                    specification=normalize_optional_text(item.get("specification")) or "未知",
                    category=normalize_optional_text(item.get("category")) or "未知",
                    picture_url=normalize_optional_text(item.get("picture_url")),
                )
            )
        return parsed_records[:MAX_HISTORY_ITEMS]

    def save_config(self) -> None:
        self.config["hotkey"] = self.current_hotkey
        self.config["token"] = self.token
        self.config["remember_password"] = self.remember_password
        self.config["saved_username"] = self.saved_username if self.remember_password else ""
        self.config["saved_password_encrypted"] = self.saved_password_encrypted if self.remember_password else ""
        self.config.pop("saved_password", None)
        self.config["history_records"] = [asdict(record) for record in self.history_records[:MAX_HISTORY_ITEMS]]
        self.config_file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_file_path, "w", encoding="utf-8") as file:
            json.dump(self.config, file, ensure_ascii=False, indent=4)

    def bind_hotkey(self) -> None:
        try:
            new_handler = add_hotkey(self.current_hotkey, self.trigger_snip)
            self.on_hotkey_bound(new_handler)
        except HotkeyError as error:
            self.on_hotkey_bind_failed(error)

    def bind_hotkey_async(self) -> None:
        self.hotkey_status_message = "启动中"
        self.update_status_labels()

        def worker() -> None:
            def schedule_ui(callback) -> None:
                try:
                    self.root.after(0, callback)
                except Exception:
                    pass

            try:
                new_handler = add_hotkey(self.current_hotkey, self.trigger_snip)
            except HotkeyError as error:
                schedule_ui(lambda err=error: self.on_hotkey_bind_failed(err))
                return
            schedule_ui(lambda handle=new_handler: self.on_hotkey_bound(handle))

        threading.Thread(target=worker, daemon=True).start()

    def on_hotkey_bound(self, new_handler) -> None:
        if self.hotkey_handler is not None:
            remove_hotkey(self.hotkey_handler)
        self.hotkey_handler = new_handler
        self.hotkey_status_message = "已启用"
        self.update_local_hotkey_binding()
        self.update_status_labels()
        if platform.system() == "Darwin":
            hotkey_display = self.get_hotkey_display_text(self.current_hotkey) or self.current_hotkey.upper()
            self.last_summary_var.set(f"最近一次扫描：快捷键已启用，按 {hotkey_display} 或点击“开始截图”。")

    def on_hotkey_bind_failed(self, error: Exception) -> None:
        self.hotkey_handler = None
        self.hotkey_status_message = f"未启用：{error}"
        self.update_local_hotkey_binding()
        self.update_status_labels()
        if platform.system() == "Darwin":
            hotkey_display = self.get_hotkey_display_text(self.current_hotkey) or self.current_hotkey.upper()
            self.last_summary_var.set(
                f"快捷键未启用。当前可在程序窗口内按 {hotkey_display}；如需全局生效，请开启“输入监控”和“辅助功能”后重启。"
            )
            return
        self.last_summary_var.set("快捷键未启用，可先授权系统权限或修改快捷键后重试。")

    def show_hotkey_error(self, error: Exception) -> None:
        if platform.system() == "Darwin":
            if self.macos_setup_notice_scheduled:
                messagebox.showwarning("快捷键提示", f"{error}\n\n请按主界面的 macOS 前置设置开启“输入监控”，授权后重启程序。")
                return
            messagebox.showwarning("快捷键提示", f"{error}\n\n{MACOS_SETUP_NOTICE}")
            return
        messagebox.showwarning("快捷键提示", str(error))

    def change_hotkey(self) -> None:
        old_hotkey = self.current_hotkey
        old_status_message = self.hotkey_status_message
        old_hotkey_enabled = self.hotkey_handler is not None

        if old_hotkey_enabled:
            remove_hotkey(self.hotkey_handler)
            self.hotkey_handler = None
        self.hotkey_status_message = "录入中"
        self.update_status_labels()

        new_hotkey = self.capture_hotkey_from_keyboard()
        if not new_hotkey:
            self.restore_hotkey_binding(old_hotkey, old_hotkey_enabled, old_status_message)
            return

        new_hotkey = self.normalize_hotkey_text(new_hotkey)
        if not new_hotkey or new_hotkey == self.current_hotkey:
            self.restore_hotkey_binding(old_hotkey, old_hotkey_enabled, old_status_message)
            return

        try:
            new_handler = add_hotkey(new_hotkey, self.trigger_snip)
            self.hotkey_handler = new_handler
            self.current_hotkey = new_hotkey
            self.hotkey_status_message = "已启用"
            self.update_local_hotkey_binding()
            self.save_config()
            self.update_status_labels()
            messagebox.showinfo("成功", f"快捷键已修改为：{self.get_hotkey_display_text(self.current_hotkey)}")
        except HotkeyPermissionError as error:
            self.hotkey_handler = None
            self.current_hotkey = new_hotkey
            self.hotkey_status_message = f"未启用：{error}"
            self.update_local_hotkey_binding()
            self.save_config()
            self.update_status_labels()
            messagebox.showwarning(
                "快捷键提示",
                f"快捷键已修改为：{self.get_hotkey_display_text(self.current_hotkey)}。\n\n"
                "当前仅在 EasyBarcodeScan 窗口内可用；如需全局生效，请开启“输入监控”和“辅助功能”后重启程序。",
            )
        except HotkeyError as error:
            self.restore_hotkey_binding(old_hotkey, old_hotkey_enabled, old_status_message)
            messagebox.showerror("错误", f"设置快捷键失败，可能是格式不正确。\n{error}")

    def add_history_records(self, records: list[HistoryRecord]) -> None:
        if not records:
            return
        self.history_records = records + self.history_records
        self.history_records = self.history_records[:MAX_HISTORY_ITEMS]
        self.save_config()
        self.refresh_history_tree()

    def open_history(self) -> None:
        if self.history_window and self.history_window.winfo_exists():
            self.bring_window_front(self.history_window)
            self.refresh_history_tree()
            return

        self.history_window = tk.Toplevel(self.root)
        self.history_window.title(f"{APP_NAME} - 历史记录")
        self.history_window.configure(bg="#f8fafc")
        if platform.system() != "Darwin":
            self.history_window.attributes("-topmost", True)
        self.center_window(self.history_window, 1080, 500)
        min_history_w, min_history_h = self.scale_window_size(self.history_window, 860, 420)
        self.history_window.minsize(min_history_w, min_history_h)
        self.bring_window_front(self.history_window)
        self.update_local_hotkey_binding()

        toolbar = tk.Frame(self.history_window, bg="#f8fafc")
        toolbar.pack(fill="x", padx=12, pady=(12, 6))
        tk.Label(
            toolbar,
            text="历史记录",
            font=("微软雅黑", 12, "bold"),
            bg="#f8fafc",
            fg="#0f172a",
        ).pack(side="left")
        ttk.Button(toolbar, text="复制选中条码", command=self.copy_selected_barcode).pack(side="right", padx=6)
        ttk.Button(toolbar, text="清空", command=self.clear_history).pack(side="right", padx=6)

        table_frame = tk.Frame(self.history_window, bg="#f8fafc")
        table_frame.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        columns = ("time", "barcode", "product", "brand", "firm", "specification", "category")
        self.history_tree = ttk.Treeview(
            table_frame,
            columns=columns,
            show="headings",
            style="History.Treeview",
        )

        column_config = [
            ("time", "查询时间", 150),
            ("barcode", "查询条码", 140),
            ("product", "商品名称", 200),
            ("brand", "品牌", 120),
            ("firm", "生产企业", 220),
            ("specification", "规格", 120),
            ("category", "分类", 140),
        ]
        for key, heading, width in column_config:
            self.history_tree.heading(key, text=heading)
            self.history_tree.column(key, width=width, anchor="w")

        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.history_tree.yview)
        self.history_tree.configure(yscrollcommand=scrollbar.set)
        self.history_tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.history_tree.bind("<Double-1>", lambda _: self.copy_selected_barcode())
        self.history_window.protocol("WM_DELETE_WINDOW", self.close_history_window)

        self.refresh_history_tree()

    def refresh_history_tree(self) -> None:
        if not (self.history_tree and self.history_tree.winfo_exists()):
            return

        for item_id in self.history_tree.get_children():
            self.history_tree.delete(item_id)

        for record in self.history_records:
            self.history_tree.insert(
                "",
                "end",
                values=(
                    record.query_time,
                    record.barcode,
                    record.product_name,
                    record.brand,
                    record.firm_name,
                    record.specification,
                    record.category,
                ),
            )

        if not self.history_records:
            self.history_tree.insert(
                "",
                "end",
                values=("暂无记录", "-", "-", "-", "-", "-", "-"),
            )

    def close_history_window(self) -> None:
        if self.history_window and self.history_window.winfo_exists():
            self.history_window.destroy()
        self.history_window = None
        self.history_tree = None

    def clear_history(self) -> None:
        if not self.history_records:
            messagebox.showinfo("提示", "当前没有历史记录。")
            return
        if messagebox.askyesno("确认清空", "确定清空所有历史记录吗？"):
            self.history_records.clear()
            self.save_config()
            self.refresh_history_tree()
            self.last_summary_var.set("最近一次扫描：暂无")

    def copy_selected_barcode(self) -> None:
        if not (self.history_tree and self.history_tree.winfo_exists()):
            return
        selected = self.history_tree.selection()
        if not selected:
            messagebox.showinfo("提示", "请先选择一条历史记录。")
            return
        values = self.history_tree.item(selected[0], "values")
        if len(values) < 2 or values[1] == "-":
            return
        barcode = values[1]
        self.root.clipboard_clear()
        self.root.clipboard_append(barcode)
        messagebox.showinfo("已复制", f"条码已复制到剪贴板：{barcode}")

    def show_product_detail_window(self, products: list[dict]) -> None:
        if not products:
            return

        self.result_products = products
        self.result_index = 0

        if self.result_window and self.result_window.winfo_exists():
            self.result_window.destroy()

        self.result_window = tk.Toplevel(self.root)
        self.result_window.title(f"{APP_NAME} - 商品详情")
        self.result_window.configure(bg="#eef4ff")
        self.center_window(self.result_window, 900, 580)
        min_result_w, min_result_h = self.scale_window_size(self.result_window, 820, 520)
        self.result_window.minsize(min_result_w, min_result_h)
        self.result_window.resizable(True, True)
        self.bring_window_front(self.result_window)
        self.update_local_hotkey_binding()

        header = tk.Frame(self.result_window, bg="#eef4ff")
        header.pack(fill="x", padx=16, pady=(14, 8))
        tk.Label(
            header,
            text="查询结果",
            font=("微软雅黑", 14, "bold"),
            bg="#eef4ff",
            fg="#1e3a8a",
        ).pack(side="left")
        tk.Label(
            header,
            textvariable=self.result_count_var,
            font=("微软雅黑", 10),
            bg="#eef4ff",
            fg="#475569",
        ).pack(side="right")

        content = tk.Frame(self.result_window, bg="#ffffff", bd=0, highlightthickness=0)
        content.pack(fill="both", expand=True, padx=16, pady=(0, 10))
        content.grid_rowconfigure(0, weight=1)
        content.grid_columnconfigure(1, weight=1)

        image_wrap = tk.Frame(content, bg="#ffffff", bd=0, highlightthickness=0, width=320, height=320)
        image_wrap.grid(row=0, column=0, sticky="nsw", padx=(14, 8), pady=14)
        image_wrap.grid_propagate(False)
        self.result_image_label = tk.Label(
            image_wrap,
            text="图片加载中...",
            font=("微软雅黑", 10),
            bg="#ffffff",
            fg="#64748b",
            justify="center",
            cursor="arrow",
        )
        self.result_image_label.pack(fill="both", expand=True)
        self.result_image_label.bind("<Button-1>", self.open_result_image_preview)

        detail_wrap = tk.Frame(content, bg="#ffffff")
        detail_wrap.grid(row=0, column=1, sticky="nsew", padx=(8, 14), pady=14)
        detail_wrap.grid_columnconfigure(0, weight=1, uniform="detail_col")
        detail_wrap.grid_columnconfigure(1, weight=1, uniform="detail_col")
        self.result_detail_wrap = detail_wrap

        name_card = tk.Frame(detail_wrap, bg="#f8fafc", bd=0, highlightthickness=0)
        name_card.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        tk.Label(
            name_card,
            text="商品名称",
            font=("微软雅黑", 9),
            bg="#f8fafc",
            fg="#64748b",
            anchor="w",
        ).pack(fill="x", padx=12, pady=(8, 2))
        self.result_name_value_label = tk.Label(
            name_card,
            textvariable=self.result_product_name_var,
            font=("微软雅黑", 11, "bold"),
            bg="#f8fafc",
            fg="#0f172a",
            anchor="w",
            justify="left",
            wraplength=520,
        )
        self.result_name_value_label.pack(fill="x", padx=12, pady=(0, 10))

        self.result_field_vars = {
            "barcode": tk.StringVar(value=""),
            "regulated_name": tk.StringVar(value=""),
            "brand": tk.StringVar(value=""),
            "firm_name": tk.StringVar(value=""),
            "specification": tk.StringVar(value=""),
            "category": tk.StringVar(value=""),
            "description": tk.StringVar(value=""),
        }
        self.result_field_rows = {}
        field_defs = [
            ("barcode", "条码", 1, 0, 1),
            ("brand", "品牌", 1, 1, 1),
            ("firm_name", "生产企业", 2, 0, 1),
            ("specification", "规格", 2, 1, 1),
            ("category", "分类", 3, 0, 1),
            ("regulated_name", "规范名称", 3, 1, 1),
            ("description", "描述", 4, 0, 2),
        ]
        for field_key, field_title, row, column, columnspan in field_defs:
            card = tk.Frame(detail_wrap, bg="#f8fafc", bd=0, highlightthickness=0)
            title_label = tk.Label(
                card,
                text=field_title,
                font=("微软雅黑", 9),
                bg="#f8fafc",
                fg="#64748b",
                anchor="w",
                justify="left",
            )
            title_label.pack(fill="x", padx=10, pady=(8, 2))
            value_label = tk.Label(
                card,
                textvariable=self.result_field_vars[field_key],
                font=("微软雅黑", 10),
                bg="#f8fafc",
                fg="#0f172a",
                anchor="w",
                justify="left",
                wraplength=520 if columnspan == 2 else 250,
            )
            value_label.pack(fill="x", padx=10, pady=(0, 8))
            if columnspan == 2:
                padx = (0, 0)
            elif column == 0:
                padx = (0, 8)
            else:
                padx = (8, 0)
            grid_options = {
                "row": row,
                "column": column,
                "columnspan": columnspan,
                "sticky": "ew",
                "padx": padx,
                "pady": 4,
            }
            card.grid(**grid_options)
            self.result_field_rows[field_key] = {
                "frame": card,
                "value_label": value_label,
                "grid_options": grid_options,
            }

        detail_wrap.bind("<Configure>", self.on_result_detail_resize)
        self.root.after(0, self.on_result_detail_resize)

        footer = tk.Frame(self.result_window, bg="#eef4ff")
        footer.pack(fill="x", padx=16, pady=(0, 14))
        self.prev_result_btn = ttk.Button(footer, text="上一条", command=self.show_prev_result)
        self.prev_result_btn.pack(side="left")
        self.next_result_btn = ttk.Button(footer, text="下一条", command=self.show_next_result)
        self.next_result_btn.pack(side="left", padx=(6, 0))
        ttk.Button(footer, text="关闭", style="Secondary.TButton", command=self.close_result_window).pack(side="right")

        self.result_window.protocol("WM_DELETE_WINDOW", self.close_result_window)
        self.result_window.bind("<Escape>", lambda _: self.close_result_window())
        self.render_current_result()

    def close_result_window(self) -> None:
        self.close_result_image_preview()
        if self.result_window and self.result_window.winfo_exists():
            self.result_window.destroy()
        self.result_window = None
        self.result_detail_wrap = None
        self.result_name_value_label = None

    def on_result_detail_resize(self, _event=None) -> None:
        if not (self.result_detail_wrap and self.result_detail_wrap.winfo_exists()):
            return

        detail_width = self.result_detail_wrap.winfo_width()
        if detail_width <= 40:
            return

        full_wrap = max(260, detail_width - 38)
        half_wrap = max(140, int((detail_width - 56) / 2))

        if self.result_name_value_label and self.result_name_value_label.winfo_exists():
            self.result_name_value_label.config(wraplength=full_wrap - 14)

        for row_meta in self.result_field_rows.values():
            value_label = row_meta.get("value_label")
            if not value_label or not value_label.winfo_exists():
                continue
            grid_options = row_meta.get("grid_options", {})
            columnspan = int(grid_options.get("columnspan", 1))
            target_wrap = full_wrap - 20 if columnspan >= 2 else half_wrap - 20
            value_label.config(wraplength=max(120, target_wrap))

    def show_prev_result(self) -> None:
        if not self.result_products:
            return
        if self.result_index > 0:
            self.result_index -= 1
            self.render_current_result()

    def show_next_result(self) -> None:
        if not self.result_products:
            return
        if self.result_index < len(self.result_products) - 1:
            self.result_index += 1
            self.render_current_result()

    def render_current_result(self) -> None:
        if not self.result_products:
            return
        if not (self.result_window and self.result_window.winfo_exists()):
            return
        self.close_result_image_preview()

        product = self.result_products[self.result_index]
        total_count = len(self.result_products)
        self.result_count_var.set(f"{self.result_index + 1} / {total_count}")

        product_name = normalize_optional_text(product.get("product_name")) or "-"
        regulated_name = normalize_optional_text(product.get("regulated_name"))
        regulated_to_show = regulated_name if regulated_name and regulated_name != product_name else None
        description = normalize_optional_text(product.get("description"))
        description_to_show = description if description else None

        picture_url = normalize_optional_text(product.get("picture_url"))
        picture_candidates = build_picture_candidates(picture_url)
        self.result_product_name_var.set(product_name)
        detail_data = [
            ("barcode", normalize_optional_text(product.get("barcode")) or "-"),
            ("brand", normalize_optional_text(product.get("brand")) or "-"),
            ("firm_name", normalize_optional_text(product.get("firm_name")) or "-"),
            ("specification", normalize_optional_text(product.get("specification")) or "-"),
            ("category", normalize_optional_text(product.get("category")) or "-"),
            ("regulated_name", regulated_to_show),
            ("description", description_to_show),
        ]

        for field_key, field_value in detail_data:
            row_meta = self.result_field_rows.get(field_key)
            if not row_meta:
                continue
            frame = row_meta["frame"]
            if field_value is None:
                frame.grid_remove()
                continue
            self.result_field_vars[field_key].set(field_value)
            frame.grid(**row_meta["grid_options"])

        if total_count <= 1:
            self.prev_result_btn.config(state="disabled")
            self.next_result_btn.config(state="disabled")
        else:
            self.prev_result_btn.config(state="normal" if self.result_index > 0 else "disabled")
            self.next_result_btn.config(state="normal" if self.result_index < total_count - 1 else "disabled")

        if not picture_candidates:
            self.result_current_full_image = None
            self.result_current_picture_url = ""
            self.result_image_label.config(text="暂无图片", image="", bg="#ffffff", fg="#64748b", cursor="arrow")
            self.result_image_label.image = None
            return

        self.result_current_full_image = None
        self.result_current_picture_url = ""
        self.result_image_label.config(text="图片加载中...", image="", bg="#ffffff", fg="#64748b", cursor="arrow")
        self.result_image_label.image = None
        target_index = self.result_index
        threading.Thread(
            target=self.load_result_image,
            args=(picture_candidates, target_index),
            daemon=True,
        ).start()

    def load_result_image(self, picture_candidates: list[str], target_index: int) -> None:
        try:
            image = None
            resolved_picture_url = ""

            for candidate_url in picture_candidates:
                cache_image = self.result_image_cache.get(candidate_url)
                if cache_image is not None:
                    image = cache_image
                    resolved_picture_url = candidate_url
                    break

                response = requests.get(candidate_url, timeout=10, impersonate="chrome110")
                if getattr(response, "status_code", 200) >= 400:
                    continue

                image_data = bytes(getattr(response, "content", b"") or b"")
                if not image_data:
                    continue

                try:
                    loaded = Image.open(BytesIO(image_data))
                    loaded.load()
                except Exception:
                    continue

                self.result_image_cache[candidate_url] = loaded
                image = loaded
                resolved_picture_url = candidate_url
                break

            if image is None:
                raise RuntimeError("图片资源不可用")

            resampling = getattr(Image, "Resampling", Image)
            lanczos = getattr(resampling, "LANCZOS", Image.LANCZOS)
            preview_image = image.copy()
            preview_image.thumbnail((300, 300), lanczos)
            photo = ImageTk.PhotoImage(preview_image)

            def update_ok() -> None:
                if not (self.result_window and self.result_window.winfo_exists()):
                    return
                if target_index != self.result_index:
                    return
                self.result_current_full_image = image.copy()
                self.result_current_picture_url = resolved_picture_url
                self.result_image_label.config(image=photo, text="", bg="#ffffff", cursor="hand2")
                self.result_image_label.image = photo

            self.root.after(0, update_ok)
        except Exception:
            def update_fail() -> None:
                if not (self.result_window and self.result_window.winfo_exists()):
                    return
                if target_index != self.result_index:
                    return
                self.result_current_full_image = None
                self.result_current_picture_url = ""
                self.result_image_label.config(text="图片加载失败", image="", bg="#ffffff", fg="#dc2626", cursor="arrow")
                self.result_image_label.image = None

            self.root.after(0, update_fail)

    def open_result_image_preview(self, _event=None) -> None:
        if self.result_current_full_image is None:
            return

        if self.image_preview_window and self.image_preview_window.winfo_exists():
            self.ensure_preview_window_front()
        else:
            self.image_preview_window = tk.Toplevel(self.root)
            self.image_preview_window.title(f"{APP_NAME} - 图片预览")
            self.image_preview_window.configure(bg="#0f172a")
            self.center_window(self.image_preview_window, 920, 680)

            title_text = "滚轮缩放 · 按住左键拖拽 · 双击复位"
            tk.Label(
                self.image_preview_window,
                text=title_text,
                font=("微软雅黑", 9),
                bg="#0f172a",
                fg="#cbd5e1",
            ).pack(fill="x", pady=(8, 6))

            self.image_preview_canvas = tk.Canvas(
                self.image_preview_window,
                bg="#111827",
                highlightthickness=0,
                cursor="fleur",
            )
            self.image_preview_canvas.pack(fill="both", expand=True, padx=10, pady=(0, 10))
            self.image_preview_canvas.bind("<Configure>", lambda _: self.render_preview_image())
            self.image_preview_canvas.bind("<MouseWheel>", self.on_preview_wheel)
            self.image_preview_canvas.bind("<Button-4>", self.on_preview_wheel)
            self.image_preview_canvas.bind("<Button-5>", self.on_preview_wheel)
            self.image_preview_canvas.bind("<ButtonPress-1>", self.on_preview_drag_start)
            self.image_preview_canvas.bind("<B1-Motion>", self.on_preview_drag_move)
            self.image_preview_canvas.bind("<Double-Button-1>", lambda _: self.reset_preview_view())
            self.image_preview_window.protocol("WM_DELETE_WINDOW", self.close_result_image_preview)
            self.ensure_preview_window_front()
            self.update_local_hotkey_binding()

        self.root.after(20, self.reset_preview_view)

    def ensure_preview_window_front(self) -> None:
        if not (self.image_preview_window and self.image_preview_window.winfo_exists()):
            return

        try:
            if self.result_window and self.result_window.winfo_exists():
                self.image_preview_window.transient(self.result_window)
            else:
                self.image_preview_window.transient(self.root)
        except Exception:
            pass

        try:
            self.image_preview_window.attributes("-topmost", True)
            if platform.system() == "Darwin":
                self.image_preview_window.after(
                    200, lambda current_window=self.image_preview_window: self._set_window_topmost(current_window, False)
                )
        except Exception:
            pass

        self.image_preview_window.lift()
        try:
            self.image_preview_window.focus_force()
        except Exception:
            pass

    def close_result_image_preview(self) -> None:
        if self.image_preview_window and self.image_preview_window.winfo_exists():
            self.image_preview_window.destroy()
        self.image_preview_window = None
        self.image_preview_canvas = None
        self.image_preview_state = {}

    def reset_preview_view(self) -> None:
        if self.result_current_full_image is None:
            return
        if not (self.image_preview_window and self.image_preview_window.winfo_exists()):
            return
        if not (self.image_preview_canvas and self.image_preview_canvas.winfo_exists()):
            return

        canvas_width = max(1, self.image_preview_canvas.winfo_width())
        canvas_height = max(1, self.image_preview_canvas.winfo_height())
        if canvas_width < 80 or canvas_height < 80:
            self.root.after(30, self.reset_preview_view)
            return
        image_width, image_height = self.result_current_full_image.size
        fit_scale = min(canvas_width / image_width, canvas_height / image_height, 1.0)
        fit_scale = max(fit_scale, 0.1)

        self.image_preview_state = {
            "image": self.result_current_full_image.copy(),
            "scale": fit_scale,
            "offset_x": canvas_width / 2,
            "offset_y": canvas_height / 2,
            "drag_last_x": None,
            "drag_last_y": None,
            "min_scale": max(fit_scale * 0.3, 0.05),
            "max_scale": max(8.0, fit_scale * 20),
            "photo": None,
        }
        self.render_preview_image()

    def render_preview_image(self) -> None:
        if not self.image_preview_state:
            return
        if not (self.image_preview_canvas and self.image_preview_canvas.winfo_exists()):
            return

        state = self.image_preview_state
        source_image = state.get("image")
        if source_image is None:
            return

        scale = max(0.01, float(state.get("scale", 1.0)))
        target_width = max(1, int(source_image.width * scale))
        target_height = max(1, int(source_image.height * scale))

        resampling = getattr(Image, "Resampling", Image)
        lanczos = getattr(resampling, "LANCZOS", Image.LANCZOS)
        resized = source_image.resize((target_width, target_height), lanczos)
        photo = ImageTk.PhotoImage(resized)
        state["photo"] = photo

        self.image_preview_canvas.delete("all")
        self.image_preview_canvas.create_image(
            float(state.get("offset_x", 0)),
            float(state.get("offset_y", 0)),
            image=photo,
            anchor="center",
        )

    def on_preview_wheel(self, event) -> None:
        if not self.image_preview_state:
            return
        if not (self.image_preview_canvas and self.image_preview_canvas.winfo_exists()):
            return

        if getattr(event, "num", None) == 4:
            zoom_in = True
        elif getattr(event, "num", None) == 5:
            zoom_in = False
        else:
            zoom_in = event.delta > 0

        state = self.image_preview_state
        old_scale = float(state.get("scale", 1.0))
        factor = 1.12 if zoom_in else 0.88
        new_scale = old_scale * factor
        min_scale = float(state.get("min_scale", 0.05))
        max_scale = float(state.get("max_scale", 8.0))
        new_scale = max(min_scale, min(max_scale, new_scale))
        if abs(new_scale - old_scale) < 1e-6:
            return

        pointer_x = float(event.x)
        pointer_y = float(event.y)
        offset_x = float(state.get("offset_x", 0))
        offset_y = float(state.get("offset_y", 0))

        image_local_x = (pointer_x - offset_x) / old_scale
        image_local_y = (pointer_y - offset_y) / old_scale
        state["scale"] = new_scale
        state["offset_x"] = pointer_x - image_local_x * new_scale
        state["offset_y"] = pointer_y - image_local_y * new_scale
        self.render_preview_image()

    def on_preview_drag_start(self, event) -> None:
        if not self.image_preview_state:
            return
        self.image_preview_state["drag_last_x"] = event.x
        self.image_preview_state["drag_last_y"] = event.y

    def on_preview_drag_move(self, event) -> None:
        if not self.image_preview_state:
            return
        last_x = self.image_preview_state.get("drag_last_x")
        last_y = self.image_preview_state.get("drag_last_y")
        if last_x is None or last_y is None:
            self.image_preview_state["drag_last_x"] = event.x
            self.image_preview_state["drag_last_y"] = event.y
            return

        delta_x = event.x - last_x
        delta_y = event.y - last_y
        self.image_preview_state["offset_x"] = float(self.image_preview_state.get("offset_x", 0)) + delta_x
        self.image_preview_state["offset_y"] = float(self.image_preview_state.get("offset_y", 0)) + delta_y
        self.image_preview_state["drag_last_x"] = event.x
        self.image_preview_state["drag_last_y"] = event.y
        self.render_preview_image()

    @staticmethod
    def generate_pkce_params() -> tuple[str, str, str]:
        verifier_bytes = os.urandom(32)
        code_verifier = base64.urlsafe_b64encode(verifier_bytes).decode("utf-8").rstrip("=")
        challenge_bytes = hashlib.sha256(code_verifier.encode("utf-8")).digest()
        code_challenge = base64.urlsafe_b64encode(challenge_bytes).decode("utf-8").rstrip("=")
        state = base64.urlsafe_b64encode(os.urandom(16)).decode("utf-8").rstrip("=")
        return code_verifier, code_challenge, state

    def show_login_window(self) -> None:
        if hasattr(self, "login_win") and self.login_win and self.login_win.winfo_exists():
            self.login_win.lift()
            return

        self.login_win = tk.Toplevel(self.root)
        self.login_win.title(f"{APP_NAME} 登录")
        if platform.system() != "Darwin":
            self.login_win.attributes("-topmost", True)
        self.login_win.configure(bg="#eaf2ff")
        self.login_win.resizable(True, True)
        self.center_window(self.login_win, 640, 500)
        min_login_w, min_login_h = self.scale_window_size(self.login_win, 600, 450)
        self.login_win.minsize(min_login_w, min_login_h)
        self.bring_window_front(self.login_win)

        self.login_session = requests.Session(impersonate="chrome110")
        self.auth_env = {}

        card_frame = tk.Frame(
            self.login_win,
            bg="#ffffff",
            bd=1,
            relief="solid",
            highlightthickness=1,
            highlightbackground="#dbeafe",
        )
        card_frame.pack(fill="both", expand=True, padx=20, pady=18)

        header_frame = tk.Frame(card_frame, bg="#ffffff")
        header_frame.pack(fill="x", padx=24, pady=(18, 8))
        tk.Label(
            header_frame,
            text="🔐 平台账号登录",
            font=("微软雅黑", 16, "bold"),
            bg="#ffffff",
            fg="#1e3a8a",
        ).pack(anchor="w")
        tk.Label(
            header_frame,
            text="登录后即可扫码查询",
            font=("微软雅黑", 9),
            bg="#ffffff",
            fg="#64748b",
        ).pack(anchor="w", pady=(4, 0))

        form_frame = tk.Frame(card_frame, bg="#ffffff")
        form_frame.pack(fill="x", padx=24, pady=(8, 6))
        form_frame.grid_columnconfigure(1, weight=1)

        label_style = {"font": ("微软雅黑", 10), "bg": "#ffffff", "fg": "#334155"}

        tk.Label(form_frame, text="账号", **label_style).grid(row=0, column=0, sticky="e", padx=(0, 12), pady=8)
        self.entry_user = ttk.Entry(form_frame, style="Login.TEntry")
        self.entry_user.grid(row=0, column=1, sticky="ew", pady=8, ipady=3)

        tk.Label(form_frame, text="密码", **label_style).grid(row=1, column=0, sticky="e", padx=(0, 12), pady=8)
        self.entry_pwd = ttk.Entry(form_frame, show="*", style="Login.TEntry")
        self.entry_pwd.grid(row=1, column=1, sticky="ew", pady=8, ipady=3)

        tk.Label(form_frame, text="验证码", **label_style).grid(row=2, column=0, sticky="e", padx=(0, 12), pady=8)
        cap_frame = tk.Frame(form_frame, bg="#ffffff")
        cap_frame.grid(row=2, column=1, sticky="ew", pady=8)
        cap_frame.grid_columnconfigure(0, weight=1)
        cap_frame.grid_columnconfigure(1, weight=0)

        self.entry_cap = ttk.Entry(cap_frame, style="Login.TEntry")
        self.entry_cap.grid(row=0, column=0, sticky="ew", padx=(0, 10), ipady=3)

        self.captcha_display_width = 140
        self.captcha_display_height = 42
        captcha_box = tk.Frame(
            cap_frame,
            bg="#f8fafc",
            bd=1,
            relief="solid",
            width=self.captcha_display_width,
            height=self.captcha_display_height,
        )
        captcha_box.grid(row=0, column=1, sticky="e")
        captcha_box.pack_propagate(False)
        self.cap_image_label = tk.Label(
            captcha_box,
            text="加载中...",
            font=("微软雅黑", 9),
            bg="#f8fafc",
            fg="#475569",
            cursor="hand2",
        )
        self.cap_image_label.pack(fill="both", expand=True)
        self.cap_image_label.bind("<Button-1>", lambda _: threading.Thread(target=self.fetch_captcha_and_env, daemon=True).start())

        self.remember_pwd_var = tk.BooleanVar(value=self.remember_password)
        remember_frame = tk.Frame(card_frame, bg="#ffffff")
        remember_frame.pack(fill="x", padx=24, pady=(2, 6))
        ttk.Checkbutton(
            remember_frame,
            text="记住密码",
            variable=self.remember_pwd_var,
            style="Login.TCheckbutton",
        ).pack(anchor="w")

        self.login_btn = ttk.Button(
            card_frame,
            text="登录",
            style="Login.TButton",
            command=self.submit_login_form,
        )
        self.login_btn.pack(fill="x", padx=24, pady=(6, 6))

        tk.Label(
            card_frame,
            text="验证码加载失败可点击验证码区域刷新",
            font=("微软雅黑", 8),
            bg="#ffffff",
            fg="#94a3b8",
        ).pack(anchor="w", padx=24, pady=(0, 14))

        if self.saved_username:
            self.entry_user.insert(0, self.saved_username)
        if self.remember_password and self.saved_password:
            self.entry_pwd.insert(0, self.saved_password)

        self.login_win.bind("<Return>", lambda _: self.submit_login_form())
        self.update_local_hotkey_binding()
        threading.Thread(target=self.fetch_captcha_and_env, daemon=True).start()

    def fetch_captcha_and_env(self) -> None:
        try:
            if not self.login_session:
                raise RuntimeError("登录会话未初始化")

            code_verifier, code_challenge, state = self.generate_pkce_params()
            self.auth_env["code_verifier"] = code_verifier

            return_url_params = {
                "client_id": "vuejs_code_client",
                "redirect_uri": "https://www.gds.org.cn/#/callback",
                "response_type": "code",
                "scope": "openid profile api1 offline_access",
                "state": state,
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
                "response_mode": "query",
            }

            raw_return_url = "/connect/authorize/callback?" + urllib.parse.urlencode(return_url_params)
            self.auth_env["return_url"] = raw_return_url
            login_url = "https://passport.gds.org.cn/Account/Login?ReturnUrl=" + urllib.parse.quote(raw_return_url, safe="")

            response_page = self.login_session.get(login_url, timeout=10)
            token_match = re.search(
                r'name="__RequestVerificationToken"\s+type="hidden"\s+value="([^"]+)"',
                response_page.text,
            )
            if not token_match:
                raise RuntimeError("无法获取登录校验参数，请稍后重试")
            self.auth_env["req_token"] = token_match.group(1)

            captcha_response = self.login_session.get(
                "https://passport.gds.org.cn/Account/Captcha",
                headers={"X-Requested-With": "XMLHttpRequest"},
                timeout=10,
            )
            cap_data = captcha_response.json()
            self.auth_env["cap_id"] = cap_data["Id"]
            img_base64 = cap_data["Base64"]

            if img_base64.startswith("data:image"):
                img_base64 = img_base64.split(",", 1)[1]

            image_bytes = base64.b64decode(img_base64)
            image = Image.open(BytesIO(image_bytes))
            resampling = getattr(Image, "Resampling", Image)
            lanczos = getattr(resampling, "LANCZOS", Image.LANCZOS)

            image_to_show = image.copy()
            max_width = max(40, self.captcha_display_width - 8)
            max_height = max(24, self.captcha_display_height - 8)
            image_to_show.thumbnail((max_width, max_height), lanczos)
            photo = ImageTk.PhotoImage(image_to_show)

            def update_ui() -> None:
                if not (self.login_win and self.login_win.winfo_exists()):
                    return
                self.cap_image_label.config(image=photo, text="", bg="#ffffff")
                self.cap_image_label.image = photo

            self.root.after(0, update_ui)

        except Exception as error:
            self.root.after(
                0,
                lambda: self.cap_image_label.config(text="加载失败\n点击重试", fg="#dc2626", image="", bg="#f8fafc"),
            )
            print(f"❌ 初始化登录环境失败: {error}")

    def submit_login_form(self) -> None:
        username = self.entry_user.get().strip()
        password = self.entry_pwd.get().strip()
        captcha = self.entry_cap.get().strip()

        if not username or not password or not captcha:
            messagebox.showwarning("提示", "请输入账号、密码和验证码。")
            return
        if "req_token" not in self.auth_env:
            messagebox.showwarning("提示", "登录环境尚未准备好，请稍后重试。")
            return

        self.pending_login_username = username
        self.pending_login_password = password
        self.pending_remember_password = bool(self.remember_pwd_var.get()) if hasattr(self, "remember_pwd_var") else False
        self.login_btn.config(state="disabled")
        threading.Thread(target=self.execute_auth_flow, args=(username, password, captcha), daemon=True).start()

    def execute_auth_flow(self, username: str, password: str, captcha: str) -> None:
        try:
            post_data = {
                "ReturnUrl": self.auth_env["return_url"],
                "Type": "account",
                "Button": "login",
                "data": "",
                "username": username,
                "password": password,
                "phone": "",
                "phoneVer": "",
                "barCode": "",
                "passwordBar": "",
                "codekey": self.auth_env["cap_id"],
                "verCode": captcha,
                "__RequestVerificationToken": self.auth_env["req_token"],
            }
            headers = {
                "X-Requested-With": "XMLHttpRequest",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            }

            login_response = self.login_session.post(
                "https://passport.gds.org.cn/Account/Login",
                data=post_data,
                headers=headers,
                timeout=10,
            )
            login_result = login_response.json()
            if login_result.get("Code") != 1:
                raise RuntimeError(login_result.get("Msg", "账号密码或验证码错误"))

            home_url = login_result["Data"]["homeurl"]
            if home_url.startswith("/"):
                home_url = "https://passport.gds.org.cn" + home_url
            auth_response = self.login_session.get(home_url, allow_redirects=False, timeout=10)

            redirect_location = auth_response.headers.get("Location") or auth_response.url
            parsed_url = urllib.parse.urlparse(redirect_location)
            query_params = urllib.parse.parse_qs(parsed_url.query)
            if "code" not in query_params and "?" in parsed_url.fragment:
                fragment_query = parsed_url.fragment.split("?", 1)[1]
                query_params = urllib.parse.parse_qs(fragment_query)
            if "code" not in query_params:
                raise RuntimeError(f"未能在回调地址中提取 code，跳转地址：{redirect_location}")
            auth_code = query_params["code"][0]

            token_payload = {
                "client_id": "vuejs_code_client",
                "code": auth_code,
                "redirect_uri": "https://www.gds.org.cn/#/callback",
                "code_verifier": self.auth_env["code_verifier"],
                "grant_type": "authorization_code",
            }
            token_response = self.login_session.post(
                "https://passport.gds.org.cn/connect/token",
                data=token_payload,
                timeout=10,
            )
            token_data = token_response.json()
            if "error" in token_data:
                raise RuntimeError(f"登录失败：{token_data.get('error')}")

            final_token = token_data.get("access_token", token_data.get("id_token"))
            if not final_token:
                raise RuntimeError("接口返回异常，请重新登录。")

            self.token = final_token
            self.save_config()
            self.root.after(0, self.on_login_success)

        except Exception as error:
            self.root.after(0, lambda msg=str(error): self.on_login_failed(msg))

    def on_login_success(self) -> None:
        previous_username = self.saved_username
        self.remember_password = self.pending_remember_password

        if self.remember_password:
            stored_ok = self.store_saved_password_secure(self.pending_login_username, self.pending_login_password)
            if stored_ok:
                if previous_username and previous_username != self.pending_login_username:
                    self.clear_saved_password_secure(previous_username)
                self.saved_username = self.pending_login_username
                self.saved_password = self.pending_login_password
            else:
                backend = self.get_password_storage_backend()
                backend_hint = "当前系统不支持" if backend == "unsupported" else "安全存储不可用"
                self.remember_password = False
                self.saved_username = ""
                self.saved_password = ""
                self.saved_password_encrypted = ""
                messagebox.showwarning("记住密码失败", f"无法启用“记住密码”，原因：{backend_hint}。")
        else:
            if previous_username:
                self.clear_saved_password_secure(previous_username)
            self.saved_username = ""
            self.saved_password = ""
            self.saved_password_encrypted = ""

        self.pending_login_username = ""
        self.pending_login_password = ""
        self.pending_remember_password = False
        self.save_config()
        self.update_status_labels()
        if self.login_win and self.login_win.winfo_exists():
            self.login_win.destroy()
        messagebox.showinfo("登录成功", "登录成功，开始扫描吧。")

    def on_login_failed(self, error_msg: str) -> None:
        messagebox.showerror("登录失败", error_msg)
        if self.login_win and self.login_win.winfo_exists():
            self.login_btn.config(state="normal")
            threading.Thread(target=self.fetch_captcha_and_env, daemon=True).start()

    def trigger_snip(self) -> None:
        if self.is_querying:
            if self.query_total > 0:
                self.last_summary_var.set(
                    f"最近一次扫描：正在查询 {self.query_done}/{self.query_total} 个条码，请稍候..."
                )
            else:
                self.last_summary_var.set("最近一次扫描：正在查询中，请稍候...")
            return
        if not self.is_snipping:
            self.is_snipping = True

    def check_trigger(self) -> None:
        if self.is_snipping:
            self.start_snip()
            self.is_snipping = False
        self.root.after(100, self.check_trigger)

    def start_snip(self) -> None:
        if platform.system() == "Darwin":
            self.start_macos_native_snip()
            return

        try:
            self.full_screen = ImageGrab.grab()
        except Exception as error:
            messagebox.showerror("截屏失败", f"无法获取屏幕截图：{error}")
            return

        self.snip_win = tk.Toplevel(self.root)
        self.snip_win.attributes("-fullscreen", True)
        if platform.system() != "Darwin":
            self.snip_win.attributes("-topmost", True)
        self.snip_win.config(cursor="cross")

        self.tk_img = ImageTk.PhotoImage(self.full_screen)
        self.canvas = tk.Canvas(self.snip_win, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.create_image(0, 0, anchor="nw", image=self.tk_img)

        self.rect = None
        self.start_x = None
        self.start_y = None

        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.snip_win.bind("<Escape>", lambda _: self.snip_win.destroy())

    def start_macos_native_snip(self) -> None:
        temp_path = ""
        hidden_windows: list[tuple[tk.Toplevel, str]] = []
        try:
            hidden_windows = self.prepare_macos_capture_windows()
            fd, temp_path = tempfile.mkstemp(suffix=".png")
            os.close(fd)
            Path(temp_path).unlink(missing_ok=True)
            self.last_summary_var.set("最近一次扫描：正在等待 macOS 截图框选...")
            self.root.update_idletasks()
            screencapture_bin = MACOS_SCREEN_CAPTURE_BIN if Path(MACOS_SCREEN_CAPTURE_BIN).exists() else "screencapture"
            result = subprocess.run(
                [screencapture_bin, "-i", "-x", temp_path],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                self.show_macos_capture_error(result)
                return
            if not Path(temp_path).exists() or Path(temp_path).stat().st_size <= 0:
                return
            with Image.open(temp_path) as image:
                cropped_img = image.convert("RGB").copy()
            if cropped_img.width <= 10 or cropped_img.height <= 10:
                return
            self.process_image(cropped_img)
        except Exception as error:
            messagebox.showerror("截屏失败", f"无法获取屏幕截图：{error}\n\n{MACOS_SETUP_NOTICE}")
        finally:
            if hidden_windows:
                self.restore_macos_capture_windows(hidden_windows)
            if temp_path:
                try:
                    Path(temp_path).unlink(missing_ok=True)
                except Exception:
                    pass

    def show_macos_capture_error(self, result: subprocess.CompletedProcess) -> None:
        stderr = (result.stderr or "").strip()
        if not stderr:
            self.last_summary_var.set("最近一次扫描：截屏已取消；若未主动取消，请开启 macOS 屏幕录制权限。")
            return
        debug_console("macOS 截图失败", {"returncode": result.returncode, "stderr": stderr})
        self.last_summary_var.set("最近一次扫描：截屏未完成，请确认已允许“屏幕录制”权限。")
        messagebox.showwarning(
            "截屏未完成",
            "macOS 系统截图没有完成。如果你刚才按 ESC 取消，可以忽略此提示；"
            f"如果没有取消，请先确认“屏幕录制”权限已授予当前应用。\n\n{MACOS_SETUP_NOTICE}",
        )

    def on_press(self, event) -> None:
        self.start_x = event.x
        self.start_y = event.y
        self.rect = self.canvas.create_rectangle(
            self.start_x,
            self.start_y,
            self.start_x,
            self.start_y,
            outline="#ef4444",
            width=2,
        )

    def on_drag(self, event) -> None:
        if self.rect is not None:
            self.canvas.coords(self.rect, self.start_x, self.start_y, event.x, event.y)

    def on_release(self, event) -> None:
        end_x, end_y = event.x, event.y
        self.snip_win.destroy()

        x1 = min(self.start_x, end_x)
        y1 = min(self.start_y, end_y)
        x2 = max(self.start_x, end_x)
        y2 = max(self.start_y, end_y)

        if x2 - x1 <= 10 or y2 - y1 <= 10:
            return

        cropped_img = self.full_screen.crop((x1, y1, x2, y2))
        self.process_image(cropped_img)

    @staticmethod
    def is_valid_gtin_checksum(code: str) -> bool:
        if not code.isdigit() or len(code) not in (13, 14):
            return False

        digits = [int(ch) for ch in code]
        check_digit = digits[-1]
        body_digits = digits[:-1]
        total = 0
        for index, value in enumerate(reversed(body_digits), start=1):
            total += value * (3 if index % 2 == 1 else 1)
        expected_check_digit = (10 - (total % 10)) % 10
        return expected_check_digit == check_digit

    @staticmethod
    def normalize_search_barcode(raw_code: str) -> str:
        digits = re.sub(r"\D", "", str(raw_code or ""))
        if len(digits) == 13 and digits.startswith("69") and BarcodeScannerApp.is_valid_gtin_checksum(digits):
            return "0" + digits
        if len(digits) == 14 and digits.startswith("069") and BarcodeScannerApp.is_valid_gtin_checksum(digits):
            return digits
        return ""

    @staticmethod
    def is_same_detected_box(existing_box: tuple[int, int, int, int], new_box: tuple[int, int, int, int]) -> bool:
        ex, ey, ew, eh = existing_box
        nx, ny, nw, nh = new_box

        ex2, ey2 = ex + ew, ey + eh
        nx2, ny2 = nx + nw, ny + nh

        inter_w = max(0, min(ex2, nx2) - max(ex, nx))
        inter_h = max(0, min(ey2, ny2) - max(ey, ny))
        inter_area = inter_w * inter_h
        union_area = max(1, ew * eh + nw * nh - inter_area)
        iou = inter_area / union_area
        if iou >= 0.36:
            return True

        ex_center_x = ex + ew / 2
        ex_center_y = ey + eh / 2
        nx_center_x = nx + nw / 2
        nx_center_y = ny + nh / 2
        center_distance = ((ex_center_x - nx_center_x) ** 2 + (ex_center_y - nx_center_y) ** 2) ** 0.5
        size_ref = max(14.0, (min(ew, eh) + min(nw, nh)) / 2)
        if center_distance > size_ref * 0.52:
            return False

        width_gap = abs(ew - nw)
        height_gap = abs(eh - nh)
        return width_gap <= max(14, size_ref * 0.9) and height_gap <= max(14, size_ref * 0.9)

    def detect_search_codes(self, pil_image: Image.Image) -> tuple[int, list[str]]:
        base_gray = ImageOps.grayscale(pil_image.convert("RGB"))

        variant_inputs: list[tuple[Image.Image, float, int, int, bool]] = []

        def add_variant(
            image_obj: Image.Image,
            scale: float = 1.0,
            offset_x: int = 0,
            offset_y: int = 0,
            iterative_mask: bool = False,
        ) -> None:
            variant_inputs.append((image_obj, scale, offset_x, offset_y, iterative_mask))

        add_variant(base_gray, 1.0, 0, 0, True)
        add_variant(ImageOps.autocontrast(base_gray), 1.0, 0, 0, True)
        add_variant(ImageEnhance.Contrast(base_gray).enhance(1.8), 1.0, 0, 0, False)
        add_variant(base_gray.filter(ImageFilter.SHARPEN), 1.0, 0, 0, False)

        for threshold in (112, 128, 144):
            binary = base_gray.point(lambda pixel, t=threshold: 255 if pixel > t else 0, mode="L")
            add_variant(binary, 1.0, 0, 0, False)

        resampling = getattr(Image, "Resampling", Image)
        lanczos = getattr(resampling, "LANCZOS", Image.LANCZOS)
        for scale in (1.6, 2.1):
            resized = base_gray.resize(
                (max(1, int(base_gray.width * scale)), max(1, int(base_gray.height * scale))),
                lanczos,
            )
            add_variant(resized, scale, 0, 0, True)
            add_variant(ImageOps.autocontrast(resized), scale, 0, 0, True)

        total_symbols = 0
        detected_clusters_by_code: dict[str, list[dict]] = {}
        seen_codes_without_box: dict[str, int] = {}

        def current_detected_count() -> int:
            count = sum(len(clusters) for clusters in detected_clusters_by_code.values())
            if count <= 0:
                count = len([code for code, hits in seen_codes_without_box.items() if hits > 0])
            return count

        def register_decoded_symbol(barcode_data, scale: float, offset_x: int, offset_y: int) -> None:
            raw_code = barcode_data.data.decode("utf-8", errors="ignore")
            normalized_code = self.normalize_search_barcode(raw_code)
            if not normalized_code:
                return

            rect = getattr(barcode_data, "rect", None)
            if rect is None:
                seen_codes_without_box[normalized_code] = seen_codes_without_box.get(normalized_code, 0) + 1
                return

            left = int(offset_x + getattr(rect, "left", 0) / max(scale, 1e-6))
            top = int(offset_y + getattr(rect, "top", 0) / max(scale, 1e-6))
            width = max(1, int(getattr(rect, "width", 0) / max(scale, 1e-6)))
            height = max(1, int(getattr(rect, "height", 0) / max(scale, 1e-6)))
            current_box = (left, top, width, height)

            clusters = detected_clusters_by_code.setdefault(normalized_code, [])
            for cluster in clusters:
                cluster_box = cluster["box"]
                if not self.is_same_detected_box(cluster_box, current_box):
                    continue

                previous_hits = int(cluster["hits"])
                updated_hits = previous_hits + 1
                cluster["hits"] = updated_hits
                cluster["box"] = (
                    int((cluster_box[0] * previous_hits + current_box[0]) / updated_hits),
                    int((cluster_box[1] * previous_hits + current_box[1]) / updated_hits),
                    int((cluster_box[2] * previous_hits + current_box[2]) / updated_hits),
                    int((cluster_box[3] * previous_hits + current_box[3]) / updated_hits),
                )
                return

            clusters.append({"box": current_box, "hits": 1})

        def decode_variant(image_input: Image.Image, scale: float, offset_x: int, offset_y: int, iterative_mask: bool) -> None:
            nonlocal total_symbols

            if not iterative_mask:
                try:
                    decoded_list = decode(image_input)
                except Exception:
                    return
                total_symbols += len(decoded_list)
                for barcode_data in decoded_list:
                    register_decoded_symbol(barcode_data, scale, offset_x, offset_y)
                return

            working_image = image_input.convert("L")
            for _ in range(10):
                try:
                    decoded_list = decode(working_image)
                except Exception:
                    break
                if not decoded_list:
                    break

                total_symbols += len(decoded_list)
                draw = ImageDraw.Draw(working_image)
                masked_any = False

                for barcode_data in decoded_list:
                    register_decoded_symbol(barcode_data, scale, offset_x, offset_y)

                    rect = getattr(barcode_data, "rect", None)
                    if rect is None:
                        continue
                    left = max(0, int(getattr(rect, "left", 0)))
                    top = max(0, int(getattr(rect, "top", 0)))
                    width = max(1, int(getattr(rect, "width", 0)))
                    height = max(1, int(getattr(rect, "height", 0)))
                    margin = max(8, int(min(width, height) * 0.25))
                    right = min(working_image.width, left + width + margin)
                    bottom = min(working_image.height, top + height + margin)
                    left = max(0, left - margin)
                    top = max(0, top - margin)
                    draw.rectangle((left, top, right, bottom), fill=255)
                    masked_any = True

                if not masked_any:
                    break

        for image_input, scale, offset_x, offset_y, iterative_mask in variant_inputs:
            decode_variant(image_input, scale, offset_x, offset_y, iterative_mask)

        if current_detected_count() <= 1:
            width, height = base_gray.size
            fixed_regions = []
            half_width = max(1, width // 2)
            half_height = max(1, height // 2)
            third_width = max(1, width // 3)

            fixed_regions.extend(
                [
                    (0, 0, half_width, height),
                    (half_width, 0, width, height),
                    (0, 0, width, half_height),
                    (0, half_height, width, height),
                    (0, 0, third_width, height),
                    (third_width, 0, min(width, third_width * 2), height),
                    (min(width, third_width * 2), 0, width, height),
                ]
            )
            for left, top, right, bottom in fixed_regions:
                if right - left < 120 or bottom - top < 80:
                    continue
                region_tile = base_gray.crop((left, top, right, bottom))
                decode_variant(region_tile, 1.0, left, top, True)
                decode_variant(ImageOps.autocontrast(region_tile), 1.0, left, top, True)

            tile_width = max(220, int(width * 0.68))
            tile_height = max(140, int(height * 0.68))
            tile_width = min(width, tile_width)
            tile_height = min(height, tile_height)
            step_x = max(80, int(tile_width * 0.48))
            step_y = max(80, int(tile_height * 0.48))

            y = 0
            while y < height:
                bottom = min(height, y + tile_height)
                x = 0
                while x < width:
                    right = min(width, x + tile_width)
                    if right - x >= 120 and bottom - y >= 80:
                        tile = base_gray.crop((x, y, right, bottom))
                        tile_variants = (
                            tile,
                            ImageOps.autocontrast(tile),
                            ImageEnhance.Contrast(tile).enhance(2.0),
                        )
                        for tile_variant in tile_variants:
                            decode_variant(tile_variant, 1.0, x, y, True)

                    if right >= width:
                        break
                    x += step_x
                if bottom >= height:
                    break
                y += step_y

            if current_detected_count() <= 1:
                fine_tile_width = max(140, int(width * 0.45))
                fine_tile_height = max(100, int(height * 0.45))
                fine_tile_width = min(width, fine_tile_width)
                fine_tile_height = min(height, fine_tile_height)
                fine_step_x = max(60, int(fine_tile_width * 0.32))
                fine_step_y = max(60, int(fine_tile_height * 0.32))

                top = 0
                while top < height:
                    bottom = min(height, top + fine_tile_height)
                    left = 0
                    while left < width:
                        right = min(width, left + fine_tile_width)
                        if right - left >= 100 and bottom - top >= 70:
                            fine_tile = base_gray.crop((left, top, right, bottom))
                            decode_variant(fine_tile, 1.0, left, top, True)
                            decode_variant(ImageOps.autocontrast(fine_tile), 1.0, left, top, True)
                            decode_variant(ImageEnhance.Contrast(fine_tile).enhance(2.2), 1.0, left, top, True)
                        if right >= width:
                            break
                        left += fine_step_x
                    if bottom >= height:
                        break
                    top += fine_step_y

        search_codes: list[str] = []
        seen_search_codes: set[str] = set()

        def add_search_code(normalized_code: str) -> None:
            if normalized_code in seen_search_codes:
                return
            seen_search_codes.add(normalized_code)
            search_codes.append(normalized_code)

        for normalized_code, clusters in detected_clusters_by_code.items():
            if not clusters:
                continue
            add_search_code(normalized_code)

        for normalized_code, hits in seen_codes_without_box.items():
            if hits <= 0 or normalized_code in detected_clusters_by_code:
                continue
            add_search_code(normalized_code)

        return total_symbols, search_codes

    def process_image(self, pil_image: Image.Image) -> None:
        if self.is_querying:
            if self.query_total > 0:
                self.last_summary_var.set(f"最近一次扫描：正在查询 {self.query_done}/{self.query_total} 个条码，请稍候...")
            else:
                self.last_summary_var.set("最近一次扫描：正在查询中，请稍候...")
            return
        if not self.token:
            messagebox.showwarning("提示", "请先登录后再扫描。")
            return
        if self.is_token_expired(self.token):
            self.mark_token_expired("登录已过期，请重新登录后再扫描。")
            return

        if pil_image.width <= 10 or pil_image.height <= 10:
            messagebox.showwarning("识别失败", "截图内容异常，请重新框选。")
            return

        detected_total, search_codes = self.detect_search_codes(pil_image)
        debug_console(
            "条码识别完成",
            {
                "detected_total": detected_total,
                "query_count": len(search_codes),
                "codes": search_codes,
            },
        )
        if detected_total <= 0:
            messagebox.showwarning("识别失败", "未在截图区域发现条形码，请重新框选。")
            return

        if not search_codes:
            messagebox.showwarning("识别失败", "截图中未发现有效的 69 码。")
            return

        self.scan_session_counter += 1
        session_id = self.scan_session_counter
        self.active_scan_session_id = session_id
        self.is_querying = True
        self.query_total = len(search_codes)
        self.query_done = 0
        self.last_summary_var.set(f"最近一次扫描：正在查询 0/{self.query_total} 个条码...")
        threading.Thread(target=self.query_multiple_products, args=(search_codes, session_id), daemon=True).start()

    def is_active_scan_session(self, session_id: int | None) -> bool:
        return session_id is not None and session_id == self.active_scan_session_id

    def update_query_progress(self, done_count: int, total_count: int, session_id: int | None = None) -> None:
        if not self.is_active_scan_session(session_id):
            return
        if not self.is_querying:
            return
        self.query_done = max(0, done_count)
        self.query_total = max(0, total_count)
        if self.query_total <= 0 or self.query_done >= self.query_total:
            return
        self.last_summary_var.set(f"最近一次扫描：正在查询 {self.query_done}/{self.query_total} 个条码...")

    def abort_query_due_auth(self, reason: str, session_id: int | None = None) -> None:
        if not self.is_active_scan_session(session_id):
            return
        self.is_querying = False
        self.active_scan_session_id = None
        self.query_done = 0
        self.query_total = 0
        self.mark_token_expired(reason)

    def query_multiple_products(self, search_codes: list[str], session_id: int) -> None:
        error_texts = []
        new_records = []
        success_products = []
        ordered_barcodes: list[str] = []
        seen_barcodes: set[str] = set()
        for barcode in search_codes:
            if barcode in seen_barcodes:
                continue
            seen_barcodes.add(barcode)
            ordered_barcodes.append(barcode)
        total_count = len(ordered_barcodes)
        done_count = 0
        debug_console(
            "开始批量查询",
            {
                "count": total_count,
                "unique_count": len(ordered_barcodes),
                "codes": search_codes,
                "deduped_codes": ordered_barcodes,
            },
        )

        api_headers = {
            "Authorization": f"Bearer {self.token}",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Connection": "keep-alive",
        }

        def fetch_product_item(barcode: str) -> dict:
            params = {"PageSize": 30, "PageIndex": 1, "SearchItem": barcode}
            max_attempts = 3
            last_error = "未知错误"
            for attempt in range(1, max_attempts + 1):
                try:
                    debug_console("请求商品接口", {"barcode": barcode, "params": params, "attempt": attempt})
                    response = requests.get(
                        API_URL,
                        headers=api_headers,
                        params=params,
                        timeout=10,
                        impersonate="chrome110",
                    )
                    status_code = getattr(response, "status_code", 200)
                    debug_console(
                        "接口HTTP返回",
                        {"barcode": barcode, "status_code": status_code, "attempt": attempt},
                    )
                    if status_code in (401, 403):
                        debug_console("接口鉴权失败", {"barcode": barcode, "status_code": status_code})
                        return {"auth_expired": True}
                    if status_code >= 500:
                        last_error = f"HTTP {status_code}"
                        if attempt < max_attempts:
                            debug_console("服务端异常重试", {"barcode": barcode, "status_code": status_code, "attempt": attempt})
                            continue
                        return {"error": last_error}

                    try:
                        data = response.json()
                    except Exception as parse_error:
                        last_error = f"响应解析失败: {parse_error}"
                        debug_console(
                            "响应解析失败",
                            {"barcode": barcode, "error": str(parse_error), "attempt": attempt},
                        )
                        if attempt < max_attempts:
                            continue
                        return {"error": last_error}

                    items = []
                    if isinstance(data, dict):
                        data_body = data.get("Data")
                        if isinstance(data_body, dict):
                            data_items = data_body.get("Items")
                            if isinstance(data_items, list):
                                items = data_items
                    debug_console(
                        "接口业务返回",
                        {
                            "barcode": barcode,
                            "Code": data.get("Code") if isinstance(data, dict) else None,
                            "Msg": data.get("Msg") if isinstance(data, dict) else None,
                            "item_count": len(items),
                            "first_item_gtin": (items[0].get("gtin") if items and isinstance(items[0], dict) else None),
                            "attempt": attempt,
                        },
                    )
                    if self.is_token_invalid_response(data):
                        return {"auth_expired": True}

                    if isinstance(data, dict) and data.get("Code") == 1 and items:
                        return {"item": items[0]}

                    return {"not_found": True}
                except Exception as error:
                    last_error = str(error)
                    debug_console("条码请求异常", {"barcode": barcode, "error": last_error, "attempt": attempt})
                    if attempt < max_attempts:
                        continue
                    return {"error": last_error}

            return {"error": last_error}

        debug_console("顺序查询模式", {"barcodes": ordered_barcodes})
        for barcode in ordered_barcodes:
            if not self.is_active_scan_session(session_id):
                debug_console("忽略过期扫描会话", {"session_id": session_id, "barcode": barcode})
                return
            query_result = fetch_product_item(barcode)
            if query_result.get("auth_expired"):
                self.root.after(
                    0,
                    lambda current_session_id=session_id: self.abort_query_due_auth(
                        "登录已失效或过期，请重新登录后再试。", current_session_id
                    ),
                )
                return

            if query_result.get("item") is not None:
                item = query_result["item"]
                record = HistoryRecord.from_item(item, barcode)
                product_data = {
                    "barcode": barcode,
                    "product_name": record.product_name,
                    "regulated_name": normalize_optional_text(item.get("RegulatedProductName")),
                    "brand": record.brand,
                    "firm_name": record.firm_name,
                    "specification": record.specification,
                    "category": record.category,
                    "description": normalize_optional_text(item.get("description")),
                    "picture_url": record.picture_url,
                }
                new_records.append(record)
                success_products.append(product_data)

                done_count += 1
                self.root.after(
                    0,
                    lambda rec=record, prod=product_data, current_session_id=session_id: self.on_query_partial_success(
                        [rec], [prod], current_session_id
                    ),
                )
                self.root.after(
                    0,
                    lambda current_done=done_count, total=total_count, current_session_id=session_id: self.update_query_progress(
                        current_done, total, current_session_id
                    ),
                )
            else:
                if query_result.get("not_found"):
                    reason = "查无相关商品信息"
                else:
                    reason = query_result.get("error") or "请求失败"
                error_texts.append(f"条码 {barcode}：{reason}")
                debug_console("条码查询失败", {"barcode": barcode, "reason": reason})

                done_count += 1
                self.root.after(
                    0,
                    lambda current_done=done_count, total=total_count, current_session_id=session_id: self.update_query_progress(
                        current_done, total, current_session_id
                    ),
                )

        self.root.after(
            0,
            lambda current_session_id=session_id: self.on_query_finished(
                error_texts,
                new_records,
                success_products,
                current_session_id,
            ),
        )

    def on_query_finished(
        self,
        error_texts: list[str],
        new_records: list[HistoryRecord],
        success_products: list[dict],
        session_id: int | None = None,
    ) -> None:
        if not self.is_active_scan_session(session_id):
            return
        self.is_querying = False
        self.active_scan_session_id = None
        self.query_done = 0
        self.query_total = 0
        debug_console(
            "批量查询结束",
            {
                "success_count": len(success_products),
                "failure_count": len(error_texts),
                "success_barcodes": [str(item.get("barcode", "")) for item in success_products],
                "failures": error_texts,
            },
        )

        if success_products:
            success_count = len(success_products)
            failure_count = len(error_texts)
            if failure_count > 0:
                self.last_summary_var.set(
                    f"最近一次扫描：成功 {success_count} 条，失败 {failure_count} 条，最新条码 {success_products[-1].get('barcode', '-')}"
                )
            else:
                self.last_summary_var.set(
                    f"最近一次扫描：成功 {success_count} 条，最新条码 {success_products[-1].get('barcode', '-')}"
                )
        else:
            failure_count = len(error_texts)
            if failure_count > 0:
                self.last_summary_var.set(f"最近一次扫描：未查询到有效商品信息（失败 {failure_count} 条）")
            else:
                self.last_summary_var.set("最近一次扫描：未查询到有效商品信息")

    def on_query_partial_success(
        self,
        partial_records: list[HistoryRecord],
        partial_products: list[dict],
        session_id: int | None = None,
    ) -> None:
        if not self.is_active_scan_session(session_id):
            return
        if partial_records:
            self.add_history_records(partial_records)

        if not partial_products:
            return

        if self.result_window and self.result_window.winfo_exists():
            old_len = len(self.result_products)
            self.result_products.extend(partial_products)
            self.result_index = old_len
            self.render_current_result()
            self.bring_window_front(self.result_window)
            self.ensure_preview_window_front()
            return

        self.show_product_detail_window(partial_products)
        if self.result_window and self.result_window.winfo_exists():
            self.bring_window_front(self.result_window)
            self.ensure_preview_window_front()

    def quit_application(self) -> None:
        try:
            if self.hotkey_handler is not None:
                remove_hotkey(self.hotkey_handler)
        except Exception:
            pass
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    BarcodeScannerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
