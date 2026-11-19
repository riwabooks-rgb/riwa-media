"""Renders pending jobs/*.json and uploads each MP4 + report to the repo through the GitHub API
(only render/, music/ and jobs/ are checked out, so the job stays fast as the repo grows)."""
import json, os, pathlib, subprocess, sys, base64, urllib.request, urllib.error
root = pathlib.Path(__file__).resolve().parent.parent
REPO, TOKEN = os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_TOKEN"]
API = f"https://api.github.com/repos/{REPO}/contents/"
def api(method, path, body=None):
    req = urllib.request.Request(API + path, method=method, data=json.dumps(body).encode() if body else None,
                                 headers={"Authorization": f"Bearer {TOKEN}", "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r: return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e: return e.code, {}
def put(path, data, msg):
    code, cur = api("GET", path + "?ref=main"); body = {"message": msg, "content": base64.b64encode(data).decode(), "branch": "main"}
    if code == 200: body["sha"] = cur["sha"]
    return api("PUT", path, body)[0]
done = []
for jf in sorted((root / "jobs").glob("*.json")):
    job = json.loads(jf.read_text(encoding="utf-8"))
    if api("GET", job["out"] + "?ref=main")[0] == 200: continue          # already rendered
    out = root / "render" / "_out.mp4"
    job2 = {**job, "music": str(root / job["music"]), "out": str(out)}
    (root / "render" / "_job.json").write_text(json.dumps(job2, ensure_ascii=False))
    r = subprocess.run([sys.executable, str(root / "render" / "render_video.py"), str(root / "render" / "_job.json")], capture_output=True, text=True)
    ok = r.returncode == 0 and out.exists()
    report = {"post_id": job["post_id"], "ok": ok, "music": job["music"], "log": (r.stdout if ok else r.stderr)[-1500:]}
    if ok: report["upload_status"] = put(job["out"], out.read_bytes(), f"riwa: video {job['post_id']}")
    put(job["out"].rsplit("/", 1)[0] + "/render_report.json", json.dumps(report, ensure_ascii=False, indent=1).encode(), f"riwa: report {job['post_id']}")
    done.append(report)
print(json.dumps(done, ensure_ascii=False)[:3000])
