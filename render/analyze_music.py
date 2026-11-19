"""Classify TikTok Commercial Music Library clips by mood from their audio (preview URLs).
Input: music_jobs/*.json  {"tracks":[{id, clip_id, name, artist, genres, preview, duration}]}
Output: catalog/music_catalog.json (merged, newest analysis wins). Uploads via GitHub API (GITHUB_TOKEN)."""
import json, os, sys, pathlib, subprocess, urllib.request, base64, datetime, re
import numpy as np
root = pathlib.Path(__file__).resolve().parent.parent
REPO, TOKEN = os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_TOKEN"]
API = f"https://api.github.com/repos/{REPO}/contents/"
SR = 22050
def api(method, path, body=None):
    req = urllib.request.Request(API + path, method=method, data=json.dumps(body).encode() if body else None,
                                 headers={"Authorization": f"Bearer {TOKEN}", "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r: return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e: return e.code, {}
def get_file(path):
    code, cur = api("GET", path + "?ref=main")
    return (json.loads(base64.b64decode(cur["content"])), cur["sha"]) if code == 200 else (None, None)
def put(path, obj, msg):
    _, sha = get_file(path)
    body = {"message": msg, "content": base64.b64encode(json.dumps(obj, ensure_ascii=False, indent=1).encode()).decode(), "branch": "main"}
    if sha: body["sha"] = sha
    return api("PUT", path, body)[0]
def pcm(url):
    data = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=60).read()
    p = subprocess.run(["ffmpeg", "-v", "error", "-i", "pipe:0", "-t", "45", "-ac", "1", "-ar", str(SR), "-f", "f32le", "pipe:1"], input=data, capture_output=True)
    return np.frombuffer(p.stdout, dtype=np.float32)
def features(x):
    if len(x) < SR * 5: raise ValueError("audio too short")
    hop, n = 512, 2048
    frames = np.lib.stride_tricks.sliding_window_view(x, n)[::hop] * np.hanning(n)
    mag = np.abs(np.fft.rfft(frames, axis=1)); freqs = np.fft.rfftfreq(n, 1 / SR)
    rms = np.sqrt((frames ** 2).mean(1)) + 1e-9
    centroid = float((mag * freqs).sum(1).mean() / (mag.sum(1).mean() + 1e-9))
    flux = np.maximum(np.diff(mag, axis=0), 0).sum(1); flux = (flux - flux.mean()) / (flux.std() + 1e-9)
    ac = np.correlate(flux, flux, "full")[len(flux) - 1:]; fps = SR / hop
    lo, hi = int(fps * 60 / 160), int(fps * 60 / 60)          # 60..160 BPM
    seg = ac[lo:hi]; lag = lo + int(np.argmax(seg)); bpm = 60 * fps / lag
    pulse = float((seg.max() - seg.mean()) / (ac[0] + 1e-9))     # beat clarity (peak above the local average)
    thr = flux.mean() + 1.0 * flux.std(); pk = (flux[1:-1] > thr) & (flux[1:-1] > flux[:-2]) & (flux[1:-1] >= flux[2:])
    onset_rate = float(pk.sum() / (len(x) / SR))
    loud_db = float(20 * np.log10(np.sqrt((x ** 2).mean()) + 1e-9))
    dyn = float(np.percentile(20 * np.log10(rms), 90) - np.percentile(20 * np.log10(rms), 10))
    low = float(mag[:, freqs < 250].sum() / (mag.sum() + 1e-9))
    # crude major/minor: chroma vs. key templates
    chroma = np.zeros(12); m = (freqs > 60) & (freqs < 2000)
    pc = (np.round(12 * np.log2(freqs[m] / 440)) % 12).astype(int); np.add.at(chroma, pc, mag[:, m].sum(0)); chroma /= chroma.sum() + 1e-9
    maj = np.array([6.35,2.23,3.48,2.33,4.38,4.09,2.52,5.19,2.39,3.66,2.29,2.88]); mnr = np.array([6.33,2.68,3.52,5.38,2.60,3.53,2.54,4.75,3.98,2.69,3.34,3.17])
    sc = lambda t: max(np.corrcoef(chroma, np.roll(t, k))[0, 1] for k in range(12))
    mode = "major" if sc(maj) >= sc(mnr) else "minor"
    return dict(bpm=round(bpm, 1), pulse=round(pulse, 3), onset_rate=round(onset_rate, 2), centroid=round(centroid), loud_db=round(loud_db, 1), dynamics_db=round(dyn, 1), low_ratio=round(low, 3), mode=mode)
def energy(f):  # 0..1
    e = 0.45 * np.clip((f["onset_rate"] - 0.8) / 3.2, 0, 1) + 0.25 * np.clip(f["pulse"] / 0.35, 0, 1) + 0.30 * np.clip((f["centroid"] - 900) / 2600, 0, 1)
    return round(float(e), 3)
def mood(f, e):
    if e < 0.33: return "calm_focus" if f["mode"] == "major" else ("melancholic" if f["centroid"] < 1500 else "reflective")
    if e < 0.55: return "warm_hope" if f["mode"] == "major" else "mystery"
    return "cinematic_rise" if f["mode"] == "major" else "tense_drive"
VOCAL_HINT = re.compile(r"instrumental|piano|lofi|lo-fi|ambient|beat|inst\.?\b", re.I)
cat0, _ = get_file("catalog/music_catalog.json"); cat_prev = (cat0 or {}).get("tracks", {})
out = []
for jf in sorted((root / "music_jobs").glob("*.json")):
    job = json.loads(jf.read_text(encoding="utf-8"))
    for t in job.get("tracks", []):
        rec = {k: t.get(k) for k in ("id", "clip_id", "name", "artist", "genres", "duration", "rank", "chart")}; rec["last_seen"] = job.get("fetched_at")
        prev = (cat_prev or {}).get(t.get("clip_id") or t.get("id"))
        if prev and prev.get("ok"): prev.update(last_seen=job.get("fetched_at"), rank=t.get("rank"), chart=t.get("chart")); out.append(prev); continue
        try:
            f = features(pcm(t["preview"])); e = energy(f)
            rec.update(features=f, energy=e, mood=mood(f, e), instrumental_hint=bool(VOCAL_HINT.search(t.get("name", ""))), ok=True)
        except Exception as ex:
            rec.update(ok=False, error=str(ex)[:200])
        rec["analyzed_at"] = datetime.datetime.utcnow().isoformat() + "Z"; out.append(rec)
cat, _ = get_file("catalog/music_catalog.json"); cat = cat or {"tracks": {}}
for r in out: cat["tracks"][r["clip_id"] or r["id"]] = r
cat["updated_at"] = datetime.datetime.utcnow().isoformat() + "Z"; cat["count"] = len(cat["tracks"])
cat["moods"] = {m: sum(1 for r in cat["tracks"].values() if r.get("mood") == m) for m in ["calm_focus", "reflective", "melancholic", "warm_hope", "mystery", "cinematic_rise", "tense_drive"]}
print("analyzed", len(out), "ok", sum(r["ok"] for r in out), "put", put("catalog/music_catalog.json", cat, f"riwa: music catalog ({len(out)} analyzed)"))
print(json.dumps(cat["moods"]))
