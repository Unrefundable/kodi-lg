"""Kodi LG - default.py.

Script entry point for remote key actions managed by Kodi LG.
"""

import json
import random
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


def _jsonrpc(method: str, params: dict | None = None) -> dict:
    try:
        raw = xbmc.executeJSONRPC(json.dumps({
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
            "id": 1,
        }))
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception as exc:  # noqa: BLE001
        _log(f"JSON-RPC {method} failed: {exc}", xbmc.LOGWARNING)
        return {}


def _item_unique_id(item: dict, *keys: str) -> str:
    unique_ids = item.get("uniqueid") or {}
    if not isinstance(unique_ids, dict):
        return ""
    for key in keys:
        value = str(unique_ids.get(key) or "").strip()
        if value:
            return value
    return ""


def _detail_path_from_library_item(media_type: str, item: dict) -> str:
    tmdb_id = _item_unique_id(item, "tmdb", "tmdb_id")
    imdb_id = _item_unique_id(item, "imdb", "imdb_id")
    params = {"info": "details", "tmdb_type": media_type, "nextpage": "false"}
    if tmdb_id:
        params["tmdb_id"] = tmdb_id
        return "plugin://plugin.video.tmdb.bingie.helper/?" + urlencode(params)
    if imdb_id:
        params["imdb_id"] = imdb_id
        return "plugin://plugin.video.tmdb.bingie.helper/?" + urlencode(params)
    if media_type == "movie" and item.get("movieid"):
        return f"videodb://movies/titles/{item['movieid']}/"
    if media_type == "tv" and item.get("tvshowid"):
        return f"videodb://tvshows/titles/{item['tvshowid']}/"
    return ""


def _random_library_detail_path() -> str:
    queries = [
        ("movie", "VideoLibrary.GetMovies", "movies"),
        ("tv", "VideoLibrary.GetTVShows", "tvshows"),
    ]
    random.shuffle(queries)
    for media_type, method, result_key in queries:
        data = _jsonrpc(method, {
            "properties": ["uniqueid", "title", "year"],
            "limits": {"start": 0, "end": 1},
            "sort": {"method": "random"},
        })
        items = data.get("result", {}).get(result_key) or []
        if not items:
            continue
        path = _detail_path_from_library_item(media_type, items[0])
        if path:
            return path
    return ""


def _handle_surprise_me() -> None:
    """Open one random movie/show details page instead of a random-items listing."""
    path = _random_library_detail_path()
    if not path:
        xbmcgui.Dialog().notification("Kodi LG", "No random title found", xbmcgui.NOTIFICATION_INFO, 4000)
        _log("Surprise Me could not find a library movie or show.", xbmc.LOGWARNING)
        return
    _show_staging_overlay()
    try:
        xbmc.executebuiltin(f'ActivateWindow(Videos,"{path}",return)')
        xbmc.sleep(_STAGING_WAIT_MS)
        _close_staging_overlay()
        xbmc.sleep(100)
        if not _open_video_info_dialog():
            _log("Surprise Me landed on details listing; Info dialog did not open.", xbmc.LOGWARNING)
    finally:
        _close_staging_overlay()


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

    if action == "surprise_me":
        _handle_surprise_me()
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
