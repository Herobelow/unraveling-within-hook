#!/usr/bin/env python3
"""Narrated build: lays TTS narration over the animated video.

Each scene keeps its original pacing, except where a narration clip is longer
than the scene (the hook) — that scene is extended so the voice never overlaps
the next line. SFX and the music bed are remapped onto the new timeline.

Expects clip_00.mp3 ... clip_08.mp3 (one per scene) in --clips.

    python3 render_narrated.py --clips . --out narrated.mp4
"""
import os, math, argparse, subprocess, wave
import numpy as np
from PIL import Image, ImageDraw
import render_video as R
from imageio_ffmpeg import get_ffmpeg_exe

W, H, SR = R.W, R.H, R.SR
FF = get_ffmpeg_exe()
OUTDIR = os.path.dirname(os.path.abspath(__file__))

ORIG_DUR     = [15, 20, 45, 45, 45, 45, 50, 50, 25]
ORIG_STARTS  = [0, 15, 35, 80, 125, 170, 215, 265, 315]
SCENES = [R.scene_hook, R.scene_setup, R.scene_lesson1, R.scene_lesson2,
          R.scene_lesson3, R.scene_lesson4, R.scene_lesson5, R.scene_rapid,
          R.scene_outro]

# (original_absolute_time, kind, freq)
SFX = [
    (0.5,"buzz",None),(4.5,"buzz",None),(9.5,"buzz",None),(14.5,"buzz",None),
    (7.0,"ding",988.0),(12.0,"ding",988.0),(17.0,"ding",988.0),
    (19.5,"ding",1175.0),(15.5,"ding",659.25),
    (35.4,"buzz",None),(40.1,"ding",None),(44.2,"ding",None),
    (49.0,"buzz",None),(49.9,"ding",None),(53.2,"ding",None),(58.0,"fanfare",None),
    (80.4,"buzz",None),(85.1,"ding",None),(89.2,"ding",None),
    (96.0,"buzz",None),(98.6,"whoosh",None),(99.4,"ding",None),
    (125.4,"buzz",None),(129.6,"ding",None),
    (145.4,"tick",None),(146.6,"tick",None),(147.8,"tick",None),
    (148.6,"whoosh",None),(149.4,"ding",None),(152.0,"fanfare",None),
    (170.4,"buzz",None),(174.0,"ding",None),(178.0,"ding",None),
    (215.4,"buzz",None),(219.6,"ding",None),(226.0,"ding",None),
    (238.0,"buzz",None),(240.0,"tick",None),(241.0,"tick",None),
    (243.5,"fanfare",None),(246.0,"pop",None),
    (270.0,"tick",None),(271.0,"tick",None),(272.0,"tick",None),
    (274.0,"ding",None),(278.2,"ding",None),(282.4,"ding",None),
    (286.0,"ding",None),(290.0,"ding",None),(294.0,"ding",None),(296.0,"fanfare",None),
    (316.0,"ding",None),(326.0,"pop",None),(332.0,"ding",None),
]

NEW_STARTS, NEW_DUR, TOTAL = [], [], 0.0


def read_audio(path):
    raw = subprocess.run(
        [FF, "-loglevel", "error", "-i", path, "-f", "f32le",
         "-ac", "1", "-ar", str(SR), "-"],
        capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()


def load_clips(d):
    clips = []
    for i in range(9):
        p = os.path.join(d, "clip_%02d.mp3" % i)
        if not os.path.exists(p):
            raise SystemExit("missing %s" % p)
        clips.append(read_audio(p))
    return clips


def map_time(o):
    for i in range(len(ORIG_STARTS)):
        s0 = ORIG_STARTS[i]
        s1 = ORIG_STARTS[i + 1] if i + 1 < len(ORIG_STARTS) else 1e9
        if s0 <= o < s1:
            return NEW_STARTS[i] + (o - s0)
    return o


def scene_at(t):
    for i in range(len(NEW_STARTS) - 1):
        if NEW_STARTS[i] <= t < NEW_STARTS[i + 1]:
            return i, t - NEW_STARTS[i]
    return len(NEW_STARTS) - 2, t - NEW_STARTS[-2]


def render_frame(t):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    img = Image.alpha_composite(R.BG.copy(), img)
    d = ImageDraw.Draw(img, "RGBA")
    R.draw_bg(d, t)
    si, lt = scene_at(t)
    SCENES[si](d, lt)
    return img.convert("RGB")


def build_audio(clips):
    n = int(TOTAL * SR)
    out = np.zeros(n, dtype=np.float32)

    def add(sig, t0):
        i = int(t0 * SR); j = min(n, i + len(sig))
        if i < n:
            out[i:j] += sig[:j - i]

    def note(freq, dur, t0, amp, kind="sine", decay=None):
        tt = np.arange(int(dur * SR)) / SR
        if kind == "sine":
            v = np.sin(2 * np.pi * freq * tt)
        elif kind == "pluck":
            v = np.sin(2 * np.pi * freq * tt) * np.exp(-tt * 4)
        elif kind == "saw":
            v = 2 * (tt * freq % 1) - 1
        else:
            v = np.sign(np.sin(2 * np.pi * freq * tt))
        if decay is not None:
            v = v * np.exp(-tt * decay)
        add(v.astype(np.float32) * amp, t0)

    for i, clip in enumerate(clips):
        add(clip.astype(np.float32) * 0.95, NEW_STARTS[i])

    prog = [(130.81, [261.63, 329.63, 392.0]),
            (110.0, [220.0, 261.63, 329.63]),
            (87.31, [174.61, 220.0, 261.63]),
            (98.0, [196.0, 246.94, 293.66])]
    beat, bar = 0.42, 0.42 * 4
    for b in range(int(TOTAL / bar)):
        root, chord = prog[b % 4]
        t0 = b * bar
        note(root, bar * 0.9, t0, 0.07, "sine", decay=0.6)
        for k in range(8):
            f = chord[k % 3] * (2 if k >= 4 else 1)
            note(f, 0.32, t0 + k * beat, 0.028, "pluck")

    def ding(t0, f=880.0, amp=0.14):
        note(f, 0.45, t0, amp, "sine", decay=2.4)
        note(f * 1.5, 0.35, t0, amp * 0.6, "sine", decay=3.0)

    def buzz(t0): note(150.0, 0.3, t0, 0.11, "saw", decay=9)
    def tick(t0): note(1400.0, 0.05, t0, 0.08, "sine", decay=60)
    def pop(t0):  note(520.0, 0.18, t0, 0.11, "sine", decay=14)
    def whoosh(t0): note(300.0, 0.35, t0, 0.09, "sine", decay=5)

    def fanfare(t0):
        for i, f in enumerate([523.25, 659.25, 783.99, 1046.5]):
            note(f, 0.28, t0 + i * 0.13, 0.13, "sine", decay=3.2)

    for (o, kind, freq) in SFX:
        t = map_time(o)
        if kind == "ding":     ding(t, freq if freq else 880.0)
        elif kind == "buzz":   buzz(t)
        elif kind == "tick":   tick(t)
        elif kind == "pop":    pop(t)
        elif kind == "fanfare": fanfare(t)
        elif kind == "whoosh": whoosh(t)

    return np.clip(out, -1, 1)


def write_wav(path, pcm):
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def main():
    global NEW_STARTS, NEW_DUR, TOTAL
    ap = argparse.ArgumentParser()
    ap.add_argument("--clips", default=OUTDIR)
    ap.add_argument("--out", default=os.path.join(OUTDIR, "5-english-grammar-mistakes-narrated.mp4"))
    ap.add_argument("--fps", type=int, default=24)
    a = ap.parse_args()

    clips = load_clips(a.clips)
    NEW_DUR = [max(ORIG_DUR[i], len(clips[i]) / SR + 1.2) for i in range(9)]
    s = 0.0
    for d in NEW_DUR:
        NEW_STARTS.append(s); s += d
    TOTAL = s
    print("scene durations:", [round(x, 1) for x in NEW_DUR])
    print("total: %.1fs" % TOTAL, flush=True)

    print("building soundtrack...", flush=True)
    pcm = (build_audio(clips) * 32000).astype(np.int16)
    wav = os.path.join(OUTDIR, "_narrated_track.wav")
    write_wav(wav, pcm)

    print("rendering video...", flush=True)
    nfr = int(TOTAL * a.fps)
    cmd = [FF, "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", "%dx%d" % (W, H), "-r", str(a.fps), "-i", "-",
           "-i", wav, "-c:v", "libx264", "-preset", "medium", "-crf", "22",
           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
           "-movflags", "+faststart", "-shortest", a.out]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for i in range(nfr):
        t = (i + 0.5) / a.fps
        proc.stdin.write(render_frame(t).tobytes())
        if i % 240 == 0:
            print("  frame %d/%d  t=%.1fs" % (i, nfr, t), flush=True)
    proc.stdin.close()
    proc.wait()
    print("done ->", a.out, flush=True)


if __name__ == "__main__":
    main()
