# haze-collector

Unattended daily archive of ASMC (ASEAN Specialised Meteorological Centre) haze
products that don't self-archive anywhere else: the regional haze situation
text, daily hotspot counts for Sumatra/Kalimantan, and NOAA-20 false-color
satellite imagery for Sumatra and Kalimantan (the two regions matching
haze-replay's own FIRMS bbox -- other ASEAN regions ASMC offers are out of
scope). Built to support the
[haze-replay](https://github.com/impaural/haze-replay) project's health
banner and future citation needs.

Runs on GitHub Actions (`.github/workflows/snapshot.yml`), cron `45 9 * * *`
UTC (ASMC's own daily update cadence at Alert Level 0/1). A second cron line
for the `0300 UTC` pass ASMC adds at Alert Level 2/3 ships commented out in
the workflow, enabled manually during a live episode.

## Layout

```
data/asmc/
  YYYY-MM-DD/
    situation.html        raw capture of https://asmc.asean.org/home/
    situation.txt         extracted "Latest Weather and Haze Situation" + outlook
    hotspot_counts.json   raw response, Sumatra/Kalimantan, past 7 days, day/high-confidence
    noaa20_sumatra.jpg    NOAA-20 false-color Sumatra satellite image (page default, no AJAX)
    noaa20_kalimantan.jpg NOAA-20 false-color Kalimantan satellite image (AJAX lookup, uses
                          the page's own issueDate -- "today" is often not published yet)
  manifest.json            {last_run_utc, last_success_utc, files_captured, files[], errors[]}
```

`manifest.json` reflects only the most recent run (not a cumulative history --
the dated directories are the archive). `last_success_utc` is carried forward
unchanged on a failed run, so it always reflects the last time every source
captured cleanly.

## Failure behavior

A failed run (page structure changed, fetch error, etc.) still commits and
pushes whatever it managed to capture plus a manifest recording the error --
the Actions run shows red, but nothing is silently lost. See
`snapshot_asmc.py`'s module docstring and haze-replay's
`docs/decisions.md` (Spec Deviations) for the real-page-structure research
this was built against.

## Attribution

Captured content originates from the ASEAN Specialised Meteorological Centre
(asmc.asean.org). This repository is a private research archive, not a
redistribution product -- see haze-replay's Publication Gate before any of
this content is cited or embedded publicly.
