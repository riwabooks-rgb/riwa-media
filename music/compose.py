"""RIWA original background music — synthesized from scratch (no samples, no third-party material).
Each mood: chord progression, soft pad + felt-piano arpeggio + low drone, convolution reverb. 48 kHz stereo."""
import numpy as np, json, subprocess, sys
SR = 48000
rng = np.random.default_rng(7)
def midi(n): return 440.0 * 2 ** ((n - 69) / 12)
def env(n, a, d, s, r, dur):
    t = np.arange(n) / SR; e = np.ones(n)
    a_n, r_n = int(a*SR), int(r*SR)
    e[:a_n] = np.linspace(0, 1, a_n) if a_n else 1
    e *= np.where(t > a, s + (1 - s) * np.exp(-(t - a) / max(d, 1e-3)), 1)
    if r_n: e[-r_n:] *= np.linspace(1, 0, r_n)
    return e
def piano(f, dur, vel=0.5):
    n = int(dur * SR); t = np.arange(n) / SR
    tone = sum((0.6 / k**1.3) * np.sin(2*np.pi*f*k*t*(1 + 0.0004*k*k)) * np.exp(-t * (1.2 + 0.9*k)) for k in range(1, 7))
    hammer = np.exp(-t*60) * rng.normal(0, 0.02, n)
    return (tone + hammer) * vel * env(n, 0.004, 0.8, 0.0, 0.15, dur)
def pad(freqs, dur, bright=0.35):
    n = int(dur * SR); t = np.arange(n) / SR; out = np.zeros(n)
    for f in freqs:
        for det in (-0.12, 0.0, 0.11):
            ff = f * 2 ** (det / 12)
            out += sum((1/k) * np.sin(2*np.pi*ff*k*t + rng.uniform(0, 6.28)) * (bright ** (k-1)) for k in range(1, 5))
    lfo = 0.85 + 0.15 * np.sin(2*np.pi*0.18*t)
    return out * lfo * env(n, 1.6, 2.0, 0.85, 1.4, dur) / (len(freqs) * 3)
def reverb(x, seconds=2.6, wet=0.32):
    n = int(seconds * SR); t = np.arange(n) / SR
    ir = rng.normal(0, 1, n) * np.exp(-t * 3.2); ir[0] = 0
    L = len(x) + n; N = 1 << (L - 1).bit_length()
    y = np.fft.irfft(np.fft.rfft(x, N) * np.fft.rfft(ir / np.sqrt(np.sum(ir**2)), N), N)[:len(x)]
    return (1 - wet) * x + wet * y * 0.6
def lowpass(x, cut):
    X = np.fft.rfft(x); f = np.fft.rfftfreq(len(x), 1/SR); X *= 1 / np.sqrt(1 + (f / cut) ** 4); return np.fft.irfft(X, len(x))

MOODS = {
  # name: (root midi, chords as semitone offsets, bpm, arpeggio pattern, pad brightness, description)
  "reflective_minor": (57, [[0,3,7,10],[ -4,0,3,7],[ -7,-3,0,5],[-2,2,5,9]], 66, [0,2,1,3,2,1], 0.30, "تأملي هادئ بمقام صغير — للأفكار النفسية والذكريات"),
  "warm_hope":        (60, [[0,4,7,11],[ -3,0,4,9],[ 5,9,12,16],[7,11,14,17]], 72, [0,1,2,3,2,1], 0.38, "دافئ ومتفائل — للخلاصات والتحفيز الهادئ"),
  "mystery_soft":     (55, [[0,3,7,14],[1,5,8,13],[ -2,3,7,10],[0,3,6,10]], 60, [0,3,1,2,3,1], 0.26, "غامض ناعم — لخفايا النفس والانحيازات"),
  "melancholic":      (52, [[0,3,7,12],[-4,0,3,8],[-2,2,5,10],[-5,-1,2,7]], 58, [0,2,3,2,1,2], 0.28, "حزين رقيق — للعلاقات والفقد والتعلق"),
  "calm_focus":       (62, [[0,7,12,16],[-5,2,7,11],[ -3,4,9,12],[-7,0,5,9]], 76, [0,1,2,1,3,1], 0.33, "هادئ مركّز — للعادات والإنتاجية والتأجيل"),
  "cinematic_rise":   (50, [[0,7,10,15],[ -2,5,8,14],[ -4,3,8,12],[-5,2,7,14]], 64, [0,2,1,3,1,2], 0.36, "سينمائي متصاعد — للمال والطموح وقصص النجاح"),
}
def compose(name, total=48.0):
    root, chords, bpm, pat, bright, _ = MOODS[name]
    beat = 60 / bpm; bar = beat * 4; n = int(total * SR)
    L = np.zeros(n); R = np.zeros(n)
    t0, ci = 0.0, 0
    while t0 < total - 0.5:
        ch = chords[ci % len(chords)]; dur = min(bar * 2, total - t0)
        s0 = int(t0 * SR)
        p = pad([midi(root + c) for c in ch[:3]], dur + 1.5, bright); e = min(n, s0 + len(p))
        L[s0:e] += p[:e - s0] * 0.55; R[s0:e] += p[:e - s0] * 0.55
        drone = pad([midi(root - 12 + ch[0])], dur + 1.5, 0.15); L[s0:e] += drone[:e-s0] * 0.35; R[s0:e] += drone[:e-s0] * 0.35
        step = beat / 2; k = 0; tt = t0 + (0 if ci else bar)  # piano enters after the first bar
        while tt < t0 + dur - 0.05 and tt < total - 1.0:
            note = root + 12 + ch[pat[k % len(pat)] % len(ch)] + (12 if (k // len(pat)) % 2 and pat[k % len(pat)] == 3 else 0)
            v = 0.32 + 0.1 * rng.random(); pn = piano(midi(note), 3.2, v); s = int(tt * SR); e2 = min(n, s + len(pn))
            pan = 0.5 + 0.25 * np.sin(k)
            L[s:e2] += pn[:e2 - s] * (1 - pan); R[s:e2] += pn[:e2 - s] * pan
            tt += step * (1.0 + (0.5 if k % 6 == 5 else 0)); k += 1
        t0 += dur; ci += 1
    L, R = lowpass(L, 7000), lowpass(R, 7000)
    L, R = reverb(L), reverb(R)
    m = max(np.abs(L).max(), np.abs(R).max()); L, R = L / m * 0.85, R / m * 0.85
    fade = int(2.0 * SR); L[-fade:] *= np.linspace(1, 0, fade); R[-fade:] *= np.linspace(1, 0, fade)
    return np.stack([L, R], 1)

if __name__ == "__main__":
    import wave
    lib = []
    for name, spec in MOODS.items():
        x = compose(name); pcm = (x * 32767).astype("<i2")
        with wave.open(f"{name}.wav", "wb") as w: w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes())
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", f"{name}.wav", "-af", "loudnorm=I=-18:TP=-2:LRA=9", "-ar", "48000", "-c:a", "aac", "-b:a", "192k", f"{name}.m4a"], check=True)
        lib.append({"id": name, "file": f"music/{name}.m4a", "mood": spec[5], "bpm": spec[2], "duration_s": 48,
                    "source": "RIWA original — synthesized programmatically by Claude for RIWA (compose.py), no samples or third-party recordings",
                    "license": "Original work owned by RIWA; free for commercial use including TikTok/Instagram/YouTube; no attribution required",
                    "commercial_tiktok_ok": True})
    json.dump(lib, open("library.json", "w"), ensure_ascii=False, indent=1); print(len(lib))
