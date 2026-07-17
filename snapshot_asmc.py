#!/usr/bin/env python
"""Daily snapshot of ASMC products that don't self-archive: the regional haze
situation text, daily hotspot counts (Sumatra/Kalimantan), and NOAA-20
false-color Sumatra satellite imagery. Runs unattended on GitHub Actions
(.github/workflows/snapshot.yml, cron 45 9 * * * UTC).

Page structure verified live 2026-07-17 (see haze-replay docs/decisions.md
Spec Deviations for the full research trail). No third-party HTML-parsing
deps: html.parser (stdlib) only, per the requests-only dependency rule.
"""
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

import requests

VERSION = "1.0.0"
HOME_URL = "https://asmc.asean.org/home/"
SATELLITE_URL = "https://asmc.asean.org/satellite-polar/"
HOTSPOT_COUNT_URL = (
    "https://asmc.asean.org/wp-content/themes/asmctheme/page-functions/"
    "functions-ajax-haze-daily-hotspot-count-new.php"
)
USER_AGENT = (
    "haze-collector/1.0 (+https://github.com/impaural/haze-collector; "
    "unattended daily research snapshot, 1x/day)"
)
MIN_SITUATION_TEXT_LENGTH = 40
TIMEOUT = 30
POLITENESS_SLEEP_SECONDS = 1

REPO_ROOT = Path(__file__).resolve().parent
DATA_DIR = REPO_ROOT / "data" / "asmc"
MANIFEST_PATH = DATA_DIR / "manifest.json"


def log(level, msg):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print("[%s] [%s] %s" % (ts, level, msg))


def utc_now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_of(path):
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def fetch(url, method="get", **kwargs):
    headers = kwargs.pop("headers", {})
    headers["User-Agent"] = USER_AGENT
    resp = requests.request(method, url, headers=headers, timeout=TIMEOUT, **kwargs)
    resp.raise_for_status()
    return resp


def check_reachable(url):
    try:
        requests.head(url, headers={"User-Agent": USER_AGENT}, timeout=10, allow_redirects=True)
        return True
    except requests.RequestException:
        return False


class SituationExtractor(HTMLParser):
    """Extracts the 'Latest Weather and Haze Situation' narrative (p#myContent)
    and the 'Weather and Haze Outlook' paragraph (p#WHoutlook) from the ASMC
    home page. Both ids are stable template markers, not content that varies
    day to day. The situation narrative is pure text with no nested tags, so
    ANY start tag encountered while capturing it marks the end of that field
    -- robust to the page's malformed nested-<p> markup without needing to
    match specific style/label text.
    """

    def __init__(self):
        super().__init__()
        self.situation_parts = []
        self.outlook_parts = []
        self._capture = None  # None | "situation" | "outlook"

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        tag_id = attrs_dict.get("id", "")
        if tag_id == "myContent":
            self._capture = "situation"
            return
        if tag_id == "WHoutlook":
            self._capture = "outlook"
            return
        if self._capture == "situation":
            self._capture = None

    def handle_endtag(self, tag):
        if self._capture == "outlook" and tag == "p":
            self._capture = None

    def handle_data(self, data):
        if self._capture == "situation":
            self.situation_parts.append(data)
        elif self._capture == "outlook":
            self.outlook_parts.append(data)

    @property
    def situation_text(self):
        return " ".join("".join(self.situation_parts).split())

    @property
    def outlook_text(self):
        return " ".join("".join(self.outlook_parts).split())


class Noaa20ImageFinder(HTMLParser):
    """Finds the NOAA-20 false-color Sumatra <img src> on the satellite page
    (defaults to today's image on first load, matching what a human visitor
    sees)."""

    def __init__(self):
        super().__init__()
        self.image_url = None

    def handle_starttag(self, tag, attrs):
        if self.image_url or tag != "img":
            return
        src = dict(attrs).get("src", "")
        if "/polarorbit/noaa20/falseColor_N20_Sumatra_" in src:
            self.image_url = src


def capture_situation(out_dir, errors, captured_files):
    try:
        resp = fetch(HOME_URL)
    except requests.RequestException as exc:
        errors.append("home page fetch failed: %s" % exc)
        return
    html = resp.text
    situation_path = out_dir / "situation.html"
    situation_path.write_text(html, encoding="utf-8")
    captured_files.append(situation_path)

    extractor = SituationExtractor()
    extractor.feed(html)
    situation_text = extractor.situation_text
    outlook_text = extractor.outlook_text

    if len(situation_text) < MIN_SITUATION_TEXT_LENGTH:
        errors.append(
            "situation text extraction failed: only %d chars (< %d floor), "
            "page structure may have changed" % (len(situation_text), MIN_SITUATION_TEXT_LENGTH)
        )
        return

    combined = situation_text
    if outlook_text:
        combined += "\n\nWeather and Haze Outlook: " + outlook_text
    text_path = out_dir / "situation.txt"
    text_path.write_text(combined, encoding="utf-8")
    captured_files.append(text_path)


def capture_hotspot_counts(out_dir, errors, captured_files):
    try:
        date_str = datetime.now(timezone.utc).strftime("%d %b, %Y").lstrip("0")
        resp = fetch(
            HOTSPOT_COUNT_URL,
            method="post",
            data={
                "date": date_str,
                "pastDays": "7",
                "regions[]": ["Sumatra", "Kalimantan"],
                "daynight": "day",
                "conf": "High",
            },
        )
    except requests.RequestException as exc:
        errors.append("hotspot count fetch failed: %s" % exc)
        return
    counts_path = out_dir / "hotspot_counts.json"
    counts_path.write_text(resp.text, encoding="utf-8")
    captured_files.append(counts_path)


def capture_noaa20_image(out_dir, errors, captured_files):
    try:
        sat_resp = fetch(SATELLITE_URL)
    except requests.RequestException as exc:
        errors.append("satellite page fetch failed: %s" % exc)
        return
    finder = Noaa20ImageFinder()
    finder.feed(sat_resp.text)
    if finder.image_url is None:
        errors.append("NOAA-20 image URL not found on satellite page (page structure changed)")
        return
    try:
        img_resp = fetch(finder.image_url)
    except requests.RequestException as exc:
        errors.append("NOAA-20 image fetch failed: %s" % exc)
        return
    image_path = out_dir / "noaa20_sumatra.jpg"
    image_path.write_bytes(img_resp.content)
    captured_files.append(image_path)


def write_manifest(captured_files, errors, now_iso):
    previous_last_success = None
    if MANIFEST_PATH.exists():
        try:
            previous = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
            previous_last_success = previous.get("last_success_utc")
        except (json.JSONDecodeError, OSError):
            previous_last_success = None

    manifest = {
        "last_run_utc": now_iso,
        "last_success_utc": now_iso if not errors else previous_last_success,
        "files_captured": len(captured_files),
        "files": [
            {"path": f.relative_to(REPO_ROOT).as_posix(), "sha256": sha256_of(f)}
            for f in captured_files
        ],
        "errors": errors,
    }
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def main():
    reachable = check_reachable(HOME_URL)
    log("INFO", "Boot complete (snapshot_asmc.py v%s) config_url_reachable=%s" % (VERSION, reachable))

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_dir = DATA_DIR / today
    out_dir.mkdir(parents=True, exist_ok=True)
    log("INFO", "run start: out_dir=%s" % out_dir.relative_to(REPO_ROOT).as_posix())

    errors = []
    captured_files = []

    capture_situation(out_dir, errors, captured_files)
    time.sleep(POLITENESS_SLEEP_SECONDS)
    capture_hotspot_counts(out_dir, errors, captured_files)
    time.sleep(POLITENESS_SLEEP_SECONDS)
    capture_noaa20_image(out_dir, errors, captured_files)

    now_iso = utc_now_iso()
    write_manifest(captured_files, errors, now_iso)

    for err in errors:
        log("ERROR", err)
    log("INFO", "run complete: files_captured=%d errors=%d" % (len(captured_files), len(errors)))

    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
