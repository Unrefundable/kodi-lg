"""
Kodi LG – service.py
Background service that runs for the lifetime of Kodi.

Responsibilities
────────────────
1. KEYMAP INSTALLATION
   Copies resources/keymaps/kodi_lg.xml to special://userdata/keymaps/ on
   startup so the LG CEC remote button remaps are always active, even after
   Kodi updates or add-on reinstalls.

2. SETTINGS WATCH
   Re-installs or removes the keymap when the user toggles the
   "remap_ud" setting so changes take effect without a Kodi restart
   (a keymap reload is triggered automatically).
"""

import os

import xbmc
import xbmcaddon
import xbmcvfs

_ADDON = xbmcaddon.Addon()
_ADDON_ID = _ADDON.getAddonInfo("id")
_ADDON_PATH = xbmcvfs.translatePath(_ADDON.getAddonInfo("path"))

_KEYMAP_SRC = os.path.join(_ADDON_PATH, "resources", "keymaps", "kodi_lg.xml")
_KEYMAP_DST = xbmcvfs.translatePath("special://userdata/keymaps/kodi_lg.xml")

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
            xbmc.executebuiltin("Action(reloadkeymaps)")
            _log(f"Keymap installed: {_KEYMAP_DST}")
        else:
            _log(f"xbmcvfs.copy failed: {_KEYMAP_SRC} -> {_KEYMAP_DST}", xbmc.LOGERROR)
    except Exception as exc:  # noqa: BLE001
        _log(f"Failed to install keymap: {exc}", xbmc.LOGERROR)


def remove_keymap() -> None:
    """Delete the installed keymap and reload Kodi's keymaps."""
    try:
        if xbmcvfs.exists(_KEYMAP_DST):
            xbmcvfs.delete(_KEYMAP_DST)
            xbmc.executebuiltin("Action(reloadkeymaps)")
            _log("Keymap removed.")
    except Exception as exc:  # noqa: BLE001
        _log(f"Failed to remove keymap: {exc}", xbmc.LOGERROR)


def patch_bingie_skin() -> None:
    """Copy patched Bingie skin files from addon resources into the skin folder.

    Patches applied:
    - VideoOSD.xml       – removes the auto-pause-on-OSD onload action so pressing
                           Up/Down shows the OSD without pausing playback.
    - Custom_1109_BingieSearch.xml – adds the voice-search mic button (id=9898).
    """
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
                _log(f"Skin patch applied: {dst_special}")
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


def main() -> None:
    # Apply skin patches and keymap on startup.
    patch_bingie_skin()

    addon = xbmcaddon.Addon()
    if addon.getSetting("remap_ud") != "false":
        install_keymap()

    monitor = LGMonitor()
    while not monitor.abortRequested():
        if monitor.waitForAbort(60):
            break


if __name__ == "__main__":
    main()
