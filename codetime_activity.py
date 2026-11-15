"""Cross-platform activity detection for CodeTime."""

import csv
import ctypes
import platform
import re
import subprocess


SUPPORTED_EDITORS = {
    "ubuntu_or_linux": ["code", "codium", "pycharm", "subl"],
    "windows": ["Code.exe", "pycharm64.exe", "sublime_text.exe"],
}


def get_operating_system():
    """Return the operating system running CodeTime."""
    system = platform.system()

    if system == "Linux":
        return "ubuntu_or_linux"

    if system == "Windows":
        return "windows"

    return "unsupported"


def get_idle_seconds():
    """Return seconds since the last user input, or None if unavailable."""
    operating_system = get_operating_system()

    if operating_system == "ubuntu_or_linux":
        try:
            result = subprocess.run(
                [
                    "gdbus",
                    "call",
                    "--session",
                    "--dest",
                    "org.gnome.Mutter.IdleMonitor",
                    "--object-path",
                    "/org/gnome/Mutter/IdleMonitor/Core",
                    "--method",
                    "org.gnome.Mutter.IdleMonitor.GetIdletime",
                ],
                capture_output=True,
                text=True,
                check=True,
                timeout=3,
            )

            match = re.search(r"uint64\s+(\d+)", result.stdout)

            if match:
                return int(match.group(1)) / 1000

        except (OSError, subprocess.SubprocessError):
            return None

        return None

    if operating_system == "windows":
        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [
                ("cbSize", ctypes.c_uint),
                ("dwTime", ctypes.c_uint),
            ]

        try:
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

            info = LASTINPUTINFO()
            info.cbSize = ctypes.sizeof(LASTINPUTINFO)

            user32.GetLastInputInfo.argtypes = [
                ctypes.POINTER(LASTINPUTINFO)
            ]
            user32.GetLastInputInfo.restype = ctypes.c_bool
            kernel32.GetTickCount.restype = ctypes.c_uint

            if not user32.GetLastInputInfo(ctypes.byref(info)):
                return None

            current_tick = kernel32.GetTickCount()
            elapsed_ms = (current_tick - info.dwTime) & 0xFFFFFFFF

            return elapsed_ms / 1000

        except (AttributeError, OSError):
            return None

    return None


def get_running_editors():
    """Return supported editors detected on this computer."""
    operating_system = get_operating_system()
    editors = SUPPORTED_EDITORS.get(operating_system, [])

    if not editors:
        return []

    try:
        if operating_system == "ubuntu_or_linux":
            result = subprocess.run(
                ["ps", "-eo", "comm"],
                capture_output=True,
                text=True,
                check=True,
                timeout=5,
            )
        elif operating_system == "windows":
            result = subprocess.run(
                ["tasklist", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                check=True,
                timeout=5,
            )
        else:
            return []

    except (OSError, subprocess.SubprocessError):
        return []

    if operating_system == "windows":
        rows = csv.reader(result.stdout.splitlines())

        running_processes = {
            row[0].strip().lower()
            for row in rows
            if row
        }
    else:
        running_processes = {
            line.strip().lower()
            for line in result.stdout.splitlines()
        }

    return [
        editor
        for editor in editors
        if editor.lower() in running_processes
    ]