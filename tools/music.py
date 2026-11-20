"""Generate an original upbeat backing track (WAV) with numpy.
Usage: music.py out.wav SECONDS SEED
Style: afro-pop groove - kick, clap, shakers, bass, marimba chords and a lead hook.
Everything is synthesized here, so the track is original and free to use."""
import sys, wave
import numpy as np

SR = 44100


def hz(semis_from_a4):
    return 440.0 * 2 ** (semis_from_a4 / 12)


def put(out, start, sig, gain=1.0):
    if start >= len(out) or start < 0:
        return
    end = min(len(out), start + len(sig))
    out[start:end] += gain * sig[: end - start]


def tgrid(seconds):
    return np.arange(int(seconds * SR)) / SR


def kick():
    t = tgrid(0.32)
    f = 46 + 95 * np.exp(-t * 32)
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 11)
    click = np.sin(2 * np.pi * 1800 * t) * np.exp(-t * 320) * 0.25
    return body + click


def noise(n, rng, bright=1):
    x = rng.standard_normal(n + 4)
    for _ in range(bright):          # each difference removes more low end
        x = np.diff(x)
    x = x[:n]
    return x / (np.abs(x).max() + 1e-9)


def clap(rng):
    t = tgrid(0.22)
    env = sum(np.exp(-np.clip(t - d, 0, None) * 38) * (t >= d) for d in (0.0, 0.011, 0.023))
    x = noise(len(t), rng, 1)
    # keep the mid band: a moving average takes the harsh top off
    x = np.convolve(x, np.ones(5) / 5, mode="same")
    return x * env / 3


def shaker(rng, length=0.07, decay=60):
    t = tgrid(length)
    return noise(len(t), rng, 2) * np.exp(-t * decay)


def bass_note(f, dur):
    t = tgrid(dur)
    x = sum(np.sin(2 * np.pi * f * k * t) / k ** 1.4 for k in range(1, 6))
    env = np.minimum(1, t / 0.008) * np.exp(-t * 3.2) * np.minimum(1, (dur - t) / 0.02).clip(0, 1)
    return np.tanh(1.6 * x) * env


def marimba(f, dur=0.5):
    t = tgrid(dur)
    x = np.sin(2 * np.pi * f * t) + 0.45 * np.sin(2 * np.pi * 4 * f * t) * np.exp(-t * 28) \
        + 0.2 * np.sin(2 * np.pi * 2 * f * t) * np.exp(-t * 12)
    return x * np.exp(-t * 8) * np.minimum(1, t / 0.003)


def lead(f, dur):
    t = tgrid(dur + 0.12)
    vib = 1 + 0.004 * np.sin(2 * np.pi * 5.5 * t) * np.minimum(1, t / 0.15)
    ph = 2 * np.pi * np.cumsum(f * vib) / SR
    x = np.sin(ph) + 0.5 * np.sin(2 * ph) * np.exp(-t * 3) + 0.28 * np.sin(3 * ph) + 0.1 * np.sin(5 * ph)
    env = np.minimum(1, t / 0.012) * (0.55 + 0.45 * np.exp(-t * 6)) * np.minimum(1, (dur + 0.12 - t) / 0.1).clip(0, 1)
    return x * env


def pad(freqs, dur, rng):
    t = tgrid(dur)
    x = np.zeros(len(t))
    for f in freqs:
        for det in (-0.6, 0.0, 0.7):
            x += np.sin(2 * np.pi * (f + det) * t + rng.uniform(0, 6.28))
    env = np.minimum(1, t / 0.25) * np.minimum(1, (dur - t) / 0.25).clip(0, 1)
    return x * env / (3 * len(freqs))


# Minor-key loop i - VI - III - VII. Chord tones in semitones above the tonic.
CHORDS = [(0, 3, 7), (8, 12, 15), (3, 7, 10), (10, 14, 17)]
# Lead hooks: per bar, (position in 16ths, semitones above tonic, length in 16ths)
HOOKS = [
    [[(0, 7, 2), (3, 10, 2), (6, 12, 2), (8, 10, 3), (11, 7, 2), (14, 5, 2)],
     [(0, 12, 3), (3, 15, 2), (6, 12, 2), (10, 10, 2), (12, 7, 4)],
     [(0, 10, 2), (3, 12, 2), (6, 15, 2), (8, 17, 3), (11, 15, 2), (14, 12, 2)],
     [(0, 17, 3), (3, 14, 2), (6, 10, 2), (8, 12, 3), (12, 14, 4)]],
    [[(0, 12, 2), (2, 12, 1), (4, 15, 2), (7, 12, 2), (10, 10, 2), (12, 7, 3)],
     [(0, 8, 2), (3, 12, 2), (6, 15, 3), (10, 12, 2), (13, 10, 3)],
     [(0, 15, 2), (2, 15, 1), (4, 19, 2), (7, 15, 2), (10, 12, 2), (12, 10, 3)],
     [(0, 14, 3), (4, 17, 2), (7, 14, 2), (10, 12, 2), (12, 10, 4)]],
    [[(2, 7, 2), (4, 10, 2), (6, 12, 4), (11, 15, 2), (14, 12, 2)],
     [(0, 12, 2), (3, 8, 2), (6, 12, 2), (8, 15, 4), (14, 12, 2)],
     [(2, 10, 2), (4, 15, 2), (6, 19, 4), (11, 17, 2), (14, 15, 2)],
     [(0, 17, 2), (3, 14, 2), (6, 17, 2), (8, 22, 4), (13, 19, 3)]],
]
KICKS = [(0, 3, 6, 8, 11, 14), (0, 4, 7, 8, 12, 14), (0, 3, 8, 10, 11, 14)]
BASS = [(0, 3, 6, 10, 12), (0, 4, 7, 11, 14), (0, 3, 8, 11, 14)]


def make(seconds, seed):
    rng = np.random.default_rng(seed)
    bpm = [106, 110, 102, 112, 108, 104][seed % 6]
    key = [0, -2, 3, -4, 2, -5][seed % 6]            # tonic, semitones from A
    hooks = HOOKS[seed % len(HOOKS)]
    kicks, bassp = KICKS[seed % 3], BASS[(seed // 3) % 3]
    s16 = 60.0 / bpm / 4
    swing = 0.14 * s16
    n = int(seconds * SR)
    drums, low, mid, top, pads = (np.zeros(n) for _ in range(5))
    K, C = kick(), None
    nbars = int(np.ceil(seconds / (16 * s16)))
    duck = np.ones(n)
    for b in range(nbars):
        ch = CHORDS[b % 4]
        bar0 = b * 16 * s16

        def at(step):
            return int((bar0 + step * s16 + (swing if step % 2 else 0)) * SR)

        last = (b + 1) * 16 * s16 > seconds - 1.2
        for st in kicks:
            p = at(st)
            put(drums, p, K, 0.55)
            if p < n:
                e = min(n, p + int(0.16 * SR))
                duck[p:e] = np.minimum(duck[p:e], np.linspace(0.45, 1.0, e - p))
        for st in (4, 12):
            put(drums, at(st), clap(rng), 1.1)
        for st in range(16):
            acc = 0.6 if st % 4 == 2 else (0.36 if st % 2 == 0 else 0.24)
            put(drums, at(st), shaker(rng), acc)
        put(drums, at(10), shaker(rng, 0.22, 16), 0.4)       # open hat
        if b % 4 == 3 and not last:                           # fill into the next phrase
            for st, g in ((13, 0.5), (14, 0.65), (15, 0.8)):
                put(drums, at(st), clap(rng), g * 0.6)
        root = hz(key + ch[0] - 24 - (12 if ch[0] >= 8 else 0))
        for i, st in enumerate(bassp):
            nxt = bassp[i + 1] if i + 1 < len(bassp) else 16
            f = root * (1.5 if (i == len(bassp) - 1 and b % 2) else 1)
            put(low, at(st), bass_note(f, (nxt - st) * s16 * 0.95), 0.9)
        for st in (0, 3, 6, 10, 13):                          # marimba chord stabs
            for tone in ch:
                put(mid, at(st), marimba(hz(key + tone)), 0.2)
        arp = [ch[0] + 12, ch[1] + 12, ch[2] + 12, ch[1] + 12]
        for st in range(0, 16, 2):                            # light high arpeggio
            put(top, at(st + 1) if st % 4 == 2 else at(st), marimba(hz(key + arp[(st // 2) % 4]), 0.3), 0.07)
        put(pads, int(bar0 * SR), pad([hz(key + tone - 12) for tone in ch], 16 * s16, rng), 0.5)
        for st, semis, ln in hooks[b % 4]:
            sig = lead(hz(key + semis), ln * s16 * 0.92)
            put(top, at(st), sig, 0.26)
            put(top, at(st) + int(3 * s16 * SR), sig, 0.07)   # echo
    mix = drums * 0.9 + (low * 0.42 + mid * 1.25 + pads * 0.5) * duck + top * 1.7
    t = np.arange(n) / SR
    mix *= np.minimum(1, t / 0.05) * np.minimum(1, (seconds - t) / 1.2).clip(0, 1)
    mix = np.tanh(1.5 * mix / (np.abs(mix).max() + 1e-9)) / np.tanh(1.5)   # gentle limiter
    mix *= 0.89
    d = int(0.011 * SR)
    wide = top * 0.9 + mid * 0.5
    wide = wide / (np.abs(wide).max() + 1e-9) * 0.08
    left = mix + wide
    right = mix - np.concatenate([np.zeros(d), wide[:-d]])
    st = np.stack([left, right], axis=1)
    return st / max(1.0, np.abs(st).max() / 0.97)


if __name__ == "__main__":
    path, seconds, seed = sys.argv[1], float(sys.argv[2]), int(sys.argv[3])
    data = (make(seconds, seed) * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(data.tobytes())
