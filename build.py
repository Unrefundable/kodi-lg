#!/usr/bin/env python3
"""
build.py – Kodi LG repository build script.

Run this after editing any addon source file to:
  1. Rebuild the zip for each addon.
  2. Regenerate addons.xml (the Kodi repo index).
  3. Regenerate addons.xml.md5.

Usage:
  python3 build.py
"""

import hashlib
import os
import xml.etree.ElementTree as ET
import zipfile

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
ADDONS = ["repository.kodi.lg", "service.kodi.lg"]


def zip_addon(addon_id: str) -> None:
    """Zip the addon source folder into {addon_id}/{addon_id}-{version}.zip"""
    addon_dir = os.path.join(REPO_ROOT, addon_id)
    tree = ET.parse(os.path.join(addon_dir, "addon.xml"))
    version = tree.getroot().get("version")
    zip_path = os.path.join(addon_dir, f"{addon_id}-{version}.zip")

    # Remove old zip so it does not get included in the new one.
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

    print(f"  [zip] {addon_id}-{version}.zip")


def build_addons_xml() -> None:
    """Combine all addon.xml files into addons.xml and write its MD5."""
    root = ET.Element("addons")
    for addon_id in ADDONS:
        tree = ET.parse(os.path.join(REPO_ROOT, addon_id, "addon.xml"))
        root.append(tree.getroot())

    xml_str = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    xml_str += ET.tostring(root, encoding="unicode")

    addons_xml = os.path.join(REPO_ROOT, "addons.xml")
    with open(addons_xml, "w", encoding="utf-8") as fh:
        fh.write(xml_str)
    print(f"  [xml] addons.xml")

    md5 = hashlib.md5(xml_str.encode("utf-8")).hexdigest()
    with open(os.path.join(REPO_ROOT, "addons.xml.md5"), "w") as fh:
        fh.write(md5)
    print(f"  [md5] addons.xml.md5  ({md5})")


if __name__ == "__main__":
    print("Building Kodi LG repository…")
    for addon in ADDONS:
        zip_addon(addon)
    build_addons_xml()
    print("Done.  Commit and push to GitHub to publish the update.")
