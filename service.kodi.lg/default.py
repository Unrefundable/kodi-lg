"""Kodi LG - default.py.

Script entry point for the FF/RW seek keymap actions.
"""

import sys
import time

import xbmc
import xbmcaddon
import xbmcgui

_ADDON = xbmcaddon.Addon()
_ADDON_ID = _ADDON.getAddonInfo("id")

_HOME_WIN = xbmcgui.Window(10000)
_PROP_DIR = "KodiLG_SeekDir"
_PROP_COUNT = "KodiLG_SeekCount"
_PROP_TIME = "KodiLG_SeekTime"


def _log(msg: str, level: int = xbmc.LOGINFO) -> None:
    xbmc.log(f"[{_ADDON_ID}] {msg}", level)


def _parse_args() -> dict:
    args = {}
    for part in sys.argv[1:]:
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        args[key.strip()] = value.strip()
    return args


def _handle_seek(direction: int) -> None:
    """Record one FF/RW press into the shared window properties."""
    prev_dir = _HOME_WIN.getProperty(_PROP_DIR)
    prev_count = int(_HOME_WIN.getProperty(_PROP_COUNT) or "0")

    if prev_dir and int(prev_dir) != direction:
        prev_count = 0

    _HOME_WIN.setProperty(_PROP_DIR, str(direction))
    _HOME_WIN.setProperty(_PROP_COUNT, str(prev_count + 1))
    _HOME_WIN.setProperty(_PROP_TIME, str(time.time()))


def main() -> None:
    action = _parse_args().get("action", "")

    if action == "seek_forward":
        _handle_seek(1)
        return

    if action == "seek_back":
        _handle_seek(-1)
        return

    if action:
        _log(f"Ignoring unsupported action: {action}", xbmc.LOGWARNING)
    else:
        _log("Ignoring script call without an action.", xbmc.LOGWARNING)


if __name__ == "__main__":
    main()
