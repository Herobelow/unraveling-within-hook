#!/usr/bin/env python3
"""
Shorts Tracker — momentum scoring & 2-week outlook for YouTube Shorts channels.

No API key required. Data sources:
  1. Channel "Shorts" RSS playlist (UUSH...) -> recent shorts + publish dates.
  2. Return YouTube Dislike API (public)     -> views + likes per video.
  3. Optional: official YouTube Data API v3  -> pass --api-key for exact stats.

Usage:
  python3 shorts_tracker.py                          # run with channels.json
  python3 shorts_tracker.py --config my.json --out output/run1
  python3 shorts_tracker.py --demo                   # offline sample run
  python3 shorts_tracker.py --from-seed data/seed.json --out output/seeded

Outputs (in --out dir):
  snapshot.json / snapshot_<date>.json   full machine-readable snapshot
  shorts.csv                             flat table of every short
  report_<date>.md                       auto-generated summary
  dashboard/data.js + dashboard_snapshot.html  dashboard bundle

Metrics are heuristics (views/day, like-rate, cadence) — see README for
how the momentum score is computed. Projections are naive linear
extrapolations, not guarantees.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import random
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
RSS_NS = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}


# --------------------------------------------------------------------------- #
#  HTTP helpers
# --------------------------------------------------------------------------- #
def http_get(url: str, timeout: int = 25, retries: int = 2) -> str:
    last = None
    for attempt in range(retries + 1):
        try:
            req = urlrequest.Request(url, headers={"User-Agent": UA, "Accept-Language": "en"})
            with urlrequest.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except (HTTPError, URLError, TimeoutError) as exc:  # noqa: PERF203
            last = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"GET failed for {url}: {last}")


def resolve_channel_id(handle: str) -> str:
    """Resolve @handle -> UCxxxx channel id using the /shorts page's
    analytics pixel (utuid=...). Works without an API key."""
    handle = handle.lstrip("@")
    html = http_get(f"https://www.youtube.com/@{handle}/shorts")
    m = re.search(r"utuid%3D([\w-]{22})|utuid=([\w-]{22})", html)
    if not m:
        raise RuntimeError(f"Could not resolve channel id for @{handle}")
    return "UC" + (m.group(1) or m.group(2))


def shorts_playlist_id(channel_id: str) -> str:
    """Every channel has generated playlist ids: UUSH<22chars> = its Shorts."""
    return "UUSH" + channel_id[2:]


def fetch_rss_videos(playlist_id: str) -> list[dict]:
    """Parse a YouTube RSS feed into [{id, title, published}]."""
    xml = http_get(f"https://www.youtube.com/feeds/videos.xml?playlist_id={playlist_id}")
    root = ET.fromstring(xml)
    out = []
    for entry in root.findall("a:entry", RSS_NS):
        vid = entry.findtext("yt:videoId", default="", namespaces=RSS_NS)
        title = entry.findtext("a:title", default="", namespaces=RSS_NS)
        pub = entry.findtext("a:published", default="", namespaces=RSS_NS)
        if vid and pub:
            out.append({
                "id": vid,
                "title": title,
                "published": datetime.fromisoformat(pub.replace("Z", "+00:00")),
            })
    return out


def fetch_stats_ryd(video_ids: list[str]) -> dict[str, dict]:
    """Views/likes via the public Return YouTube Dislike API."""
    stats = {}
    for vid in video_ids:
        try:
            data = json.loads(http_get(
                f"https://returnyoutubedislikeapi.com/votes?videoId={vid}", timeout=20))
            stats[vid] = {
                "views": data.get("viewCount"),
                "likes": data.get("likes"),
            }
        except (RuntimeError, ValueError) as exc:
            print(f"    ! RYD failed for {vid}: {exc}", file=sys.stderr)
        time.sleep(0.35)
    return stats


def fetch_stats_api(api_key: str, video_ids: list[str]) -> dict[str, dict]:
    """Exact stats via official YouTube Data API (batched, 50 ids/call)."""
    stats: dict[str, dict] = {}
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i + 50]
        url = ("https://www.googleapis.com/youtube/v3/videos?part=statistics"
               f"&id={','.join(batch)}&key={api_key}")
        data = json.loads(http_get(url))
        for item in data.get("items", []):
            s = item.get("statistics", {})
            stats[item["id"]] = {
                "views": int(s.get("viewCount", 0)) or None,
                "likes": int(s.get("likeCount", 0)) or None,
            }
    return stats


# --------------------------------------------------------------------------- #
#  Metrics
# --------------------------------------------------------------------------- #
def short_metrics(video: dict, now: datetime) -> dict:
    age_days = max((now - video["published"]).total_seconds() / 86400.0, 0.02)
    views = video.get("views")
    likes = video.get("likes")
    vpd = views / age_days if views else None
    like_rate = (likes / views) if (likes and views) else None

    vel = min(1.0, math.log10(1 + vpd) / 6.0) if vpd else 0.0          # 1M/day -> 1.0
    rec = max(0.0, 1.0 - age_days / 30.0)
    eng = min(1.0, like_rate / 0.05) if like_rate is not None else None  # 5% -> 1.0
    if eng is None:
        score = 100.0 * (0.65 * vel + 0.35 * rec)
    else:
        score = 100.0 * (0.55 * vel + 0.25 * eng + 0.20 * rec)

    return {
        **video,
        "published": video["published"].isoformat(),
        "age_days": round(age_days, 2),
        "views": views,
        "likes": likes,
        "views_per_day": round(vpd) if vpd else None,
        "like_rate": round(like_rate, 5) if like_rate is not None else None,
        "score": round(score, 1),
        "url": f"https://www.youtube.com/shorts/{video['id']}",
    }


def channel_metrics(shorts: list[dict], now: datetime) -> dict:
    dates = sorted(datetime.fromisoformat(s["published"]) for s in shorts)
    # Cadence from median gap between consecutive uploads (per-week rate)
    gaps = [(dates[i + 1] - dates[i]).total_seconds() / 86400.0
            for i in range(len(dates) - 1)]
    gaps = [g for g in gaps if g > 0]
    cadence = min(10.0, 7.0 / sorted(gaps)[len(gaps) // 2]) if gaps else 10.0
    newest_age = (now - dates[-1]).days
    dormant = newest_age > 21          # nothing posted in 3+ weeks
    if dormant:
        cadence = min(cadence, 0.5)

    recent = [s for s in shorts if (now - datetime.fromisoformat(s["published"])).days <= 30]
    pool = recent or shorts
    vpds = [s["views_per_day"] for s in pool if s["views_per_day"]]
    scores = [s["score"] for s in pool]

    momentum = sum(scores[:6]) / min(6, len(scores)) if scores else 0.0
    momentum = min(100.0, momentum + min(8.0, cadence))  # posting-cadence bonus
    if dormant:
        momentum *= 0.9
    median_vpd = sorted(vpds)[len(vpds) // 2] if vpds else 0
    momentum = round(momentum, 1)

    if momentum >= 70:
        status = "SURGING"
    elif momentum >= 55:
        status = "HOT"
    elif momentum >= 35:
        status = "STEADY"
    else:
        status = "COOLING"
    if dormant:
        status += " · dormant"

    return {
        "momentum": momentum,
        "status": status,
        "shorts_per_week": round(cadence, 1),
        "median_views_per_day": median_vpd,
        "projection_14d_per_short": median_vpd * 14,
        "best_short": max(shorts, key=lambda s: s["views"] or 0),
    }


# --------------------------------------------------------------------------- #
#  Output writers
# --------------------------------------------------------------------------- #
def fmt(n) -> str:
    if n is None:
        return "-"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}K"
    return str(int(n))


def write_outputs(out_dir: str, now: datetime, channels: list[dict], tz_name: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    date_tag = now.strftime("%Y-%m-%d")

    # JSON snapshot
    snapshot = {
        "generated_at": now.isoformat(),
        "timezone": tz_name,
        "method": "RSS + ReturnYouTubeDislike (no API key)",
        "disclaimer": "Momentum scores and 14-day projections are heuristic "
                      "linear extrapolations of observed views/day — not guarantees.",
        "channels": channels,
    }
    json_path = os.path.join(out_dir, f"snapshot_{date_tag}.json")
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(snapshot, fh, indent=2, ensure_ascii=False)
    with open(os.path.join(out_dir, "snapshot.json"), "w", encoding="utf-8") as fh:
        json.dump(snapshot, fh, indent=2, ensure_ascii=False)

    # CSV
    csv_path = os.path.join(out_dir, "shorts.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["channel", "video_id", "title", "published", "age_days",
                    "views", "likes", "views_per_day", "like_rate", "score", "url"])
        for ch in channels:
            for s in ch["shorts"]:
                w.writerow([ch["name"], s["id"], s["title"], s["published"], s["age_days"],
                            s["views"], s["likes"], s["views_per_day"], s["like_rate"],
                            s["score"], s["url"]])

    # Markdown report
    ranked = sorted(channels, key=lambda c: -c["metrics"]["momentum"])
    md = [f"# Shorts momentum snapshot — {now.strftime('%Y-%m-%d %H:%M')} ({tz_name})", ""]
    md.append("| # | Channel | Momentum | Status | Median views/day | 14-day proj./short | Shorts/wk |")
    md.append("|---|---------|----------|--------|------------------|--------------------|-----------|")
    for i, ch in enumerate(ranked, 1):
        m = ch["metrics"]
        md.append(f"| {i} | {ch['name']} | {m['momentum']} | {m['status']} | "
                  f"{fmt(m['median_views_per_day'])} | {fmt(m['projection_14d_per_short'])} | "
                  f"{m['shorts_per_week']} |")
    md += ["", "## Top shorts by momentum score", ""]
    all_shorts = sorted(((s, ch) for ch in channels for s in ch["shorts"]),
                        key=lambda p: -p[0]["score"])[:15]
    for s, ch in all_shorts:
        md.append(f"- **{s['score']}** — [{s['title']}]({s['url']}) · {ch['name']} · "
                  f"{fmt(s['views'])} views · {fmt(s['views_per_day'])}/day · {s['age_days']}d old")
    md_path = os.path.join(out_dir, f"report_{date_tag}.md")
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")

    # Dashboard bundle
    dash_dir = os.path.join(out_dir, "dashboard")
    os.makedirs(dash_dir, exist_ok=True)
    leaderboard = sorted(all_shorts, key=lambda p: -p[0]["score"])[:10]
    data_js = {
        **snapshot,
        "leaderboard": [
            {"channel": ch["name"], **{k: s[k] for k in
             ("id", "title", "views", "views_per_day", "score", "age_days", "url")}}
            for s, ch in leaderboard
        ],
    }
    with open(os.path.join(dash_dir, "data.js"), "w", encoding="utf-8") as fh:
        fh.write("window.SHORTS_DATA = " + json.dumps(data_js, ensure_ascii=False) + ";\n")

    template = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "dashboard", "index.html")

    # Serve-ready copy of the dashboard shell (reads data.js at runtime)
    if os.path.exists(template):
        with open(template, encoding="utf-8") as fh:
            shell = fh.read()
        with open(os.path.join(dash_dir, "index.html"), "w", encoding="utf-8") as fh:
            fh.write(shell)

    # Self-contained snapshot (data inlined) for offline viewing
    if os.path.exists(template):
        with open(template, encoding="utf-8") as fh:
            html = fh.read()
        inline = ("<script>window.SHORTS_DATA = "
                  + json.dumps(data_js, ensure_ascii=False) + ";</script>")
        html = html.replace('<script src="data.js"></script>', inline)
        with open(os.path.join(dash_dir, "dashboard_snapshot.html"), "w", encoding="utf-8") as fh:
            fh.write(html)

    print(f"  ✓ wrote {json_path}\n  ✓ wrote {csv_path}\n  ✓ wrote {md_path}\n"
          f"  ✓ wrote {dash_dir}/data.js + dashboard_snapshot.html")
    return md_path


# --------------------------------------------------------------------------- #
#  Modes
# --------------------------------------------------------------------------- #
def collect_live(cfg: dict, args) -> tuple[list[dict], datetime]:
    now = datetime.now(timezone.utc)
    channels = []
    for ch in cfg["channels"]:
        name = ch.get("name", ch.get("handle", "?"))
        print(f"→ {name}")
        cid = ch.get("channel_id")
        if not cid:
            cid = resolve_channel_id(ch["handle"])
            print(f"    resolved @{ch['handle']} -> {cid}")
        try:
            vids = fetch_rss_videos(shorts_playlist_id(cid))[:args.max_shorts]
        except RuntimeError:
            print("    ! Shorts playlist failed, falling back to channel feed", file=sys.stderr)
            vids = fetch_rss_videos(cid)[:args.max_shorts]
        if not vids:
            print("    ! no videos found, skipping", file=sys.stderr)
            continue
        ids = [v["id"] for v in vids]
        stats = {}
        if args.api_key:
            stats = fetch_stats_api(args.api_key, ids)
        elif not args.no_enrich:
            stats = fetch_stats_ryd(ids)
        shorts = []
        for v in vids:
            v.update(stats.get(v["id"], {}))
            shorts.append(short_metrics(v, now))
        shorts.sort(key=lambda s: s["published"], reverse=True)
        channels.append({"name": name, "handle": ch.get("handle"), "label": ch.get("label", ""),
                         "channel_id": cid, "shorts": shorts,
                         "metrics": channel_metrics(shorts, now)})
        print(f"    {len(shorts)} shorts, momentum {channels[-1]['metrics']['momentum']}")
    return channels, now


def run_demo(now: datetime) -> list[dict]:
    """Deterministic synthetic data so the pipeline can be tested offline."""
    rng = random.Random(42)
    demo = [
        ("NovaPlays", "@novaplays", "FPS highlights", 6, 900_000),
        ("PixelPanda", "@pixelpanda", "Minecraft builds", 3, 240_000),
        ("TurboTuk", "@turbotuk", "mobile racing (EAT)", 9, 60_000),
    ]
    channels = []
    for name, handle, label, per_week, base in demo:
        shorts = []
        for i in range(6):
            pub = now - timedelta(days=rng.uniform(0.2, 20))
            vpd = base * rng.uniform(0.3, 2.2)
            views = int(vpd * max(0.2, (now - pub).days))
            shorts.append(short_metrics({
                "id": f"demo{i}{name[:3]}", "title": f"{name} short #{i + 1}",
                "published": pub, "views": views,
                "likes": int(views * rng.uniform(0.02, 0.06)),
            }, now))
        shorts.sort(key=lambda s: s["published"], reverse=True)
        channels.append({"name": name, "handle": handle, "label": label,
                         "channel_id": "DEMO", "shorts": shorts,
                         "metrics": channel_metrics(shorts, now)})
    return channels


def load_seed(path: str) -> tuple[list[dict], datetime]:
    with open(path, encoding="utf-8") as fh:
        seed = json.load(fh)
    now = datetime.fromisoformat(seed["snapshot_at"])
    channels = []
    for ch in seed["channels"]:
        shorts = [short_metrics({
            "id": s["id"], "title": s["title"],
            "published": datetime.fromisoformat(s["published"]),
            "views": s.get("views"), "likes": s.get("likes"),
        }, now) for s in ch["shorts"]]
        shorts.sort(key=lambda s: s["published"], reverse=True)
        channels.append({"name": ch["name"], "handle": ch.get("handle"),
                         "label": ch.get("label", ""), "channel_id": ch.get("channel_id", ""),
                         "shorts": shorts, "metrics": channel_metrics(shorts, now)})
    return channels, now


# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser(description="YouTube Shorts momentum tracker")
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument("--config", default=os.path.join(here, "channels.json"))
    ap.add_argument("--out", default=os.path.join(here, "output", "latest"))
    ap.add_argument("--max-shorts", type=int, default=10)
    ap.add_argument("--api-key", default=os.environ.get("YT_API_KEY"),
                    help="Optional official YouTube Data API key")
    ap.add_argument("--no-enrich", action="store_true", help="Skip per-video stats (RSS only)")
    ap.add_argument("--demo", action="store_true", help="Offline demo with synthetic data")
    ap.add_argument("--from-seed", help="Build outputs from a hand-collected seed JSON")
    ap.add_argument("--tz", default="Africa/Nairobi", help="Timezone label for outputs")
    args = ap.parse_args()

    if args.demo:
        now = datetime.now(timezone.utc)
        channels = run_demo(now)
    elif args.from_seed:
        channels, now = load_seed(args.from_seed)
    else:
        with open(args.config, encoding="utf-8") as fh:
            cfg = json.load(fh)
        channels, now = collect_live(cfg, args)

    print(f"\nSnapshot: {now.isoformat()} — {len(channels)} channels")
    write_outputs(args.out, now, channels, args.tz)


if __name__ == "__main__":
    main()
