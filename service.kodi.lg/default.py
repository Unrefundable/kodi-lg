"""Kodi LG - default.py.

Script entry point for remote key actions managed by Kodi LG.
"""

import json
import sys
import time
from urllib.parse import urlencode

import xbmc
import xbmcaddon
import xbmcgui

_ADDON = xbmcaddon.Addon()
_ADDON_ID = _ADDON.getAddonInfo("id")

_HOME_WIN = xbmcgui.Window(10000)
_PROP_DIR = "KodiLG_SeekDir"
_PROP_COUNT = "KodiLG_SeekCount"
_PROP_TIME = "KodiLG_SeekTime"
_KDMM_CONTEXT = "kdmm.playback_context"
_STAGING_WAIT_MS = 2200


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


def _detail_path_from_context(raw_context: str) -> str:
    """Build the TMDb Bingie Helper details route for the current KDMM item."""
    if not raw_context:
        return ""
    try:
        context = json.loads(raw_context)
    except Exception:
        return ""
    if not isinstance(context, dict):
        return ""

    is_movie = bool(context.get("is_movie"))
    tmdb_id = str(context.get("tmdb_id") or "").strip()
    imdb_id = str(context.get("imdb_id") or "").strip()

    params = {
        "info": "details",
        "tmdb_type": "movie" if is_movie else "tv",
        "nextpage": "false",
    }
    if tmdb_id:
        params["tmdb_id"] = tmdb_id
    elif imdb_id:
        params["imdb_id"] = imdb_id
    else:
        return ""

    return "plugin://plugin.video.tmdb.bingie.helper/?" + urlencode(params)


def _open_video_info_dialog() -> bool:
    """Open Bingie's video-info dialog after a TMDb Helper details route loads."""
    for _ in range(24):
        if xbmc.getCondVisibility("Window.IsActive(DialogVideoInfo.xml)"):
            return True
        xbmc.executeJSONRPC(json.dumps({
            "jsonrpc": "2.0",
            "method": "Input.ExecuteAction",
            "params": {"action": "info"},
            "id": 1,
        }))
        xbmc.sleep(450)
    return False


def _show_staging_overlay() -> None:
    """Hide TMDb Helper's one-item staging list while the real dialog opens."""
    xbmc.executebuiltin("ActivateWindow(busydialognocancel)")


def _close_staging_overlay() -> None:
    xbmc.executebuiltin("Dialog.Close(busydialognocancel,true)")
    xbmc.executebuiltin("Dialog.Close(busydialog,true)")


def _handle_back_from_video() -> None:
    """Stop playback and return to the matching movie/show details route."""
    path = _detail_path_from_context(_HOME_WIN.getProperty(_KDMM_CONTEXT))
    xbmc.Player().stop()
    if not path:
        return
    _show_staging_overlay()
    try:
        xbmc.sleep(900)
        xbmc.executebuiltin(f'ActivateWindow(Videos,"{path}",return)')
        xbmc.sleep(_STAGING_WAIT_MS)
        _close_staging_overlay()
        xbmc.sleep(100)
        if not _open_video_info_dialog():
            _log("Back from video landed on details listing; Info dialog did not open.", xbmc.LOGWARNING)
    finally:
        _close_staging_overlay()


def _handle_video_info_buttons() -> None:
    """Keep the customized video-info buttons aligned with the inline shelves."""
    xbmc.executebuiltin("Skin.SetBool(videoinfo_button_trailer)")
    xbmc.executebuiltin("Skin.Reset(videoinfo_button_similar)")
    xbmc.executebuiltin("Skin.Reset(videoinfo_button_trailersandmore)")


def main() -> None:
    action = _parse_args().get("action", "")

    if action == "seek_forward":
        _handle_seek(1)
        return

    if action == "seek_back":
        _handle_seek(-1)
        return

    if action == "back_from_video":
        _handle_back_from_video()
        return

    if action == "video_info_buttons":
        _handle_video_info_buttons()
        return

    if action:
        _log(f"Ignoring unsupported action: {action}", xbmc.LOGWARNING)
    else:
        _log("Ignoring script call without an action.", xbmc.LOGWARNING)


if __name__ == "__main__":
    main()
