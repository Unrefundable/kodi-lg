#!/usr/bin/env python3
"""
build.py – Kodi LG repository build script.

Run this after editing any addon source file to:
  1. Rebuild the zip for each addon in its source subdirectory.
  2. Copy repository.kodi.lg-VERSION.zip to the repo root so Kodi's
     "Install from zip" file browser can find it directly.
  3. Regenerate addons.xml (the Kodi repo index) and its MD5.
  4. Regenerate index.html so GitHub Pages serves a Kodi-browsable
     directory listing instead of the rendered README.

How Kodi uses this layout
──────────────────────────
  File Manager source URL : https://unrefundable.github.io/kodi-lg/
  │
  ├─ index.html                        ← browsed by Kodi to show zip list
  ├─ repository.kodi.lg-X.Y.Z.zip     ← STEP 1: user installs this via
  │                                         "Install from zip file"
  ├─ addons.xml                        ← fetched directly after repo install
  ├─ addons.xml.md5
  └─ service.kodi.lg/
      └─ service.kodi.lg-X.Y.Z.zip   ← STEP 2: installed via
                                            "Install from repository"

Usage:
  python3 build.py
"""

import hashlib
import os
import shutil
import xml.etree.ElementTree as ET
import zipfile

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
REPO_ADDON_ID = "repository.kodi.lg"
ADDON_IDS = [REPO_ADDON_ID, "service.kodi.lg"]
PAGES_URL = "https://unrefundable.github.io/kodi-lg"


def zip_addon(addon_id: str) -> str:
    """
    Zip the addon source folder into {addon_id}/{addon_id}-{version}.zip.
    Returns the full path of the created zip.
    """
    addon_dir = os.path.join(REPO_ROOT, addon_id)
    tree = ET.parse(os.path.join(addon_dir, "addon.xml"))
    version = tree.getroot().get("version")
    zip_path = os.path.join(addon_dir, f"{addon_id}-{version}.zip")

    # Remove old zip so it is not included in the new one.
    if os.path.exists(zip_path):
        os.remove(zip_path)

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(addon_dir):
            dirs[:] = [d for d in dirs if d not in {"__pycache__", ".git"}]
            for fname in files:
                if fname.endswith(".zip"):
                    continue
                fpath = os.path.join(root, fname)
                arcname = os.path.relpath(fpath, REPO_ROOT)
                zf.write(fpath, arcname)

    print(f"  [zip] {addon_id}/{addon_id}-{version}.zip")
    return zip_path


def copy_repo_zip_to_root(repo_zip_path: str) -> str:
    """
    Copy repository.kodi.lg-VERSION.zip to the repository root so Kodi's
    'Install from zip file' browser can find it at the top level.
    Returns the root-level zip filename.
    """
    filename = os.path.basename(repo_zip_path)
    dest = os.path.join(REPO_ROOT, filename)
    shutil.copy2(repo_zip_path, dest)
    print(f"  [root] {filename}  (copied to root for 'Install from zip')")
    return filename


def build_addons_xml() -> None:
    """Combine all addon.xml files into addons.xml and write its MD5."""
    root_el = ET.Element("addons")
    for addon_id in ADDON_IDS:
        tree = ET.parse(os.path.join(REPO_ROOT, addon_id, "addon.xml"))
        root_el.append(tree.getroot())

    xml_str = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    xml_str += ET.tostring(root_el, encoding="unicode")

    addons_xml = os.path.join(REPO_ROOT, "addons.xml")
    with open(addons_xml, "w", encoding="utf-8") as fh:
        fh.write(xml_str)
    print(f"  [xml] addons.xml")

    md5 = hashlib.md5(xml_str.encode("utf-8")).hexdigest()
    with open(os.path.join(REPO_ROOT, "addons.xml.md5"), "w") as fh:
        fh.write(md5)
    print(f"  [md5] addons.xml.md5  ({md5})")


def build_index_html(repo_zip_filename: str) -> None:
    """
    Generate index.html at the repo root.

    GitHub Pages serves this instead of rendering README.md.  The page
    contains a single <a href> link to the repository zip so that
    Kodi's file browser shows only that file when the user navigates
    to the source URL via Install from zip.
    """
    html = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>Kodi LG Repository</title></head>
<body>
<a href="{repo_zip_filename}">{repo_zip_filename}</a>
</body>
</html>
"""

    index_path = os.path.join(REPO_ROOT, "index.html")
    with open(index_path, "w", encoding="utf-8") as fh:
        fh.write(html)
    print(f"  [html] index.html")


# ── Remove any stale root-level repository zips from previous runs ──────── #
def _clean_old_root_zips() -> None:
    for fname in os.listdir(REPO_ROOT):
        if fname.startswith("repository.kodi.lg-") and fname.endswith(".zip"):
            os.remove(os.path.join(REPO_ROOT, fname))


if __name__ == "__main__":
    print("Building Kodi LG repository…")
    _clean_old_root_zips()
    repo_zip = None
    for addon_id in ADDON_IDS:
        path = zip_addon(addon_id)
        if addon_id == REPO_ADDON_ID:
            repo_zip = path
    root_zip_name = copy_repo_zip_to_root(repo_zip)
    build_addons_xml()
    build_index_html(root_zip_name)
    print("Done.  Commit and push to GitHub to publish the update.")
