"""Platform-specific activity detection for CodeTime."""

import csv
import platform
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
