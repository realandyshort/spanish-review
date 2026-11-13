#!/usr/bin/env python3
"""Build a Spanish review podcast MP3 (and optionally a captioned vertical MP4) from an episode JSON file.

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

The optional MP4 is the same audio with flashcard-style captions on a black, phone-shaped screen:
the English term appears first, the Spanish joins it when spoken, and each word lights up as it is
said (timing is estimated from word length). Narration is shown one sentence at a time. In vocab
items only the first English sentence is shown (anything after it is a spoken hint), and Spanish
alternatives written "X. O, Y." show as two lines. Cards are drawn with Pillow and stitched by
ffmpeg, so no subtitle plugin is needed.
"""
import hashlib, json, os, re, subprocess, sys, wave
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

# Video / caption card settings (vertical, phone-shaped)
W, H, FPS = 1080, 1920, 15
FONT = "/System/Library/Fonts/Helvetica.ttc"   # index 0 regular, 1 bold, 4 light
DIM, LIT, HOT = (120, 120, 120), (255, 255, 255), (255, 214, 79)   # unspoken, spoken, being spoken
SENT = re.compile(r"(?<=[.!?])\s+")


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


def tokens(text, kind):
    """Split spoken text into (word, visible, line_break_after) for the caption.
    Vocab English: only the first sentence is shown (anything after it is a spoken hint).
    Vocab Spanish: alternatives separated by ". O, " become separate lines; the "O," is hidden.
    """
    out, sent = [], 0
    ws = text.split()
    for i, w in enumerate(ws):
        last_in_sentence = w.endswith((".", "!", "?")) or i == len(ws) - 1
        vis = True
        if kind == "en" and sent > 0:
            vis = False
        if kind == "es" and w.lower().strip(",") == "o" and (i == 0 or ws[i - 1].endswith(".")):
            vis = False
        shown = w[:-1] if (w.endswith(".") and last_in_sentence) else w
        out.append((shown, vis, last_in_sentence and i < len(ws) - 1))
        if last_in_sentence:
            sent += 1
    return out


def build(ep):
    """Return list of (voice, text, scale, pause_after_seconds, blocks, hl).
    blocks: what the video shows while this segment plays, list of (style, text).
    hl: (block_index, word_offset) when this segment's words should light up inside that block, else None.
    """
    seg = []

    def say(v, t, s=1.0, p=0.6, blocks=None, hl=None):
        seg.append((v, t, s, p, blocks or [("narr", t)], hl))

    def narrate(text, pause):
        """Narration is spoken and shown one sentence at a time."""
        sents = SENT.split(text.strip())
        for i, st in enumerate(sents):
            say("en", st, 1.0, pause if i == len(sents) - 1 else 0.35, [("narr", st)], (0, 0))

    def item(en, es):
        answer = 3.0 + 0.32 * len(es.split())          # longer answers get a longer pause
        say("en", en, EN_PROMPT, answer, [("en", en)], (0, 0))
        both = [("en", en), ("es", es)]
        parts = chunks(es)
        off = 0
        if len(es.split()) >= 3 and len(parts) >= 2:   # phrases: word groups with gaps first, then whole
            for c in parts[:-1]:
                say("A", c, SLOW, WORD_GAP, both, (1, off)); off += len(c.split())
            say("A", parts[-1], SLOW, REPEAT_GAP, both, (1, off))
        else:
            say("A", es, SLOW, REPEAT_GAP, both, (1, 0))
        say("A", es, SLOW, ITEM_GAP, both, (1, 0))

    narrate(ep["intro"], 1.0)
    for sec in ep.get("sections", []):
        say("en", sec["name"], 1.0, 0.9, [("head", sec["name"])], (0, 0))
        for en, es in sec["items"]:
            item(en, es)
    for d in ep.get("drills", []):
        say("en", d["name"], 1.0, 0.9, [("head", d["name"])], (0, 0))
        for en, es in d["items"]:
            say("en", en, EN_PROMPT, 2.7, [("en", en)], (0, 0))
            say("A", es, SLOW, 2.0, [("en", en), ("es", es)], (1, 0))
    if ep.get("recap"):
        say("en", ep["recap"]["name"], 1.0, 0.9, [("head", ep["recap"]["name"])], (0, 0))
        for en, es in ep["recap"]["items"]:
            item(en, es)
    conv = ep.get("conversation")
    if conv:
        narrate(conv["intro"], 1.0)
        for who, es, en in conv["lines"]:
            name = SPEAKERS[who]
            say(who, es, SLOW, 0.7, [("who", name), ("ces", es)], (1, 0))
            say("en", en, 1.0, 1.1, [("who", name), ("ces", es), ("cen", en)], (2, 0))
        narrate("Now the same conversation at natural speed, in Spanish only.", 1.2)
        for who, es, en in conv["lines"]:
            say(who, es, NATURAL, 0.55, [("who", SPEAKERS[who]), ("ces", es)], (1, 0))
    narrate(ep["outro"], 0.5)
    return seg


# ---------- captioned video ----------

STYLE = {  # style -> (font index, size, base colour, gap after block)
    "narr": (4, 54, LIT, 0),
    "head": (0, 64, LIT, 0),
    "en":   (0, 58, (180, 180, 180), 48),
    "es":   (1, 84, LIT, 0),
    "who":  (0, 40, (120, 170, 255), 24),
    "ces":  (1, 72, LIT, 40),
    "cen":  (4, 50, (180, 180, 180), 0),
}


def layout(draw, toks, font, max_w):
    """Wrap visible tokens into lines; returns list of lines, each a list of (word, token_index)."""
    lines, cur, cur_w = [], [], 0
    space = draw.textbbox((0, 0), " ", font=font)[2]
    for i, (w, vis, brk) in enumerate(toks):
        if not vis:
            continue
        ww = draw.textbbox((0, 0), w, font=font)[2]
        if cur and cur_w + space + ww > max_w:
            lines.append(cur); cur, cur_w = [], 0
        cur.append((w, i)); cur_w += (space if len(cur) > 1 else 0) + ww
        if brk:
            lines.append(cur); cur, cur_w = [], 0
    if cur:
        lines.append(cur)
    return lines


def render_card(card):
    """card: tuple of (style, text, n_spoken, current). Draws a cached PNG and returns its path."""
    from PIL import Image, ImageDraw, ImageFont
    os.makedirs(CACHE, exist_ok=True)
    key = hashlib.md5(json.dumps(card, ensure_ascii=False).encode()).hexdigest()
    path = os.path.join(CACHE, "card_" + key + ".png")
    if os.path.exists(path):
        return path
    img = Image.new("RGB", (W, H), "black")
    d = ImageDraw.Draw(img)
    plan = []
    for style, text, n_spoken, current in card:
        idx, size, base, gap = STYLE[style]
        font = ImageFont.truetype(FONT, size, index=idx)
        kind = "en" if style == "en" else "es" if style == "es" else "x"
        lines = layout(d, tokens(text, kind), font, W - 160)
        plan.append((lines, font, base, gap, n_spoken, current, size))
    total = sum(int(sz * 1.3) * len(lines) + gap for lines, _, _, gap, _, _, sz in plan)
    y = (H - total) // 2
    for lines, font, base, gap, n_spoken, current, size in plan:
        lh = int(size * 1.3)
        space = d.textbbox((0, 0), " ", font=font)[2]
        for line in lines:
            widths = [d.textbbox((0, 0), w, font=font)[2] for w, _ in line]
            x = (W - (sum(widths) + space * (len(line) - 1))) // 2
            for (w, i), ww in zip(line, widths):
                if n_spoken is None:          # block not being spoken: plain base colour
                    col = base
                elif i == current:
                    col = HOT
                elif i < n_spoken:
                    col = LIT if base == LIT else base
                else:
                    col = DIM
                d.text((x, y), w, font=font, fill=col)
                x += ww + space
            y += lh
        y += gap
    img.save(path, optimize=True)
    return path


def word_times(text, dur):
    """Approximate start time of each word inside a segment, by character share."""
    ws = text.split()
    weights = [len(w.strip(".,¿?¡!;:")) + 2 for w in ws]
    tot = sum(weights)
    t, out = 0.0, []
    for wt in weights:
        out.append(t); t += dur * wt / tot
    return out


def render_video(timeline, mp3, out, title):
    """timeline: list of (start_seconds, card). Writes an H.264 MP4 with AAC audio."""
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
            f.write(f"file '{p}'\nduration {max(end - t, 0.05):.3f}\n")
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
    spoken = {}   # id(blocks) is not stable across segments, so track by block text
    for (v, t, s, pause, blocks, hl), p in zip(seg, paths):
        start = sum(len(x) for x in parts) / SR
        wav = load(p)
        dur = len(wav) / SR
        def card(n_by_block, current_block=None, current=-1):
            return tuple((st, tx, n_by_block.get(bi), current if bi == current_block else -1)
                         for bi, (st, tx) in enumerate(blocks))
        # words of blocks before the highlighted one are fully spoken; later blocks not yet
        n_by_block = {}
        if hl:
            bi, off = hl
            for j in range(len(blocks)):
                n_by_block[j] = len(blocks[j][1].split()) if j < bi else (0 if j > bi else off)
            ws = t.split()
            for k, wt in enumerate(word_times(t, dur)):
                n_by_block[bi] = off + k
                timeline.append((start + wt, card(n_by_block, bi, off + k)))
            n_by_block[bi] = off + len(ws)
            timeline.append((start + dur, card(n_by_block)))
        else:
            timeline.append((start, card({})))
        parts += [wav, np.zeros(int(SR * pause), np.int16)]
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
