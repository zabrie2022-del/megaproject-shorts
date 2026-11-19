"""Generate a simple original backing track (WAV) with numpy. Usage: music.py out.wav seconds seed"""
import sys, wave
import numpy as np

SR = 44100
NOTE = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def freq(name, octave):
    semis = NOTE[name[0]] + (1 if name.endswith("#") else 0) + (octave - 4) * 12 - 9
    return 440.0 * 2 ** (semis / 12)


# (root, third, fifth) triads, four per progression
PROGS = [
    [("A", "C", "E"), ("F", "A", "C"), ("C", "E", "G"), ("G", "B", "D")],
    [("D", "F", "A"), ("A#", "D", "F"), ("F", "A", "C"), ("C", "E", "G")],
    [("E", "G", "B"), ("C", "E", "G"), ("G", "B", "D"), ("D", "F#", "A")],
    [("C", "E", "G"), ("A", "C", "E"), ("F", "A", "C"), ("G", "B", "D")],
    [("F", "A", "C"), ("C", "E", "G"), ("D", "F", "A"), ("A#", "D", "F")],
    [("G", "B", "D"), ("E", "G", "B"), ("C", "E", "G"), ("D", "F#", "A")],
]


def make(seconds, seed):
    rng = np.random.default_rng(seed)
    prog = PROGS[seed % len(PROGS)]
    bpm = [84, 90, 96, 100, 88, 92][seed % 6]
    beat = 60.0 / bpm
    n = int(seconds * SR)
    t = np.arange(n) / SR
    out = np.zeros(n)
    bar = beat * 4
    nbars = int(np.ceil(seconds / bar))
    for b in range(nbars):
        chord = prog[b % 4]
        s, e = int(b * bar * SR), min(n, int((b + 1) * bar * SR))
        if s >= n:
            break
        tt = t[s:e] - b * bar
        env = np.minimum(1, tt / 0.6) * np.minimum(1, (bar - tt) / 0.6).clip(0, 1)
        pad = np.zeros(e - s)
        for name in chord:
            f = freq(name, 3 if name == chord[0] else 4)
            for det in (-0.4, 0.0, 0.4):
                pad += np.sin(2 * np.pi * (f + det) * tt + rng.uniform(0, 6.28))
            pad += 0.3 * np.sin(2 * np.pi * f * 2 * tt)
        out[s:e] += 0.035 * pad * env * (0.85 + 0.15 * np.sin(2 * np.pi * 0.25 * tt))
        out[s:e] += 0.16 * np.sin(2 * np.pi * freq(chord[0], 2) * tt) * env
        # plucked arpeggio on eighth notes
        order = [0, 1, 2, 1, 0, 2, 1, 2]
        for k in range(8):
            ps = s + int(k * beat / 2 * SR)
            if ps >= n:
                break
            pe = min(n, ps + int(0.6 * SR))
            pt = np.arange(pe - ps) / SR
            f = freq(chord[order[(k + seed) % 8]], 5)
            pl = np.sin(2 * np.pi * f * pt) + 0.35 * np.sin(2 * np.pi * 2 * f * pt)
            out[ps:pe] += 0.07 * pl * np.exp(-pt * 7) * (1 if b >= 1 else 0.5)
        # soft kick on each beat from the third bar on
        if b >= 2:
            for k in range(4):
                ks = s + int(k * beat * SR)
                if ks >= n:
                    break
                ke = min(n, ks + int(0.25 * SR))
                kt = np.arange(ke - ks) / SR
                out[ks:ke] += 0.22 * np.sin(2 * np.pi * (50 * kt + 60 * (1 - np.exp(-kt * 30)) / 30)) * np.exp(-kt * 14)
    fade = np.minimum(1, t / 0.8) * np.minimum(1, (seconds - t) / 1.5).clip(0, 1)
    out *= fade
    out = out / (np.abs(out).max() + 1e-9) * 0.6
    # light stereo width
    delay = int(0.012 * SR)
    left = out
    right = np.concatenate([np.zeros(delay), out[:-delay]]) * 0.9 + out * 0.1
    return np.stack([left, right], axis=1)


if __name__ == "__main__":
    path, seconds, seed = sys.argv[1], float(sys.argv[2]), int(sys.argv[3])
    data = (make(seconds, seed) * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(data.tobytes())
