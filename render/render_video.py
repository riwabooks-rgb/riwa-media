"""RIWA slide video: 5 vertical slides -> 1080x1920 MP4 (H.264 + AAC) with calm crossfades and licensed music.
Usage: python render_video.py job.json
job = {"post_id", "slides": [url|path x5], "durations": [sec x5] (optional), "texts": [str x5] (optional),
       "music": path, "out": path, "fade": 0.6}"""
import json, sys, subprocess, tempfile, pathlib, urllib.request, shutil

def reading_time(text, kind):
    """Seconds a slide stays on screen: base + time to read Arabic text at a relaxed pace (~2.6 words/s)."""
    words = len((text or "").split())
    base = {"cover": 3.0, "promo": 4.5}.get(kind, 2.0)
    return round(min(7.0, max(base, base + words / 2.6)), 2)

def main(job):
    tmp = pathlib.Path(tempfile.mkdtemp())
    imgs = []
    for i, s in enumerate(job["slides"], 1):
        p = tmp / f"s{i}.jpg"
        if str(s).startswith("http"):
            with urllib.request.urlopen(s, timeout=60) as r, open(p, "wb") as f: shutil.copyfileobj(r, f)
        else: shutil.copy(s, p)
        imgs.append(p)
    kinds = ["cover"] + ["body"] * (len(imgs) - 2) + ["promo"]
    durs = job.get("durations") or [reading_time(t, k) for t, k in zip(job.get("texts", [""] * len(imgs)), kinds)]
    fade = float(job.get("fade", 0.6)); fps = 30
    total = sum(durs) - fade * (len(imgs) - 1)
    args = ["ffmpeg", "-y", "-loglevel", "error"]
    for p, d in zip(imgs, durs): args += ["-loop", "1", "-t", f"{d + 0.05:.2f}", "-framerate", str(fps), "-i", str(p)]
    args += ["-i", job["music"]]
    # scale exactly (slides are already 1080x1920), then chain crossfades; no zoom so the Arabic text stays sharp
    f = [f"[{i}:v]scale=1080:1920:flags=lanczos,setsar=1,format=yuv420p,fps={fps}[v{i}]" for i in range(len(imgs))]
    last, off = "v0", 0.0
    for i in range(1, len(imgs)):
        off += durs[i - 1] - fade
        f.append(f"[{last}][v{i}]xfade=transition=fadeblack:duration={fade}:offset={off:.2f}[x{i}]"); last = f"x{i}"
    a = len(imgs)
    f.append(f"[{a}:a]atrim=0:{total:.2f},asetpts=PTS-STARTPTS,volume=0.9,afade=t=in:st=0:d=1.2,afade=t=out:st={max(0, total - 2.0):.2f}:d=2.0,"
             f"loudnorm=I=-16:TP=-1.5:LRA=9,aresample=44100[aout]")
    args += ["-filter_complex", ";".join(f), "-map", f"[{last}]", "-map", "[aout]",
             "-c:v", "libx264", "-preset", "veryfast", "-profile:v", "high", "-level", "4.1", "-crf", "18", "-pix_fmt", "yuv420p", "-r", str(fps),
             "-c:a", "aac", "-b:a", "160k", "-ac", "2", "-movflags", "+faststart", "-t", f"{total:.2f}", job["out"]]
    subprocess.run(args, check=True)
    probe = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration,size:stream=codec_name,width,height,r_frame_rate,sample_rate,channels", "-of", "json", job["out"]], capture_output=True, text=True).stdout)
    print(json.dumps({"durations": durs, "total": round(total, 2), "probe": probe}, ensure_ascii=False))

if __name__ == "__main__":
    main(json.load(open(sys.argv[1])))
