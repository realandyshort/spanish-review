#!/usr/bin/env python3
"""Build a Spanish review podcast MP3 from an episode JSON file.

Usage: python3 make_episode.py episodes/2026-11-10.json out.mp3

Episode JSON keys:
  title, intro (English text)
  sections: list of {"name": English heading, "items": [[english, spanish], ...]}
  drills:   list of {"name": English heading, "items": [[english, spanish], ...]}  (said once each)
  recap:    {"name": ..., "items": [[english, spanish], ...]}
  conversation: {"intro": English, "lines": [["A"|"B", spanish, english], ...]}
  outro (English text)

Format per vocab item: English, pause to answer, Spanish slowly, Spanish slowly again.
Conversation: slow pass with English after each line, then a natural-speed pass in Spanish only.
"""
import hashlib, json, os, subprocess, sys, wave
from concurrent.futures import ThreadPoolExecutor
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
TTS = os.path.join(HERE, "tts")
ENGINE = os.path.join(TTS, "engine/bin/sherpa-onnx-offline-tts")
VOICES = {  # name -> model folder suffix
    "en": "en_US-lessac-medium",   # English narrator
    "A": "es_MX-claude-high",      # Mexican Spanish, female (also reads vocab)
    "B": "es_MX-ald-medium",       # Mexican Spanish, male
}
SR = 22050
CACHE = os.path.join(HERE, "cache")
SLOW, NATURAL = 1.35, 1.05   # length scale: higher is slower
EN_SPEAKER = 1               # Kokoro English voice (1 = af_bella); more natural than the Piper English voice
EN_PROMPT = 1.2              # English prompts in the vocab sections are slowed down
WORD_GAP = 0.35              # seconds between word groups on the first reading of a phrase
GLUE = {"el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del", "a", "al", "en", "con", "por",
        "para", "sin", "y", "o", "que", "no", "me", "te", "le", "les", "lo", "se", "nos", "mi", "tu", "su", "muy"}


def chunks(es):
    """Split a phrase into word groups, keeping small words with the word that follows."""
    out, cur = [], []
    for w in es.split():
        cur.append(w)
        if w.lower().strip(".,¿?¡!") not in GLUE:
            out.append(" ".join(cur)); cur = []
    if cur:
        out.append(" ".join(cur))
    return out


def synth(voice, text, scale):
    os.makedirs(CACHE, exist_ok=True)
    key = hashlib.md5(f"{voice}|{scale}|{text}".encode()).hexdigest()
    path = os.path.join(CACHE, key + ".wav")
    if not os.path.exists(path) and voice == "en":
        k = os.path.join(TTS, "kokoro-en-v0_19")
        raw = path + ".raw.wav"
        r = subprocess.run([ENGINE, f"--kokoro-model={k}/model.onnx", f"--kokoro-voices={k}/voices.bin",
                            f"--kokoro-tokens={k}/tokens.txt", f"--kokoro-data-dir={k}/espeak-ng-data",
                            f"--kokoro-length-scale={scale}", f"--sid={EN_SPEAKER}",
                            f"--output-filename={raw}", text], capture_output=True, text=True)
        if r.returncode != 0 or not os.path.exists(raw):
            raise RuntimeError(f"TTS failed for {text!r}: {r.stderr[-300:]}")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", raw, "-ar", str(SR), "-ac", "1", path], check=True)
        os.remove(raw)
    if not os.path.exists(path):
        v = VOICES[voice]
        d = os.path.join(TTS, "vits-piper-" + v)
        r = subprocess.run([ENGINE, f"--vits-model={d}/{v}.onnx", f"--vits-tokens={d}/tokens.txt",
                            f"--vits-data-dir={d}/espeak-ng-data", f"--vits-length-scale={scale}",
                            f"--output-filename={path}", text], capture_output=True, text=True)
        if r.returncode != 0 or not os.path.exists(path):
            raise RuntimeError(f"TTS failed for {text!r}: {r.stderr[-300:]}")
    return path


def load(path):
    with wave.open(path) as w:
        assert w.getframerate() == SR and w.getnchannels() == 1
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    # trim leading/trailing silence so pauses are controlled here
    loud = np.where(np.abs(x) > 300)[0]
    if not len(loud):
        return x
    x = x[max(loud[0] - 400, 0): loud[-1] + 1200].astype(float)
    voiced = x[np.abs(x) > 300]
    gain = min(3000 / (np.sqrt((voiced ** 2).mean()) + 1), 30000 / np.abs(x).max())  # even out voice levels
    return (x * gain).astype(np.int16)


def build(ep):
    """Return list of (voice, text, scale, pause_after_seconds)."""
    seg = []
    say = lambda v, t, s=1.0, p=0.6: seg.append((v, t, s, p))

    def item(en, es):
        answer = 2.5 + 0.28 * len(es.split())          # longer answers get a longer pause
        say("en", en, EN_PROMPT, answer)
        parts = chunks(es)
        if len(es.split()) >= 3 and len(parts) >= 2:   # phrases: word groups with gaps first, then whole
            for c in parts[:-1]:
                say("A", c, SLOW, WORD_GAP)
            say("A", parts[-1], SLOW, 1.3)
        else:
            say("A", es, SLOW, 1.2)
        say("A", es, SLOW, 2.2)

    say("en", ep["intro"], 1.0, 1.0)
    for sec in ep.get("sections", []):
        say("en", sec["name"], 1.0, 0.9)
        for en, es in sec["items"]:
            item(en, es)
    for d in ep.get("drills", []):
        say("en", d["name"], 1.0, 0.9)
        for en, es in d["items"]:
            say("en", en, EN_PROMPT, 2.2)
            say("A", es, SLOW, 1.6)
    if ep.get("recap"):
        say("en", ep["recap"]["name"], 1.0, 0.9)
        for en, es in ep["recap"]["items"]:
            item(en, es)
    conv = ep.get("conversation")
    if conv:
        say("en", conv["intro"], 1.0, 1.0)
        for who, es, en in conv["lines"]:
            say(who, es, SLOW, 0.7)
            say("en", en, 1.0, 1.1)
        say("en", "Now the same conversation at natural speed, in Spanish only.", 1.0, 1.2)
        for who, es, en in conv["lines"]:
            say(who, es, NATURAL, 0.55)
    say("en", ep["outro"], 1.0, 0.5)
    return seg


def main(src, out):
    ep = json.load(open(src, encoding="utf-8"))
    seg = build(ep)
    with ThreadPoolExecutor(4) as ex:
        paths = list(ex.map(lambda s: synth(s[0], s[1], s[2]), seg))
    parts = [np.zeros(int(SR * 0.5), np.int16)]
    for (v, t, s, pause), p in zip(seg, paths):
        parts += [load(p), np.zeros(int(SR * pause), np.int16)]
    audio = np.concatenate(parts)
    tmp = out + ".wav"
    with wave.open(tmp, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(audio.tobytes())
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", tmp, "-af", "loudnorm=I=-18:TP=-2",
                    "-ar", "44100", "-codec:a", "libmp3lame", "-b:a", "96k",
                    "-metadata", f"title={ep['title']}", "-metadata", "artist=Spanish Review",
                    "-metadata", "album=Andy's Spanish Review", out], check=True)
    os.remove(tmp)
    print(f"{len(seg)} segments, {len(audio)/SR/60:.1f} minutes -> {out}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
