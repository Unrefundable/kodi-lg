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

3. TRAKT PAGE SIZE
   Sets pagemulti_trakt=13 in the TMDb Bingie Helper user settings so
   Trakt lists (e.g. Top 250) fetch up to 260 items instead of the
   default 20.

4. STREAM BUFFER (advancedsettings.xml)
   Creates userdata/advancedsettings.xml with a 256 MiB read-ahead cache
   so fast-forward/rewind on streaming sources doesn't snap back.
"""

import os
import xml.etree.ElementTree as ET

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


_ADVANCED_SETTINGS = """\
<advancedsettings>
    <!-- Stream buffer: 256 MiB read-ahead so FF/RW on streaming sources
         doesn't snap back on slow-start devices (e.g. Ugoos AM6B+). -->
    <cache>
        <buffermode>1</buffermode>
        <memorysize>268435456</memorysize>
        <readfactor>20.0</readfactor>
    </cache>
</advancedsettings>
"""


def ensure_advanced_settings() -> None:
    """Create userdata/advancedsettings.xml with stream buffer settings.

    Only writes the file if it does not already exist, so manual edits
    made by the user are never overwritten.
    """
    dst = xbmcvfs.translatePath("special://profile/advancedsettings.xml")
    if xbmcvfs.exists(dst):
        _log("advancedsettings.xml already exists – not overwriting.")
        return
    try:
        with xbmcvfs.File(dst, "w") as fh:
            fh.write(_ADVANCED_SETTINGS)
        _log("advancedsettings.xml created with 256 MiB stream buffer.")
    except Exception as exc:  # noqa: BLE001
        _log(f"Failed to create advancedsettings.xml: {exc}", xbmc.LOGERROR)


def main() -> None:
    # Apply skin patches and keymap on startup.
    patch_bingie_skin()
    set_trakt_page_size()
    ensure_advanced_settings()

    addon = xbmcaddon.Addon()
    if addon.getSetting("remap_ud") != "false":
        install_keymap()

    # Force Kodi to re-fetch addons.xml from all repositories so the
    # latest version is always visible without waiting for the daily poll.
    xbmc.executebuiltin("UpdateAddonRepos")

    monitor = LGMonitor()
    while not monitor.abortRequested():
        if monitor.waitForAbort(60):
            break


if __name__ == "__main__":
    main()
