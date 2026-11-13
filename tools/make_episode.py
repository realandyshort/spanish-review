#!/usr/bin/env python3
"""Build a Spanish review podcast MP3 (and optionally a captioned MP4) from an episode JSON file.

Usage: python3 make_episode.py episodes/2026-11-10.json out.mp3 [out.mp4]

Episode JSON keys:
  title, intro (English text)
  sections: list of {"name": English heading, "items": [[english, spanish], ...]}
  drills:   list of {"name": English heading, "items": [[english, spanish], ...]}  (said once each)
  recap:    {"name": ..., "items": [[english, spanish], ...]}
  conversation: {"intro": English, "lines": [["A"|"B", spanish, english], ...]}
  outro (English text)

Format per vocab item: English, pause to answer, Spanish slowly, Spanish slowly again.
Conversation: slow pass with English after each line, then a natural-speed pass in Spanish only.

The optional MP4 is the same audio with caption cards on a black background: the English prompt
appears first, the Spanish line joins it when it is spoken. Cards are drawn with Pillow and
stitched by ffmpeg, so no subtitle plugin is needed.
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
SPEAKERS = {"A": "Sofía", "B": "Diego"}   # names shown on the conversation caption cards
SR = 22050
CACHE = os.path.join(HERE, "cache")
SLOW, NATURAL = 1.35, 1.05   # length scale: higher is slower
EN_SPEAKER = 1               # Kokoro English voice (1 = af_bella); more natural than the Piper English voice
EN_PROMPT = 1.2              # English prompts in the vocab sections are slowed down
WORD_GAP = 0.45              # seconds between word groups on the first reading of a phrase
REPEAT_GAP = 1.7             # pause between the first and second Spanish reading
ITEM_GAP = 2.8               # pause after an item before the next English prompt
GLUE = {"el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del", "a", "al", "en", "con", "por",
        "para", "sin", "y", "o", "que", "no", "me", "te", "le", "les", "lo", "se", "nos", "mi", "tu", "su", "muy"}

# Video / caption card settings
W, H, FPS = 1280, 720, 10
FONT = "/System/Library/Fonts/Helvetica.ttc"   # index 0 regular, 1 bold, 4 light


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
    """Return list of (voice, text, scale, pause_after_seconds, card).
    card describes what the video shows while this segment (and its pause) plays:
      ("text", english)                      narration, headings
      ("item", english, spanish_or_None)     vocab / drill / recap
      ("conv", speaker, spanish, english_or_None)
    """
    seg = []
    say = lambda v, t, s=1.0, p=0.6, card=None: seg.append((v, t, s, p, card or ("text", t)))

    def item(en, es):
        answer = 3.0 + 0.32 * len(es.split())          # longer answers get a longer pause
        say("en", en, EN_PROMPT, answer, ("item", en, None))
        both = ("item", en, es)
        parts = chunks(es)
        if len(es.split()) >= 3 and len(parts) >= 2:   # phrases: word groups with gaps first, then whole
            for c in parts[:-1]:
                say("A", c, SLOW, WORD_GAP, both)
            say("A", parts[-1], SLOW, REPEAT_GAP, both)
        else:
            say("A", es, SLOW, REPEAT_GAP, both)
        say("A", es, SLOW, ITEM_GAP, both)

    say("en", ep["intro"], 1.0, 1.0)
    for sec in ep.get("sections", []):
        say("en", sec["name"], 1.0, 0.9)
        for en, es in sec["items"]:
            item(en, es)
    for d in ep.get("drills", []):
        say("en", d["name"], 1.0, 0.9)
        for en, es in d["items"]:
            say("en", en, EN_PROMPT, 2.7, ("item", en, None))
            say("A", es, SLOW, 2.0, ("item", en, es))
    if ep.get("recap"):
        say("en", ep["recap"]["name"], 1.0, 0.9)
        for en, es in ep["recap"]["items"]:
            item(en, es)
    conv = ep.get("conversation")
    if conv:
        say("en", conv["intro"], 1.0, 1.0)
        for who, es, en in conv["lines"]:
            say(who, es, SLOW, 0.7, ("conv", SPEAKERS[who], es, None))
            say("en", en, 1.0, 1.1, ("conv", SPEAKERS[who], es, en))
        say("en", "Now the same conversation at natural speed, in Spanish only.", 1.0, 1.2)
        for who, es, en in conv["lines"]:
            say(who, es, NATURAL, 0.55, ("conv", SPEAKERS[who], es, None))
    say("en", ep["outro"], 1.0, 0.5)
    return seg


# ---------- captioned video ----------

def _wrap(draw, text, font, max_w):
    lines, cur = [], []
    for w in text.split():
        trial = " ".join(cur + [w])
        if cur and draw.textbbox((0, 0), trial, font=font)[2] > max_w:
            lines.append(" ".join(cur)); cur = [w]
        else:
            cur.append(w)
    if cur:
        lines.append(" ".join(cur))
    return lines


def render_card(card):
    """Draw one caption card to a cached PNG and return its path."""
    from PIL import Image, ImageDraw, ImageFont
    os.makedirs(CACHE, exist_ok=True)
    key = hashlib.md5(json.dumps(card, ensure_ascii=False).encode()).hexdigest()
    path = os.path.join(CACHE, "card_" + key + ".png")
    if os.path.exists(path):
        return path
    img = Image.new("RGB", (W, H), "black")
    d = ImageDraw.Draw(img)
    reg = lambda s: ImageFont.truetype(FONT, s, index=0)
    bold = lambda s: ImageFont.truetype(FONT, s, index=1)
    light = lambda s: ImageFont.truetype(FONT, s, index=4)
    blocks = []   # (lines, font, color, gap_after)
    kind = card[0]
    if kind == "text":
        f = light(40) if len(card[1]) > 60 else reg(52)
        blocks.append((_wrap(d, card[1], f, W - 160), f, (235, 235, 235), 0))
    elif kind == "item":
        _, en, es = card
        f = reg(46)
        blocks.append((_wrap(d, en, f, W - 160), f, (170, 170, 170), 36))
        if es:
            f2 = bold(64)
            blocks.append((_wrap(d, es, f2, W - 160), f2, (255, 255, 255), 0))
    elif kind == "conv":
        _, who, es, en = card
        f0 = reg(34)
        blocks.append(([who], f0, (120, 170, 255), 18))
        f1 = bold(56)
        blocks.append((_wrap(d, es, f1, W - 160), f1, (255, 255, 255), 30 if en else 0))
        if en:
            f2 = light(40)
            blocks.append((_wrap(d, en, f2, W - 160), f2, (170, 170, 170), 0))
    # measure, then draw centred
    heights = []
    for lines, f, _, gap in blocks:
        lh = int(f.size * 1.25)
        heights.append(lh * len(lines) + gap)
    y = (H - sum(heights)) // 2
    for (lines, f, color, gap), hh in zip(blocks, heights):
        lh = int(f.size * 1.25)
        for ln in lines:
            tw = d.textbbox((0, 0), ln, font=f)[2]
            d.text(((W - tw) // 2, y), ln, font=f, fill=color)
            y += lh
        y += gap
    img.save(path, optimize=True)
    return path


def render_video(timeline, mp3, out, title):
    """timeline: list of (start_seconds, card). Writes an H.264 MP4 with AAC audio."""
    # merge consecutive identical cards
    merged = []
    for t, c in timeline:
        if merged and merged[-1][1] == c:
            continue
        merged.append((t, c))
    total = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                  "-of", "default=nw=1:nk=1", mp3], capture_output=True, text=True).stdout)
    lst = out + ".cards.txt"
    with open(lst, "w", encoding="utf-8") as f:
        for i, (t, c) in enumerate(merged):
            end = merged[i + 1][0] if i + 1 < len(merged) else total
            p = render_card(c)
            f.write(f"file '{p}'\nduration {max(end - t, 0.1):.3f}\n")
        f.write(f"file '{p}'\n")   # concat demuxer needs the last file repeated
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-i", mp3,
                    "-vf", f"fps={FPS},format=yuv420p", "-c:v", "libx264", "-tune", "stillimage",
                    "-preset", "veryfast", "-crf", "26", "-c:a", "aac", "-b:a", "96k", "-shortest",
                    "-movflags", "+faststart", "-metadata", f"title={title}",
                    "-metadata", "artist=Spanish Review", "-metadata", "album=Andy's Spanish Review", out], check=True)
    os.remove(lst)


def main(src, out, video=None):
    ep = json.load(open(src, encoding="utf-8"))
    seg = build(ep)
    with ThreadPoolExecutor(4) as ex:
        paths = list(ex.map(lambda s: synth(s[0], s[1], s[2]), seg))
    parts = [np.zeros(int(SR * 0.5), np.int16)]
    timeline = []
    for (v, t, s, pause, card), p in zip(seg, paths):
        timeline.append((sum(len(x) for x in parts) / SR, card))
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
    if video:
        render_video(timeline, out, video, ep["title"])
        print(f"captioned video -> {video} ({os.path.getsize(video)/1e6:.1f} MB)")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
