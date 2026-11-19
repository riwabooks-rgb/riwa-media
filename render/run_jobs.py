"""Renders every jobs/*.json that has no finished video yet. Runs inside GitHub Actions (FFmpeg preinstalled)."""
import json, pathlib, subprocess, sys
root = pathlib.Path(__file__).resolve().parent.parent
done = []
for jf in sorted((root / "jobs").glob("*.json")):
    job = json.loads(jf.read_text(encoding="utf-8"))
    out = root / job["out"]
    if out.exists(): continue
    out.parent.mkdir(parents=True, exist_ok=True)
    job["slides"] = [str(root / s) if not str(s).startswith("http") else s for s in job["slides"]]
    job["music"] = str(root / job["music"]); job["out"] = str(out)
    tmp = root / "render" / "_job.json"; tmp.write_text(json.dumps(job, ensure_ascii=False))
    r = subprocess.run([sys.executable, str(root / "render" / "render_video.py"), str(tmp)], capture_output=True, text=True)
    status = {"post_id": job["post_id"], "ok": r.returncode == 0 and out.exists(), "log": (r.stdout or r.stderr)[-1500:]}
    (out.parent / "render_report.json").write_text(json.dumps(status, ensure_ascii=False, indent=1))
    done.append(status)
print(json.dumps(done, ensure_ascii=False))
