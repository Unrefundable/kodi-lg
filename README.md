# Kodi LG

LG remote enhancements for Kodi, installable via a Kodi add-on repository hosted on GitHub.

## Features

### 1 – OSD on Up / Down during video playback
By default, pressing **Up** or **Down** on your LG remote's navigation circle while watching a video skips forward or backward 10 minutes.  This add-on remaps those buttons to show the **OSD progress bar and pause controls** instead—the same screen you normally see by pressing OK/Select.

### 2 – Voice Search
Press the **Blue colour button** (configurable) on your LG remote to speak a movie or show name.  The add-on records audio from a microphone connected to your media player device, sends it to Google Speech recognition, and opens a TMDb Bingie Helper search with the result—no typing required.

> **Note on the LG Magic Remote microphone:** The Magic Remote's built-in mic is handled entirely by LG webOS and its audio is **not** forwarded over HDMI-CEC to connected devices.  You need a **USB microphone plugged into your Ugoos AM6B+** (or whichever device runs Kodi/CoreELEC) for voice capture to work.

---

## Install on Kodi (CoreELEC / LibreELEC / any platform)

### Step 1 – Add the repository source

1. In Kodi, go to **Settings → File Manager → Add source**.
2. Enter the URL:
   ```
   https://raw.githubusercontent.com/Unrefundable/kodi-lg/main/
   ```
3. Name the source **Kodi LG** and press **OK**.

### Step 2 – Install the repository from zip

1. Go to **Settings → Add-ons → Install from zip file**.
2. Navigate to the **Kodi LG** source you just added.
3. Open the `repository.kodi.lg/` folder.
4. Select **`repository.kodi.lg-1.0.0.zip`** and install it.
5. Wait for the *Add-on installed* notification.

### Step 3 – Install the add-on from the repository

1. Go to **Settings → Add-ons → Install from repository**.
2. Select **Kodi LG Repository**.
3. Choose **Services** → **Kodi LG** → **Install**.
4. Wait for the *Add-on installed* notification.

Kodi LG starts automatically at login and installs the keymap immediately.

---

## Configuration

Go to **Settings → Add-ons → My add-ons → Services → Kodi LG → Configure**:

| Setting | Default | Description |
|---|---|---|
| Recording duration | 5 s | How long to listen for your voice command |
| Recognition language | en-US | BCP-47 language code (e.g. `en-GB`, `fr-FR`) |
| Google Cloud Speech API key | *(blank)* | Optional. Leave blank to use the free Web Speech endpoint. Get a key from [console.cloud.google.com](https://console.cloud.google.com/) for higher rate limits. |
| Trigger button | Blue | Colour button that starts voice search |
| Up/Down shows OSD | Enabled | Toggle the playback button remap |

---

## Repository structure

```
kodi-lg/
├── addons.xml                          ← Kodi repo index
├── addons.xml.md5                      ← MD5 checksum
├── repository.kodi.lg/
│   ├── addon.xml                       ← source
│   └── repository.kodi.lg-1.0.0.zip   ← installable zip
└── service.kodi.lg/
    ├── addon.xml                       ← source
    ├── service.py                      ← background service (keymap install)
    ├── default.py                      ← voice search script
    └── resources/
        ├── keymaps/kodi_lg.xml         ← keymap overrides
        └── settings.xml
```

## Updating / rebuilding the repo

After editing source files, re-run the build script to regenerate zips and `addons.xml`:

```bash
python3 build.py
git add -A
git commit -m "bump version X.Y.Z"
git push
```

Kodi's repository checker will pick up the update automatically within 24 hours, or immediately via **Settings → Add-ons → My add-ons → Kodi LG Repository → Check for updates**.
