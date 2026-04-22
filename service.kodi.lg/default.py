"""
Kodi LG – default.py
Voice search entry point.

Called by the keymap via:  RunScript(service.kodi.lg)

Flow
────
1. Show "Listening…" toast notification for the configured duration.
2. Record audio from the default ALSA capture device (arecord).
3. Send the raw PCM audio to Google's Web Speech API for transcription.
4. Show the recognised text in a Yes/No dialog so the user can confirm.
5. Navigate to TMDb Bingie Helper search with the recognised query, which
   shows both movie and TV results powered by TMDb.

Requirements on the device (CoreELEC / LibreELEC / Linux)
──────────────────────────────────────────────────────────
• A microphone recognised by ALSA (USB mic plugged into the Ugoos AM6B+).
• Internet access for Google Speech recognition.
• script.module.requests must be installed (listed as a dependency).

Note on the LG Magic Remote microphone
──────────────────────────────────────
The LG Magic Remote's built-in microphone is handled entirely by LG webOS
and its audio data is NOT forwarded over HDMI-CEC to connected devices.
Voice capture therefore requires a separate microphone on the Kodi device.
"""

import json
import os
import subprocess
import sys
import tempfile
import time

import xbmc
import xbmcaddon
import xbmcgui

# ── Bootstrap ─────────────────────────────────────────────────────────────── #
_ADDON = xbmcaddon.Addon()
_ADDON_ID = _ADDON.getAddonInfo("id")

# Google Web Speech API v2 – public research key (no sign-up required).
# Rate-limited; suitable for personal use.  The user can supply a proper
# Google Cloud Speech-to-Text API key in the add-on settings for a more
# reliable experience.
_GOOGLE_WEB_SPEECH_URL = (
    "https://www.google.com/speech-api/v2/recognize"
    "?output=json&lang={lang}&key=AIzaSyBOti4mM-6x9WDnZIjIeyEU21OpBXqWBgY"
)
_GOOGLE_CLOUD_SPEECH_URL = (
    "https://speech.googleapis.com/v1/speech:recognize?key={api_key}"
)

# Skin integration
# The Bingie skin search window watches Skin.String(CustomSearchTerm).
# Setting it via a built-in updates the live search results immediately
# without leaving the search window or showing a separate browser window.

_TMP_AUDIO = os.path.join(tempfile.gettempdir(), "kodi_lg_voice.raw")

# Skin string key used by the Bingie search window to drive live results.
_SKIN_SEARCH_KEY = "CustomSearchTerm"


# ── Helpers ───────────────────────────────────────────────────────────────── #

def _log(msg: str, level: int = xbmc.LOGINFO) -> None:
    xbmc.log(f"[{_ADDON_ID}] {msg}", level)


def _addon() -> xbmcaddon.Addon:
    """Return a fresh Addon instance so settings are always current."""
    return xbmcaddon.Addon()


def _setting(key: str, default: str = "") -> str:
    val = _addon().getSetting(key)
    return val if val else default


def _setting_int(key: str, default: int = 0) -> int:
    try:
        return int(_addon().getSetting(key) or default)
    except (ValueError, TypeError):
        return default


# ── Audio recording ───────────────────────────────────────────────────────── #

def record_audio(duration: int, sample_rate: int = 16000) -> bool:
    """
    Record *duration* seconds of 16-bit mono PCM at *sample_rate* Hz using
    arecord (ALSA).  The raw PCM data is written to _TMP_AUDIO.

    Returns True on success, False on any error.
    """
    cmd = [
        "arecord",
        "-d", str(duration),   # recording duration in seconds
        "-f", "S16_LE",        # 16-bit signed little-endian
        "-r", str(sample_rate),
        "-c", "1",             # mono
        _TMP_AUDIO,
    ]
    _log(f"Recording {duration}s of audio: {' '.join(cmd)}")
    try:
        result = subprocess.run(
            cmd,
            timeout=duration + 5,
            capture_output=True,
        )
        if result.returncode != 0:
            _log(
                f"arecord exited {result.returncode}: "
                f"{result.stderr.decode(errors='replace')}",
                xbmc.LOGERROR,
            )
            return False
        size = os.path.getsize(_TMP_AUDIO)
        if size == 0:
            _log("Recorded file is empty.", xbmc.LOGERROR)
            return False
        _log(f"Recorded {size} bytes of audio.")
        return True
    except FileNotFoundError:
        _log(
            "arecord not found.  Ensure ALSA tools are installed on the device.",
            xbmc.LOGERROR,
        )
        return False
    except subprocess.TimeoutExpired:
        _log("arecord timed out.", xbmc.LOGERROR)
        return False
    except Exception as exc:  # noqa: BLE001
        _log(f"Unexpected record error: {exc}", xbmc.LOGERROR)
        return False


# ── Speech recognition ────────────────────────────────────────────────────── #

def _transcribe_web_speech(lang: str, sample_rate: int = 16000) -> str | None:
    """
    Send raw PCM to the Google Web Speech API (no API key required).
    Returns the top hypothesis transcript, or None on failure.
    """
    import requests  # bundled via script.module.requests

    url = _GOOGLE_WEB_SPEECH_URL.format(lang=lang)
    headers = {"Content-Type": f"audio/l16;rate={sample_rate}"}

    try:
        with open(_TMP_AUDIO, "rb") as fh:
            audio_data = fh.read()
        resp = requests.post(url, data=audio_data, headers=headers, timeout=15)
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        _log(f"Web Speech API request failed: {exc}", xbmc.LOGERROR)
        return None

    # The API returns multiple JSON lines; find the first non-empty result.
    for line in resp.text.strip().splitlines():
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        for result in data.get("result", []):
            alternatives = result.get("alternative", [])
            if alternatives:
                text = alternatives[0].get("transcript", "").strip()
                if text:
                    _log(f"Recognised (web): '{text}'")
                    return text
    _log("Web Speech API returned no transcript.", xbmc.LOGWARNING)
    return None


def _transcribe_cloud_speech(api_key: str, lang: str, sample_rate: int = 16000) -> str | None:
    """
    Send raw PCM to Google Cloud Speech-to-Text v1 (requires a valid API key).
    Returns the top alternative transcript, or None on failure.
    """
    import base64

    import requests  # bundled via script.module.requests

    url = _GOOGLE_CLOUD_SPEECH_URL.format(api_key=api_key)
    try:
        with open(_TMP_AUDIO, "rb") as fh:
            audio_b64 = base64.b64encode(fh.read()).decode()
    except Exception as exc:  # noqa: BLE001
        _log(f"Failed to read audio file: {exc}", xbmc.LOGERROR)
        return None

    body = {
        "config": {
            "encoding": "LINEAR16",
            "sampleRateHertz": sample_rate,
            "languageCode": lang,
        },
        "audio": {"content": audio_b64},
    }
    try:
        resp = requests.post(url, json=body, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        _log(f"Cloud Speech API request failed: {exc}", xbmc.LOGERROR)
        return None

    try:
        text = data["results"][0]["alternatives"][0]["transcript"].strip()
        _log(f"Recognised (cloud): '{text}'")
        return text
    except (KeyError, IndexError):
        _log("Cloud Speech API returned no transcript.", xbmc.LOGWARNING)
        return None


def transcribe(sample_rate: int = 16000) -> str | None:
    """
    Transcribe _TMP_AUDIO.  Uses Google Cloud Speech if an API key is set in
    the add-on settings, otherwise falls back to the public Web Speech API.
    """
    lang = _setting("voice_language", "en-US")
    api_key = _setting("google_api_key", "")

    if api_key:
        result = _transcribe_cloud_speech(api_key, lang, sample_rate)
        if result:
            return result
        _log("Cloud Speech failed; falling back to Web Speech API.", xbmc.LOGWARNING)

    return _transcribe_web_speech(lang, sample_rate)


# ── Search navigation ─────────────────────────────────────────────────────── #

def apply_search_query(query: str) -> None:
    """
    Populate the Bingie skin search box with *query*.

    Sets Skin.String(CustomSearchTerm) which the Bingie search window watches
    to populate its results containers in real time — no window navigation
    required.  Also fires SetProperty(CustomSearch,1,home) which resets the
    search pagination state the same way the skin's own keyboard does.
    """
    _log(f"Applying search query to skin: '{query}'")
    # Escape any single-quotes in the text so the built-in call is safe.
    safe_query = query.replace("'", "\\'")
    xbmc.executebuiltin(f"Skin.SetString({_SKIN_SEARCH_KEY},{safe_query})")
    xbmc.executebuiltin("SetProperty(CustomSearch,1,home)")


# ── Main voice search flow ────────────────────────────────────────────────── #

def voice_search() -> None:
    dialog = xbmcgui.Dialog()
    duration = _setting_int("record_seconds", 5)
    sample_rate = 16000

    # ── Step 1: Tell the user we are listening ──────────────────────────── #
    xbmcgui.Dialog().notification(
        "Kodi LG – Voice Search",
        f"Listening\u2026 speak the movie or show name ({duration}s)",
        xbmcgui.NOTIFICATION_INFO,
        (duration + 2) * 1000,
        sound=False,
    )

    # ── Step 2: Record ──────────────────────────────────────────────────── #
    if not record_audio(duration, sample_rate):
        dialog.notification(
            "Kodi LG – Voice Search",
            "Could not record audio.\nCheck microphone connection.",
            xbmcgui.NOTIFICATION_ERROR,
            5000,
        )
        return

    # ── Step 3: Transcribe ──────────────────────────────────────────────── #
    xbmcgui.Dialog().notification(
        "Kodi LG – Voice Search",
        "Recognising speech\u2026",
        xbmcgui.NOTIFICATION_INFO,
        3000,
        sound=False,
    )
    text = transcribe(sample_rate)
    if not text:
        dialog.notification(
            "Kodi LG – Voice Search",
            "Could not recognise speech.\nPlease try again.",
            xbmcgui.NOTIFICATION_WARNING,
            5000,
        )
        return

    # ── Step 4: Confirm with user ───────────────────────────────────────── #
    confirmed = dialog.yesno(
        "Kodi LG – Voice Search",
        f'You said:[CR][B]{text}[/B][CR][CR]Search for this?',
    )
    if not confirmed:
        return

    # ── Step 5: Set the search query in the skin ────────────────────────── #
    apply_search_query(text)


# ── Seek accumulator IPC ─────────────────────────────────────────────────── #
# The service's background thread watches these home-window properties and
# executes ONE seekTime() call 1.5 s after the last button press.

_HOME_WIN = xbmcgui.Window(10000)
_PROP_DIR   = "KodiLG_SeekDir"    # "1" = forward, "-1" = back
_PROP_COUNT = "KodiLG_SeekCount"  # number of presses accumulated
_PROP_TIME  = "KodiLG_SeekTime"   # time.time() of last press (string)


def _handle_seek(direction: int) -> None:
    """Record one FF/RW press into the shared window properties.

    The service loop reads these and executes the actual seek once the
    button has been released for SEEK_COMMIT_DELAY seconds.
    """
    prev_dir   = _HOME_WIN.getProperty(_PROP_DIR)
    prev_count = int(_HOME_WIN.getProperty(_PROP_COUNT) or "0")

    # If direction changed, reset counter.
    if prev_dir and int(prev_dir) != direction:
        prev_count = 0

    _HOME_WIN.setProperty(_PROP_DIR,   str(direction))
    _HOME_WIN.setProperty(_PROP_COUNT, str(prev_count + 1))
    _HOME_WIN.setProperty(_PROP_TIME,  str(time.time()))


if __name__ == "__main__":
    # Parse arguments: RunScript(service.kodi.lg,action=seek_forward) etc.
    args = {}
    for part in sys.argv[1:]:
        if "=" in part:
            k, v = part.split("=", 1)
            args[k.strip()] = v.strip()

    action = args.get("action", "")

    if action == "seek_forward":
        _handle_seek(1)
    elif action == "seek_back":
        _handle_seek(-1)
    else:
        # Default: voice search
        voice_search()
