"""Regression test for the 2026-07-21 Sumatra capture gap.

ASMC's satellite-polar page does not always default to NOAA-20 imagery --
on 2026-07-21 the default view served Suomi NPP (falseColor_NPP_Sumatra_...)
instead of NOAA-20 (falseColor_N20_Sumatra_...), and the scraper (which only
ever looked at the default page's inline <img>) logged "not found" even
though NOAA-20 Sumatra imagery was available that day via the same
satellite_type=N20 AJAX endpoint already used for Kalimantan.

Fixture HTML below is trimmed from real responses captured live on
2026-07-21 (see conversation/decisions for the request trail), not
synthesized -- same markup shape, irrelevant surrounding page stripped.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import snapshot_asmc  # noqa: E402

# Default satellite-polar page: today's default view is SNPP, not NOAA-20.
SATELLITE_PAGE_SNPP_DEFAULT = """
<div class="tab-pane-body">
  <div class="map-container">
    <img src="https://asmc.asean.org/files/asmc/polarorbit/snpp/falseColor_NPP_Sumatra_20260721_140106.jpg?p=1784633544" alt="satellite">
  </div>
  <input id="issueDate" type="text" class="form-control datepicker" value="21 Jul, 2026">
</div>
"""

# AJAX fragment (functions-ajax-satellite-polar.php) for satellite_type=N20, region=Sumatra.
AJAX_N20_SUMATRA = """
<input type="hidden" id="selectedType" value="N20"/>
<div class="tab-pane-body">
  <div class="map-container">
    <img src="https://asmc.asean.org/files/asmc/polarorbit/noaa20/falseColor_N20_Sumatra_20260721_140106.jpg?p=1784635187" alt="satellite">
  </div>
</div>
"""

# AJAX fragment for satellite_type=N20, region=Kali (unchanged from existing behavior).
AJAX_N20_KALIMANTAN = """
<input type="hidden" id="selectedType" value="N20"/>
<div class="tab-pane-body">
  <div class="map-container">
    <img src="https://asmc.asean.org/files/asmc/polarorbit/noaa20/falseColor_N20_Kali_20260721_140214.jpg?p=1784635200" alt="satellite">
  </div>
</div>
"""


class FakeResponse:
    def __init__(self, text="", content=b""):
        self.text = text
        self.content = content or text.encode("utf-8")


def make_fake_fetch():
    calls = []

    def fake_fetch(url, method="get", **kwargs):
        calls.append((url, method, kwargs.get("data")))
        if url == snapshot_asmc.SATELLITE_URL:
            return FakeResponse(text=SATELLITE_PAGE_SNPP_DEFAULT)
        if url == snapshot_asmc.REGION_IMAGE_AJAX_URL:
            region = kwargs["data"]["region"]
            if region == "Sumatra":
                return FakeResponse(text=AJAX_N20_SUMATRA)
            if region == "Kali":
                return FakeResponse(text=AJAX_N20_KALIMANTAN)
            raise AssertionError("unexpected region %r" % region)
        if "falseColor_N20_Sumatra_" in url:
            return FakeResponse(content=b"sumatra-n20-bytes")
        if "falseColor_N20_Kali_" in url:
            return FakeResponse(content=b"kalimantan-n20-bytes")
        raise AssertionError("unexpected URL fetched: %s" % url)

    return fake_fetch, calls


def test_capture_noaa20_images_gets_sumatra_when_default_view_is_snpp(tmp_path, monkeypatch):
    fake_fetch, calls = make_fake_fetch()
    monkeypatch.setattr(snapshot_asmc, "fetch", fake_fetch)
    monkeypatch.setattr(snapshot_asmc.time, "sleep", lambda *_: None)

    errors = []
    captured_files = []
    snapshot_asmc.capture_noaa20_images(tmp_path, errors, captured_files)

    assert errors == []
    captured_names = {f.name for f in captured_files}
    assert captured_names == {"noaa20_sumatra.jpg", "noaa20_kalimantan.jpg"}

    sumatra_path = tmp_path / "noaa20_sumatra.jpg"
    assert sumatra_path.read_bytes() == b"sumatra-n20-bytes"
    kalimantan_path = tmp_path / "noaa20_kalimantan.jpg"
    assert kalimantan_path.read_bytes() == b"kalimantan-n20-bytes"
