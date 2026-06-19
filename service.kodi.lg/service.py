"""Kodi LG - service.py.

Background service that keeps the managed keymaps and Bingie skin files in
place, applies the Trakt page-size override, and commits one seek on FF/RW
button release.
"""

import os
import json
import shutil
import time
import xml.etree.ElementTree as ET
from typing import Optional

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
    ("1080i/LoginScreen.xml", "special://home/addons/skin.bingie/1080i/LoginScreen.xml"),
    ("1080i/DialogNotification.xml", "special://home/addons/skin.bingie/1080i/DialogNotification.xml"),
    ("1080i/MyVideoNav.xml", "special://home/addons/skin.bingie/1080i/MyVideoNav.xml"),
    ("1080i/MyMusicNav.xml", "special://home/addons/skin.bingie/1080i/MyMusicNav.xml"),
    ("1080i/Custom_1102_StartUp2.xml", "special://home/addons/skin.bingie/1080i/Custom_1102_StartUp2.xml"),
    ("1080i/script-skinshortcuts-includes.xml", "special://home/addons/skin.bingie/1080i/script-skinshortcuts-includes.xml"),
    ("1080i/IncludesPaths.xml", "special://home/addons/skin.bingie/1080i/IncludesPaths.xml"),
    ("1080i/IncludesDefaultSkinSettings.xml", "special://home/addons/skin.bingie/1080i/IncludesDefaultSkinSettings.xml"),
    ("1080i/IncludesDialogVideoInfo.xml", "special://home/addons/skin.bingie/1080i/IncludesDialogVideoInfo.xml"),
]

_PROFILE_DEFAULT_FILES = [
    "guisettings.xml",
    "advancedsettings.xml",
    "sources.xml",
    "keymaps/kodi_lg.xml",
    "keymaps/kodi_seek.xml",
    "addon_data/skin.bingie/settings.xml",
    "addon_data/inputstream.adaptive/settings.xml",
    "addon_data/plugin.video.youtube/settings.xml",
    "addon_data/plugin.video.tmdb.bingie.helper/settings.xml",
    "addon_data/plugin.video.tmdb.bingie.helper/players/kdmm.json",
    "addon_data/plugin.video.kdmm/settings.xml",
    "addon_data/plugin.video.kdmm/ad_tokens.json",
    "addon_data/plugin.video.kdmm/settings_persistence.json",
]

_BINGIE_THREAD_PATH = xbmcvfs.translatePath(
    "special://home/addons/script.module.bingie/resources/modules/bingie/thread.py"
)

_VIDEO_INFO_BUTTON_SETTINGS = {
    "videoinfo_button_artwork": False,
    "videoinfo_button_cast": False,
    "videoinfo_button_favorites": False,
    "videoinfo_button_moreinfo": False,
    "videoinfo_button_mylist": True,
    "videoinfo_button_myrating": False,
    "videoinfo_button_play_beginning": True,
    "videoinfo_button_play_next": True,
    "videoinfo_button_play_next_tmdb": True,
    "videoinfo_button_plot": False,
    "videoinfo_button_refresh": False,
    "videoinfo_button_similar": False,
    "videoinfo_button_trailer": True,
    "videoinfo_button_trailersandmore": False,
    "videoinfo_button_trakt": False,
    "videoinfo_button_versions": False,
    "videoinfo_button_wikipedia": False,
}


def _log(msg: str, level: int = xbmc.LOGINFO) -> None:
    xbmc.log(f"[{_ADDON_ID}] {msg}", level)


def raise_file_descriptor_limit() -> None:
    """Give large cloud widgets enough file handles on macOS."""
    try:
        import resource
    except Exception as exc:  # noqa: BLE001
        _log(f"resource module unavailable; cannot raise file limit: {exc}", xbmc.LOGWARNING)
        return

    try:
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        target = min(max(soft, 4096), hard if hard > 0 else 4096)
        if soft < target:
            resource.setrlimit(resource.RLIMIT_NOFILE, (target, hard))
            _log(f"Raised file descriptor limit from {soft} to {target}.")
    except Exception as exc:  # noqa: BLE001
        _log(f"Failed to raise file descriptor limit: {exc}", xbmc.LOGWARNING)


def patch_bingie_thread_limit() -> None:
    """Cap Bingie's unlimited ParallelThread fan-out for 250-item widgets."""
    try:
        if not os.path.exists(_BINGIE_THREAD_PATH):
            return
        with open(_BINGIE_THREAD_PATH, "r", encoding="utf-8") as fh:
            raw = fh.read()
        if "thread_max = 12" in raw:
            return
        updated = raw.replace("thread_max = 0  # 0 is unlimited", "thread_max = 12")
        updated = updated.replace("thread_max = 0", "thread_max = 12")
        if updated != raw:
            with open(_BINGIE_THREAD_PATH, "w", encoding="utf-8") as fh:
                fh.write(updated)
            _log("Bingie ParallelThread limit set to 12.")
    except Exception as exc:  # noqa: BLE001
        _log(f"Failed to patch Bingie thread limit: {exc}", xbmc.LOGERROR)


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


def sync_profile_defaults() -> None:
    """Copy Master profile defaults into non-master profiles.

    Kodi's profile editor creates sparse profiles with stock settings. For this
    cloud-streaming setup the Master profile is the baseline, so every profile
    should inherit the same skin, widget, keymap, source, and helper settings.
    """
    master_dir = xbmcvfs.translatePath("special://masterprofile/")
    profiles_xml = os.path.join(master_dir, "profiles.xml")
    if not os.path.exists(profiles_xml):
        _log("profiles.xml not found - skipping profile default sync.")
        return

    try:
        tree = ET.parse(profiles_xml)
        root = tree.getroot()
    except Exception as exc:  # noqa: BLE001
        _log(f"Failed to read profiles.xml: {exc}", xbmc.LOGERROR)
        return

    for profile in root.findall("profile"):
        directory = profile.find("directory")
        name = profile.findtext("name", "")
        if directory is None:
            continue

        rel_dir = (directory.text or "").strip()
        if rel_dir in ("", "special://masterprofile/"):
            continue

        profile_dir = os.path.join(master_dir, rel_dir)
        copied = 0
        for rel_file in _PROFILE_DEFAULT_FILES:
            src = os.path.join(master_dir, rel_file)
            dst = os.path.join(profile_dir, rel_file)
            if not os.path.exists(src):
                continue
            try:
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)
                copied += 1
            except Exception as exc:  # noqa: BLE001
                _log(f"Failed to sync {rel_file} to profile {name}: {exc}", xbmc.LOGERROR)

        if copied:
            _log(f"Profile defaults synced to {name or rel_dir}: {copied} files.")


def _set_xml_setting(path: str, setting_id: str, value: str, default: Optional[str] = "true") -> bool:
    """Set a Kodi XML setting value in-place."""
    if not os.path.exists(path):
        return False
    try:
        tree = ET.parse(path)
        root = tree.getroot()
        changed = False
        for elem in root.findall("setting"):
            if elem.get("id") != setting_id:
                continue
            if elem.text != value:
                elem.text = value
                changed = True
            if default is not None and elem.get("default") != default:
                elem.set("default", default)
                changed = True
            break
        else:
            attrs = {"id": setting_id}
            if default is not None:
                attrs["default"] = default
            elem = ET.SubElement(root, "setting", attrs)
            elem.text = value
            changed = True

        if changed:
            tree.write(path, encoding="utf-8", xml_declaration=False)
        return changed
    except Exception as exc:  # noqa: BLE001
        _log(f"Failed to update XML setting {setting_id} in {path}: {exc}", xbmc.LOGERROR)
        return False


def enforce_cloud_file_settings() -> None:
    """Disable Kodi's add-source/local-file affordances for every profile."""
    try:
        xbmc.executeJSONRPC(json.dumps({
            "jsonrpc": "2.0",
            "method": "Settings.SetSettingValue",
            "params": {
                "setting": "filelists.showaddsourcebuttons",
                "value": False,
            },
            "id": 1,
        }))
    except Exception as exc:  # noqa: BLE001
        _log(f"Failed to set runtime add-source setting: {exc}", xbmc.LOGWARNING)

    master_dir = xbmcvfs.translatePath("special://masterprofile/")
    paths = [os.path.join(master_dir, "guisettings.xml")]
    profiles_dir = os.path.join(master_dir, "profiles")
    if os.path.isdir(profiles_dir):
        for name in os.listdir(profiles_dir):
            paths.append(os.path.join(profiles_dir, name, "guisettings.xml"))

    changed = 0
    for path in paths:
        if _set_xml_setting(path, "filelists.showaddsourcebuttons", "false"):
            changed += 1
        if _set_xml_setting(
            path,
            "debug.screenshotpath",
            xbmcvfs.translatePath("special://masterprofile/screenshots/"),
            default=None,
        ):
            changed += 1
    if changed:
        _log(f"Cloud file-list settings enforced in {changed} profile file(s).")


def enforce_macos_audio_settings() -> None:
    """Replace copied CoreELEC ALSA devices with the Mac default audio sink."""
    runtime_settings = {
        "audiooutput.audiodevice": "DARWINOSX:default|Default",
        "audiooutput.passthrough": False,
        "audiooutput.passthroughdevice": "DARWINOSX:default|Default",
    }
    for setting, value in runtime_settings.items():
        try:
            xbmc.executeJSONRPC(json.dumps({
                "jsonrpc": "2.0",
                "method": "Settings.SetSettingValue",
                "params": {
                    "setting": setting,
                    "value": value,
                },
                "id": 1,
            }))
        except Exception as exc:  # noqa: BLE001
            _log(f"Failed to set runtime audio setting {setting}: {exc}", xbmc.LOGWARNING)

    master_dir = xbmcvfs.translatePath("special://masterprofile/")
    paths = [os.path.join(master_dir, "guisettings.xml")]
    profiles_dir = os.path.join(master_dir, "profiles")
    if os.path.isdir(profiles_dir):
        for name in os.listdir(profiles_dir):
            paths.append(os.path.join(profiles_dir, name, "guisettings.xml"))

    changed = 0
    for path in paths:
        changed += int(_set_xml_setting(
            path, "audiooutput.audiodevice", "DARWINOSX:default|Default", default=None
        ))
        changed += int(_set_xml_setting(path, "audiooutput.passthrough", "false", default=None))
        changed += int(_set_xml_setting(
            path, "audiooutput.passthroughdevice", "DARWINOSX:default|Default", default=None
        ))
    if changed:
        _log(f"macOS audio settings enforced ({changed} value update(s)).")


def _profile_dirs() -> list[str]:
    """Return master plus all named Kodi profile directories."""
    master_dir = xbmcvfs.translatePath("special://masterprofile/")
    dirs = [master_dir]
    profiles_dir = os.path.join(master_dir, "profiles")
    if os.path.isdir(profiles_dir):
        for name in os.listdir(profiles_dir):
            profile_dir = os.path.join(profiles_dir, name)
            if os.path.isdir(profile_dir):
                dirs.append(profile_dir)
    return dirs


def _ensure_settings_xml(path: str) -> None:
    if os.path.exists(path):
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write('<settings version="2">\n</settings>\n')


def enforce_trailer_quality_settings() -> None:
    """Prefer the highest available YouTube trailer streams."""
    youtube_values = {
        "kodion.video.quality.isa": "true",
        "kodion.mpd.videos": "true",
        "kodion.mpd.stream.select": "3",
        "kodion.mpd.quality.selection": "6",
        "kodion.video.quality.ask": "false",
        "kodion.video.quality": "4",
    }
    inputstream_values = {
        "adaptivestream.type": "default",
        "adaptivestream.res.max": "4K",
        "adaptivestream.res.secure.max": "4K",
        "adaptivestream.bandwidth.init.auto": "false",
        "adaptivestream.bandwidth.init": "1000000",
        "adaptivestream.bandwidth.max": "0",
    }

    changed = 0
    for profile_dir in _profile_dirs():
        youtube_path = os.path.join(profile_dir, "addon_data", "plugin.video.youtube", "settings.xml")
        if os.path.exists(youtube_path):
            for setting, value in youtube_values.items():
                changed += int(_set_xml_setting(youtube_path, setting, value, default=None))

        inputstream_path = os.path.join(profile_dir, "addon_data", "inputstream.adaptive", "settings.xml")
        try:
            _ensure_settings_xml(inputstream_path)
            for setting, value in inputstream_values.items():
                changed += int(_set_xml_setting(inputstream_path, setting, value, default=None))
        except Exception as exc:  # noqa: BLE001
            _log(f"Failed to enforce inputstream quality settings in {inputstream_path}: {exc}", xbmc.LOGERROR)

    if changed:
        _log(f"Trailer quality settings enforced ({changed} value update(s)).")


def enforce_video_info_button_settings() -> None:
    """Keep video-info buttons aligned with the Mac/Ugoos curated layout."""
    changed = 0
    for setting, enabled in _VIDEO_INFO_BUTTON_SETTINGS.items():
        xbmc.executebuiltin(f"Skin.SetBool({setting})" if enabled else f"Skin.Reset({setting})")

    for profile_dir in _profile_dirs():
        settings_path = os.path.join(profile_dir, "addon_data", "skin.bingie", "settings.xml")
        try:
            _ensure_settings_xml(settings_path)
            for setting, enabled in _VIDEO_INFO_BUTTON_SETTINGS.items():
                changed += int(_set_xml_setting(
                    settings_path,
                    setting,
                    "true" if enabled else "false",
                    default=None,
                ))
        except Exception as exc:  # noqa: BLE001
            _log(f"Failed to enforce video-info buttons in {settings_path}: {exc}", xbmc.LOGERROR)
    if changed:
        _log(f"Video-info button settings enforced ({changed} value update(s)).")


def patch_tmdb_helper_settings_schema() -> None:
    """Allow pagemulti_trakt=13 so Kodi accepts 260-item Trakt lists."""
    settings_xml = xbmcvfs.translatePath(
        "special://home/addons/plugin.video.tmdb.bingie.helper/resources/settings.xml"
    )
    if not os.path.exists(settings_xml):
        _log("TMDb Bingie Helper resources/settings.xml not found – skipping schema patch.")
        return

    try:
        tree = ET.parse(settings_xml)
        root = tree.getroot()
        changed = False
        for setting in root.findall(".//setting"):
            if setting.get("id") != "pagemulti_trakt":
                continue
            maximum = setting.find("./constraints/maximum")
            if maximum is None:
                constraints = setting.find("constraints")
                if constraints is None:
                    constraints = ET.SubElement(setting, "constraints")
                maximum = ET.SubElement(constraints, "maximum")
            if maximum.text != "13":
                maximum.text = "13"
                changed = True
            break
        if changed:
            tree.write(settings_xml, encoding="utf-8", xml_declaration=True)
            _log("TMDb Bingie Helper pagemulti_trakt schema maximum set to 13.")
    except Exception as exc:  # noqa: BLE001
        _log(f"Failed to patch TMDb Helper settings schema: {exc}", xbmc.LOGERROR)


def enable_login_screen() -> None:
    """Keep Kodi on the profile chooser instead of silently auto-entering a profile."""
    profiles_xml = xbmcvfs.translatePath("special://masterprofile/profiles.xml")
    if not xbmcvfs.exists(profiles_xml):
        _log("profiles.xml not found - skipping login screen enable.")
        return

    try:
        tree = ET.parse(profiles_xml)
        root = tree.getroot()

        login = root.find("useloginscreen")
        if login is None:
            login = ET.SubElement(root, "useloginscreen")
        autologin = root.find("autologin")
        if autologin is None:
            autologin = ET.SubElement(root, "autologin")

        changed = login.text != "true" or autologin.text != "-1"
        login.text = "true"
        autologin.text = "-1"
        if not changed:
            return

        tree.write(profiles_xml, encoding="utf-8", xml_declaration=False)
        _log("Kodi profile login screen enabled.")
    except Exception as exc:  # noqa: BLE001
        _log(f"Failed to enable profile login screen: {exc}", xbmc.LOGERROR)


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
    raise_file_descriptor_limit()
    patch_bingie_thread_limit()
    enable_login_screen()
    patch_tmdb_helper_settings_schema()
    patch_bingie_skin()
    install_seek_keymap()
    enforce_cloud_file_settings()
    enforce_macos_audio_settings()
    enforce_trailer_quality_settings()
    set_trakt_page_size()
    ensure_advanced_settings()
    sync_profile_defaults()
    enforce_video_info_button_settings()

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
        raise_file_descriptor_limit()
        patch_bingie_thread_limit()
        enable_login_screen()
        patch_tmdb_helper_settings_schema()
        enforce_cloud_file_settings()
        enforce_macos_audio_settings()
        enforce_trailer_quality_settings()
        set_trakt_page_size()
        sync_profile_defaults()
        enforce_video_info_button_settings()


if __name__ == "__main__":
    main()
