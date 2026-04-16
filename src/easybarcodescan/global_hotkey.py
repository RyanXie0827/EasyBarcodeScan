import platform
import threading
from dataclasses import dataclass


class HotkeyError(RuntimeError):
    pass


class HotkeyPermissionError(HotkeyError):
    pass


def get_default_hotkey() -> str:
    if platform.system() == "Darwin":
        return "ctrl+shift+a"
    return "ctrl+alt+a"


def get_hotkey_example() -> str:
    if platform.system() == "Darwin":
        return "ctrl+shift+a"
    return "ctrl+shift+a"


def add_hotkey(hotkey: str, callback):
    if platform.system() == "Darwin":
        listener = _MacHotkeyListener(hotkey, callback)
        listener.start()
        return listener

    try:
        import keyboard
    except Exception as error:
        raise HotkeyError(f"无法加载快捷键模块：{error}") from error

    try:
        return keyboard.add_hotkey(hotkey, callback)
    except Exception as error:
        raise HotkeyError(str(error)) from error


def remove_hotkey(handle) -> None:
    if handle is None:
        return

    if isinstance(handle, _MacHotkeyListener):
        handle.stop()
        return

    try:
        import keyboard
    except Exception:
        return

    try:
        keyboard.remove_hotkey(handle)
    except Exception:
        pass


def _is_macos_accessibility_trusted(prompt: bool = False) -> bool:
    try:
        import Quartz
    except Exception:
        return True

    if prompt and hasattr(Quartz, "AXIsProcessTrustedWithOptions"):
        options = None
        prompt_key = getattr(Quartz, "kAXTrustedCheckOptionPrompt", None)
        if prompt_key is not None:
            options = {prompt_key: True}
        try:
            if options is not None:
                return bool(Quartz.AXIsProcessTrustedWithOptions(options))
        except Exception:
            pass

    if hasattr(Quartz, "AXIsProcessTrusted"):
        try:
            return bool(Quartz.AXIsProcessTrusted())
        except Exception:
            pass

    return True


@dataclass(frozen=True)
class _ParsedMacHotkey:
    key_code: int
    modifier_mask: int


class _MacHotkeyListener:
    _MODIFIER_ALIASES = {
        "ctrl": "control",
        "control": "control",
        "alt": "option",
        "option": "option",
        "shift": "shift",
        "cmd": "command",
        "command": "command",
    }

    _KEY_CODES = {
        "a": 0,
        "s": 1,
        "d": 2,
        "f": 3,
        "h": 4,
        "g": 5,
        "z": 6,
        "x": 7,
        "c": 8,
        "v": 9,
        "b": 11,
        "q": 12,
        "w": 13,
        "e": 14,
        "r": 15,
        "y": 16,
        "t": 17,
        "1": 18,
        "2": 19,
        "3": 20,
        "4": 21,
        "6": 22,
        "5": 23,
        "9": 25,
        "7": 26,
        "8": 28,
        "0": 29,
        "o": 31,
        "u": 32,
        "i": 34,
        "p": 35,
        "enter": 36,
        "return": 36,
        "l": 37,
        "j": 38,
        "k": 40,
        "n": 45,
        "m": 46,
        "tab": 48,
        "space": 49,
        "backspace": 51,
        "delete": 51,
        "escape": 53,
        "esc": 53,
        "left": 123,
        "right": 124,
        "down": 125,
        "up": 126,
        "f1": 122,
        "f2": 120,
        "f3": 99,
        "f4": 118,
        "f5": 96,
        "f6": 97,
        "f7": 98,
        "f8": 100,
        "f9": 101,
        "f10": 109,
        "f11": 103,
        "f12": 111,
        "f13": 105,
        "f14": 107,
        "f15": 113,
        "f16": 106,
        "f17": 64,
        "f18": 79,
        "f19": 80,
    }

    def __init__(self, hotkey: str, callback):
        self._callback = callback
        self._parsed = self._parse_hotkey(hotkey)
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._ready = threading.Event()
        self._run_loop_ref = None
        self._tap = None
        self._source = None
        self._error = None

    def start(self) -> None:
        self._thread.start()
        self._ready.wait(timeout=2)
        if self._error:
            raise self._error
        if self._tap is None:
            raise HotkeyError("无法启动 macOS 全局快捷键监听。")

    def stop(self) -> None:
        try:
            import Quartz
        except Exception:
            return

        if self._run_loop_ref is not None:
            Quartz.CFRunLoopStop(self._run_loop_ref)
        if self._tap is not None:
            Quartz.CFMachPortInvalidate(self._tap)
        self._tap = None
        self._source = None
        self._run_loop_ref = None

    def _run_loop(self) -> None:
        try:
            import Quartz
        except Exception as error:
            self._error = HotkeyError(f"无法加载 macOS 快捷键依赖：{error}")
            self._ready.set()
            return

        if not _is_macos_accessibility_trusted(prompt=True):
            self._error = HotkeyPermissionError(
                "无法拦截 macOS 全局快捷键，请先授予“辅助功能”权限，然后完全退出并重新打开程序。"
            )
            self._ready.set()
            return

        if hasattr(Quartz, "CGPreflightListenEventAccess") and not Quartz.CGPreflightListenEventAccess():
            if hasattr(Quartz, "CGRequestListenEventAccess"):
                try:
                    Quartz.CGRequestListenEventAccess()
                except Exception:
                    pass

        event_mask = Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown)
        self._tap = Quartz.CGEventTapCreate(
            Quartz.kCGSessionEventTap,
            Quartz.kCGHeadInsertEventTap,
            getattr(Quartz, "kCGEventTapOptionDefault", 0),
            event_mask,
            self._handle_event,
            None,
        )
        if self._tap is None:
            self._error = HotkeyPermissionError(
                "无法创建 macOS 全局快捷键监听，请确认已授予“输入监控”和“辅助功能”权限。"
            )
            self._ready.set()
            return

        self._source = Quartz.CFMachPortCreateRunLoopSource(None, self._tap, 0)
        self._run_loop_ref = Quartz.CFRunLoopGetCurrent()
        Quartz.CFRunLoopAddSource(self._run_loop_ref, self._source, Quartz.kCFRunLoopCommonModes)
        Quartz.CGEventTapEnable(self._tap, True)
        self._ready.set()
        Quartz.CFRunLoopRun()

    def _handle_event(self, _proxy, event_type, event, _refcon):
        import Quartz

        if event_type in (Quartz.kCGEventTapDisabledByTimeout, Quartz.kCGEventTapDisabledByUserInput):
            if self._tap is not None:
                Quartz.CGEventTapEnable(self._tap, True)
            return event

        if event_type != Quartz.kCGEventKeyDown:
            return event

        try:
            is_auto_repeat = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventAutorepeat)
            if is_auto_repeat:
                return None
        except Exception:
            pass

        key_code = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode)
        flags = Quartz.CGEventGetFlags(event)
        relevant_flags = (
            Quartz.kCGEventFlagMaskControl
            | Quartz.kCGEventFlagMaskAlternate
            | Quartz.kCGEventFlagMaskShift
            | Quartz.kCGEventFlagMaskCommand
        )
        if key_code == self._parsed.key_code and (flags & relevant_flags) == self._parsed.modifier_mask:
            self._callback()
            return None
        return event

    @classmethod
    def _parse_hotkey(cls, hotkey: str) -> _ParsedMacHotkey:
        try:
            import Quartz
        except Exception as error:
            raise HotkeyError(f"无法加载 macOS 快捷键依赖：{error}") from error

        tokens = [part.strip().lower() for part in str(hotkey).split("+") if part.strip()]
        if not tokens:
            raise HotkeyError("快捷键不能为空。")

        key_token = tokens[-1]
        modifier_tokens = tokens[:-1]
        if key_token not in cls._KEY_CODES:
            raise HotkeyError("macOS 快捷键仅支持字母、数字、F1-F19、方向键、ESC、TAB、ENTER、SPACE、DELETE。")

        modifier_mask = 0
        modifier_flags = {
            "control": Quartz.kCGEventFlagMaskControl,
            "option": Quartz.kCGEventFlagMaskAlternate,
            "shift": Quartz.kCGEventFlagMaskShift,
            "command": Quartz.kCGEventFlagMaskCommand,
        }
        seen_modifiers: set[str] = set()
        for token in modifier_tokens:
            modifier_name = cls._MODIFIER_ALIASES.get(token)
            if modifier_name is None:
                raise HotkeyError(f"macOS 不支持修饰键：{token}")
            if modifier_name in seen_modifiers:
                continue
            seen_modifiers.add(modifier_name)
            modifier_mask |= modifier_flags[modifier_name]

        return _ParsedMacHotkey(cls._KEY_CODES[key_token], modifier_mask)
