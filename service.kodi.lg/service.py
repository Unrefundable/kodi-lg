"""Kodi LG - service.py.

Background service that keeps the managed keymaps and Bingie skin files in
place, applies the Trakt page-size override, and commits one seek on FF/RW
button release.
"""

import os
import time
import xml.etree.ElementTree as ET

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

_ADDON = xbmcaddon.Addon()
_ADDON_ID = _ADDON.getAddonInfo("id")
_ADDON_PATH = xbmcvfs.translatePath(_ADDON.getAddonInfo("path"))

_KEYMAP_SRC = os.path.join(_ADDON_PATH, "resources", "keymaps", "kodi_lg.xml")
_KEYMAP_DST = xbmcvfs.translatePath("special://userdata/keymaps/kodi_lg.xml")

_SEEK_KEYMAP_SRC = os.path.join(_ADDON_PATH, "resources", "keymaps", "kodi_seek.xml")
_SEEK_KEYMAP_DST = xbmcvfs.translatePath("special://userdata/keymaps/kodi_seek.xml")

_SKIN_PATCHES = [
    ("1080i/VideoOSD.xml", "special://home/addons/skin.bingie/1080i/VideoOSD.xml"),
    ("1080i/Custom_1109_BingieSearch.xml", "special://home/addons/skin.bingie/1080i/Custom_1109_BingieSearch.xml"),
]


def _log(msg: str, level: int = xbmc.LOGINFO) -> None:
    xbmc.log(f"[{_ADDON_ID}] {msg}", level)


def install_keymap() -> None:
    """Copy the keymap XML to userdata/keymaps/ and ask Kodi to reload it."""
    try:
        ok = xbmcvfs.copy(_KEYMAP_SRC, _KEYMAP_DST)
        if ok:
            _log(f"Keymap installed: {_KEYMAP_DST}")
        else:
            _log(f"xbmcvfs.copy failed: {_KEYMAP_SRC} -> {_KEYMAP_DST}", xbmc.LOGERROR)
    except Exception as exc:  # noqa: BLE001
        _log(f"Failed to install keymap: {exc}", xbmc.LOGERROR)


def install_seek_keymap() -> None:
    """Deploy the general seek keymap (FF/RW → direct seek for all remotes)."""
    try:
        ok = xbmcvfs.copy(_SEEK_KEYMAP_SRC, _SEEK_KEYMAP_DST)
        if ok:
            _log(f"Seek keymap installed: {_SEEK_KEYMAP_DST}")
        else:
            _log(f"xbmcvfs.copy failed: {_SEEK_KEYMAP_SRC} -> {_SEEK_KEYMAP_DST}", xbmc.LOGERROR)
    except Exception as exc:  # noqa: BLE001
        _log(f"Failed to install seek keymap: {exc}", xbmc.LOGERROR)


def remove_keymap() -> None:
    """Delete the installed keymaps and reload Kodi's keymaps."""
    try:
        if xbmcvfs.exists(_KEYMAP_DST):
            xbmcvfs.delete(_KEYMAP_DST)
            _log("LG keymap removed.")
    except Exception as exc:  # noqa: BLE001
        _log(f"Failed to remove keymap: {exc}", xbmc.LOGERROR)
    xbmc.executebuiltin("Action(reloadkeymaps)")


def patch_bingie_skin() -> None:
    """Sync the managed Bingie skin files into the installed skin."""
    patches_dir = os.path.join(_ADDON_PATH, "resources", "skin_patches")
    bingie_base = xbmcvfs.translatePath("special://home/addons/skin.bingie/")

    if not xbmcvfs.exists(bingie_base):
        _log("skin.bingie not found – skipping skin patches.")
        return

    for rel_src, dst_special in _SKIN_PATCHES:
        src = os.path.join(patches_dir, rel_src.replace("/", os.sep))
        dst = xbmcvfs.translatePath(dst_special)
        try:
            ok = xbmcvfs.copy(src, dst)
            if ok:
                _log(f"Skin file synced: {dst_special}")
            else:
                _log(f"xbmcvfs.copy failed: {src} -> {dst}", xbmc.LOGERROR)
        except Exception as exc:  # noqa: BLE001
            _log(f"Failed to apply skin patch {rel_src}: {exc}", xbmc.LOGERROR)


class LGMonitor(xbmc.Monitor):
    """Watches for settings changes so the keymap can be toggled at runtime."""

    def onSettingsChanged(self) -> None:  # noqa: N802
        addon = xbmcaddon.Addon()
        remap_enabled = addon.getSetting("remap_ud") == "true"
        if remap_enabled:
            install_keymap()
        else:
            remove_keymap()


# ── Seek accumulator ──────────────────────────────────────────────────────── #
# Shared window properties (set by default.py via RunScript, read here).
_HOME_WIN      = None   # set in main() after xbmcgui is usable
_PROP_DIR      = "KodiLG_SeekDir"
_PROP_COUNT    = "KodiLG_SeekCount"
_PROP_TIME     = "KodiLG_SeekTime"

# How long after the LAST button press before we commit the seek.
# 1.5 s lets the user hold the button as long as they want; the seek
# fires ~1.5 s after they release.
_SEEK_COMMIT_DELAY = 1.5


def _get_big_seek_step_seconds() -> int:
    """Read Kodi's own 'big skip step' setting (set in Settings → Player).

    Returns the step in seconds.  Falls back to 600 s (10 min) if the
    setting cannot be read.
    """
    try:
        import json as _json
        result = xbmc.executeJSONRPC(_json.dumps({
            "jsonrpc": "2.0",
            "method": "Settings.GetSettingValue",
            "params": {"setting": "videoplayer.seekstepsbig"},
            "id": 1,
        }))
        data = _json.loads(result)
        minutes = data.get("result", {}).get("value", 10)
        return int(minutes) * 60
    except Exception:
        return 600


def seek_accumulator_loop(monitor: xbmc.Monitor) -> None:
    """Background loop: wait for FF/RW button to be released, then seek once.

    default.py writes _PROP_DIR / _PROP_COUNT / _PROP_TIME on each key
    repeat.  We poll every 0.2 s; when _PROP_TIME is more than
    _SEEK_COMMIT_DELAY seconds old we execute one seekTime() to the
    accumulated target position and clear state.
    """
    home = xbmcgui.Window(10000)
    player = xbmc.Player()

    while not monitor.abortRequested():
        raw_ts = home.getProperty(_PROP_TIME)
        if raw_ts:
            elapsed = time.time() - float(raw_ts)
            if elapsed >= _SEEK_COMMIT_DELAY:
                # Atomically clear so we don't double-seek.
                home.setProperty(_PROP_TIME, "")
                count     = int(home.getProperty(_PROP_COUNT) or "0")
                direction = int(home.getProperty(_PROP_DIR)   or "0")
                home.setProperty(_PROP_COUNT, "0")

                if count > 0 and direction != 0 and player.isPlayingVideo():
                    step    = _get_big_seek_step_seconds()
                    current = player.getTime()
                    total   = player.getTotalTime()
                    target  = max(0.0, min(float(total), current + direction * count * step))
                    _log(
                        f"Seek: {'+' if direction > 0 else ''}"
                        f"{direction * count * step}s "
                        f"({count} × {step}s) → {target:.0f}s"
                    )
                    player.seekTime(target)

        if monitor.waitForAbort(0.2):
            break


def set_trakt_page_size() -> None:
    """Set pagemulti_trakt=13 in the TMDb Bingie Helper user settings.

    The plugin's UI caps this at 3 (60 items) but the code reads the
    value directly from the user settings XML, so writing 13 gives
    20 × 13 = 260 items — enough to cover the full Trakt Top 250.
    """
    settings_path = xbmcvfs.translatePath(
        "special://profile/addon_data/plugin.video.tmdb.bingie.helper/settings.xml"
    )
    if not xbmcvfs.exists(settings_path):
        _log("TMDb Bingie Helper settings.xml not found – skipping pagemulti_trakt patch.")
        return

    try:
        with xbmcvfs.File(settings_path) as fh:
            raw = fh.read()
        tree = ET.fromstring(raw)

        for elem in tree.findall("setting"):
            if elem.get("id") == "pagemulti_trakt":
                if elem.text == "13":
                    return  # already set, nothing to do
                elem.text = "13"
                elem.set("default", "false")
                break
        else:
            # Setting not present yet – add it
            new = ET.SubElement(tree, "setting", {"id": "pagemulti_trakt", "default": "false"})
            new.text = "13"

        updated = ET.tostring(tree, encoding="unicode", xml_declaration=False)
        with xbmcvfs.File(settings_path, "w") as fh:
            fh.write(updated)
        _log("pagemulti_trakt set to 13 (Trakt Top 250 now fetches 260 items).")
    except Exception as exc:  # noqa: BLE001
        _log(f"Failed to patch pagemulti_trakt: {exc}", xbmc.LOGERROR)


def ensure_advanced_settings() -> None:
    """Ensure advancedsettings.xml exists but leave any existing user content.

    seekdelay is no longer needed: FF/RW now use the script-based
    seek accumulator in seek_accumulator_loop(), which fires ONE seekTime()
    call after the user releases the button.  We only write the file if it
    doesn't already exist so we don't clobber user customisations.
    """
    dst = xbmcvfs.translatePath("special://profile/advancedsettings.xml")
    if xbmcvfs.exists(dst):
        _log("advancedsettings.xml already present — not overwriting.")
        return
    minimal = "<advancedsettings>\n</advancedsettings>\n"
    try:
        with xbmcvfs.File(dst, "w") as fh:
            fh.write(minimal)
        _log("advancedsettings.xml created (minimal placeholder).")
    except Exception as exc:  # noqa: BLE001
        _log(f"Failed to write advancedsettings.xml: {exc}", xbmc.LOGERROR)


def main() -> None:
    # Apply managed skin files, keymaps, and settings on startup.
    patch_bingie_skin()
    install_seek_keymap()
    set_trakt_page_size()
    ensure_advanced_settings()

    addon = xbmcaddon.Addon()
    if addon.getSetting("remap_ud") != "false":
        install_keymap()

    xbmc.executebuiltin("Action(reloadkeymaps)")

    # Force Kodi to re-fetch addons.xml from all repositories so the
    # latest version is always visible without waiting for the daily poll.
    xbmc.executebuiltin("UpdateAddonRepos")

    monitor = LGMonitor()

    # Start the seek accumulator in a background thread.  It polls window
    # properties written by default.py (via RunScript) and fires one
    # seekTime() call ~1.5 s after the user releases the FF/RW button.
    import threading
    seek_thread = threading.Thread(
        target=seek_accumulator_loop, args=(monitor,), daemon=True
    )
    seek_thread.start()

    while not monitor.abortRequested():
        if monitor.waitForAbort(60):
            break


if __name__ == "__main__":
    main()
