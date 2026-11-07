#!/usr/bin/env python3
"""Trim the recording, lay each voiceover clip at its scene start, export MP4.
Needs ffmpeg. Usage (from video/): python3 mix.py   -> out/infill-demo.mp4
Without out/voice/manifest.json it exports the video with no audio."""
import json, os, subprocess, sys
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
t = json.load(open(os.path.join(OUT, "timing.json")))
keep = float(t["keepFrom"]); marks = t.get("marks", [])
src = os.path.join(OUT, "infill-demo.webm"); dst = os.path.join(OUT, "infill-demo.mp4")
man_p = os.path.join(OUT, "voice", "manifest.json")
cmd = ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{keep:.3f}", "-i", src]
clips = json.load(open(man_p))["clips"] if os.path.exists(man_p) else []
filt, labels = [], []
for n, c in enumerate(clips):
    if c["i"] >= len(marks):
        continue
    cmd += ["-i", os.path.join(OUT, "voice", c["file"])]
    delay = max(0, int((marks[c["i"]] - keep + 0.25) * 1000))  # small lead-in after each cut
    filt.append(f"[{len(labels) + 1}:a]adelay={delay}|{delay}[a{n}]"); labels.append(f"[a{n}]")
vid = ["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
if labels:
    filt.append("".join(labels) + f"amix=inputs={len(labels)}:normalize=0,apad[aout]")
    cmd += ["-filter_complex", ";".join(filt), "-map", "0:v", "-map", "[aout]", "-shortest"] + vid + ["-c:a", "aac", "-b:a", "160k", dst]
else:
    cmd += vid + ["-an", dst]
subprocess.run(cmd, check=True)
dur = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", dst], capture_output=True, text=True).stdout.strip()
print(f"wrote {dst} ({float(dur):.1f} s, {'with' if labels else 'no'} voiceover)")
