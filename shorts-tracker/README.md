# Shorts Tracker

Momentum scoring and a 2-week outlook for YouTube Shorts channels — built for the
gaming niche, works for any niche. **No YouTube API key required.**

## Quick start

```bash
# 1. Edit channels.json — put your competitors' handles in
# 2. Run (needs normal internet access to youtube.com)
python3 shorts_tracker.py

# Options
python3 shorts_tracker.py --out output/run1 --max-shorts 15
python3 shorts_tracker.py --api-key $YT_API_KEY      # exact stats via official API
python3 shorts_tracker.py --demo                     # offline test with synthetic data
python3 shorts_tracker.py --from-seed data/seed_2026-09-21.json --out output/seeded
```

Outputs land in `--out`:

| File | What it is |
|------|------------|
| `snapshot_<date>.json` | Full machine-readable snapshot (channels, shorts, metrics) |
| `shorts.csv` | Flat table — open in Excel/Sheets |
| `report_<date>.md` | Auto-summary: channel ranking + top shorts |
| `dashboard/index.html` + `data.js` | Serve with `python3 -m http.server` for the visual dashboard |
| `dashboard/dashboard_snapshot.html` | Same dashboard, data inlined — open directly, no server |

## How it works (no API key)

1. **Shorts RSS** — every channel has a generated Shorts playlist
   (`UUSH` + channel id minus `UC`); its RSS feed lists the latest ~15 shorts
   with exact publish timestamps. Handles are resolved to channel ids
   automatically (scraped from the channel's `/shorts` page).
2. **Per-video stats** — views + likes via the public Return YouTube Dislike
   API (`returnyoutubedislikeapi.com`). Pass `--api-key` to use the official
   YouTube Data API instead (exact numbers, batched 50 ids/call).
3. **Scoring** — see below. All numbers are labeled with the snapshot time
   (default `Africa/Nairobi` — change with `--tz`).

## The momentum score (0–100)

Per short: `0.55·velocity + 0.25·engagement + 0.20·recency`
- **velocity** — `log10(views/day)/6`, so 1M views/day = full marks
- **engagement** — like-rate vs a 5% benchmark (skipped when likes unknown)
- **recency** — 1.0 at upload → 0 at 30 days

Per channel: average of its 6 best recent shorts, **+ up to 8 bonus for
posting cadence** (7 ÷ median upload gap), ×0.9 if nothing posted in 3+ weeks
(“dormant”).

**14-day projection** = median views/day × 14. This is a *naive linear
extrapolation* — real Shorts decay; treat it as a rough ceiling indicator,
not a promise. Shorts younger than ~3 hours have noisy views/day.

## Swapping in your own competitors

Edit `channels.json`:

```json
{ "channels": [
  { "name": "SomeCreator", "handle": "theirhandle", "label": "what they do" }
]}
```

`channel_id` is optional — if omitted the tool resolves it from the handle.
Run on any machine with normal internet (this repo's sandbox blocks
youtube.com, so use `--demo`/`--from-seed` there). Standard library only —
Python 3.9+, nothing to pip install.

## Data files

- `data/seed_2026-09-21.json` — hand-collected live snapshot (2026-09-21,
  ~21:30 EAT) used to generate the committed `output/2026-09-21` report and
  dashboard. Views/likes came from watch pages + the public stats API;
  publish dates from Shorts RSS. Jynxzi/Dream likes are unavailable (channel
  shelf counts are rounded).
