"""Original dark, tense backing track for a drama Short, synthesized with numpy.
Usage: ambient.py out.wav SECONDS"""
import sys, wave
import numpy as np
SR = 44100
secs = float(sys.argv[2]); n = int(secs * SR); t = np.arange(n) / SR
rng = np.random.default_rng(22)
hz = lambda m: 440 * 2 ** ((m - 69) / 12)
out = np.zeros(n)
# low drone on A with slow movement
for m, g in [(33, .30), (40, .16), (45, .10)]:
    f = hz(m)
    out += g * np.sin(2 * np.pi * f * t + 0.3 * np.sin(2 * np.pi * .07 * t)) * (0.85 + 0.15 * np.sin(2 * np.pi * .05 * t + m))
# pad chords: Am, F, C, E (8 s each), soft attack and release
chords = [[57, 60, 64], [53, 57, 60], [48, 55, 64], [52, 56, 59]]
L = 8.0
for k in range(int(secs // L) + 1):
    s0 = int(k * L * SR); s1 = min(n, int((k + 1) * L * SR) + SR)
    if s0 >= n: break
    tt = np.arange(s1 - s0) / SR
    env = np.minimum(1, tt / 2.5) * np.minimum(1, np.maximum(0, (L + 1 - tt)) / 2.0)
    for m in chords[k % 4]:
        f = hz(m)
        v = sum(np.sin(2 * np.pi * f * (1 + d) * tt) for d in (-.003, 0, .003)) / 3
        out[s0:s1] += 0.07 * env * v
# heartbeat pulse every 1.2 s, quiet
for k in np.arange(2.4, secs - 1, 1.2):
    for off, g in ((0, 1), (0.22, .6)):
        s0 = int((k + off) * SR); m = min(n - s0, int(.35 * SR))
        if m <= 0: continue
        tt = np.arange(m) / SR
        f = 48 + 40 * np.exp(-tt * 30)
        out[s0:s0 + m] += 0.22 * g * np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-tt * 9)
# sparse piano-like notes
notes = [69, 72, 76, 74, 72, 71, 69, 64]
for i, k in enumerate(np.arange(4.0, secs - 2, 4.0)):
    s0 = int(k * SR); m = min(n - s0, int(3 * SR)); tt = np.arange(m) / SR
    f = hz(notes[i % len(notes)])
    tone = np.sin(2 * np.pi * f * tt) + .3 * np.sin(4 * np.pi * f * tt) + .1 * np.sin(6 * np.pi * f * tt)
    out[s0:s0 + m] += 0.06 * tone * np.exp(-tt * 1.6)
# simple reverb-ish smear and fades
d = int(.11 * SR)
for g in (.35, .2, .1):
    out[d:] += g * out[:-d]
out *= np.minimum(1, t / 2.0) * np.minimum(1, (secs - t) / 2.5)
out = out / np.abs(out).max() * 0.6
st = np.stack([out, np.roll(out, 300)], 1)
with wave.open(sys.argv[1], 'wb') as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((st * 32767).astype('<i2').tobytes())
print('music', secs)
