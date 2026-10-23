# 5 English Grammar Mistakes — Video Script Package

A production-ready package for the ~5:40 animated English-grammar video described in the brief.

## What's in this folder

| File | What it is |
|---|---|
| `01-production-script.md` | Master script — timings, VO, on-screen text, visuals, SFX/music cues |
| `02-voiceover-script.txt` | Clean voiceover script, one sentence per line, for recording/TTS |
| `03-subtitles.srt` | Timed subtitles for burned-in captions or SRT upload |
| `04-youtube-metadata.md` | Title options, description, tags, thumbnail concept, chapters |
| `thumbnail.png` | Suggested thumbnail artwork (concept render) |
| `5-english-grammar-mistakes.mp4` | Animated video with music + SFX and burned-in captions (no voiceover) |
| `5-english-grammar-mistakes-narrated.mp4` | **The finished video with spoken narration** — 5:58, 1280×720, 24 fps, H.264 + AAC |
| `render_video.py` | Source code that generates the captioned MP4 (Pillow frames + ffmpeg + synthesized audio) |
| `render_narrated.py` | Source code for the narrated build (lays TTS clips over the animation) |
| `clip_00.mp3` … `clip_08.mp3` | The nine scene narration clips (one per scene) used by the narrated build |

## The video

**`5-english-grammar-mistakes-narrated.mp4`** is the finished, publish-ready build:
a fully self-contained animated video of the script with **spoken narration**.
Midnight-navy/gold brand style, recurring characters (Alex & Maya), speech bubbles,
a 5-slot Mistake Tracker that fills green as each mistake is corrected, red→green
sentence flashes, the 2 s quick-test pause, the 3-2-1 countdown with the `ate→eat`
transform, the rapid-fire scoreboard, and the subscribe CTA. The soundtrack is a
synthesized music bed plus SFX, layered under the TTS narration. Runtime 5:58.

`5-english-grammar-mistakes.mp4` is the same animation with narration carried only
by burned-in captions and no voiceover audio.

## How to use it

1. **Watch / publish** `5-english-grammar-mistakes-narrated.mp4`.
2. **Re-render** after editing the scenes in `render_video.py`:

   ```bash
   pip install pillow numpy imageio-ffmpeg
   python3 render_video.py            # full captioned render
   python3 render_video.py --start 35 --end 80 --out /tmp/lesson1.mp4   # a range
   ```

3. **Rebuild with narration** (needs the `clip_*.mp3` files, or regenerate them
   from `02-voiceover-script.txt` via TTS):

   ```bash
   python3 render_narrated.py --clips . --out narrated.mp4
   ```

   Each scene keeps its pacing unless its narration clip is longer, in which case
   the scene stretches so the voice never overlaps the next line.
4. **Publish** using `04-youtube-metadata.md`.

## The five mistakes

| # | Wrong | Correct | Rule |
|---|-------|---------|------|
| 1 | I am agree | I agree | "Agree" is a verb — no "am" |
| 2 | She don't | She doesn't | he/she/it → "doesn't" (present simple negative) |
| 3 | I didn't went | I didn't go | after "didn't," use the base form |
| 4 | I have 25 years | I am 25 years old | age uses "be," not "have" |
| 5 | He go to school | He goes to school | he/she/it → add -s/-es (present simple) |

## Next steps (not included here)
- Render the actual narrated MP4 (visuals + TTS + captions).
- Build a companion landing page in the `discipline-blueprint` style.
