# Weekly Spanish review podcast (set up 2026-11-11)

After each week's Anki vocab upload, make Andy an audio episode (MP3) and send it in the chat.

## Format Andy chose
- Scope (updated 2026-11-12): each Friday episode covers the tutoring sessions from THAT week (Anki CSVs dated in the past 7 days) plus a general review of older vocab and concepts (rotate through earlier sessions and the combined deck; include grammar concepts, not only words). If there was no tutoring that week, make the whole episode a general review.
- Vocab review: English, pause to answer, then the Spanish twice, slowly.
- Verb drill: any conjugation drills from that week, English prompt then Spanish once.
- Conversation: two voices (Sofía = voice A, female; Diego = voice B, male). Slow pass with English after each line, then a natural-speed pass in Spanish only. Use this week's words, the recap words, and grammar he already has (present, preterite, ir a + infinitive). His own details (dog Papa, trip plans) are fine to use.
- Length: 10 to 15 minutes. Episode 1 was about 11 to 12 minutes with 24 new items, 10 drill forms, 10 recap items, 23 conversation lines.
- English prompts are written by hand for listening: short, no parentheses.

## Andy's feedback on episode 1 (2026-11-11) and what changed in version 2
- English in the vocab section was sometimes too fast. Now English prompts there are slowed (EN_PROMPT = 1.2) and the gap after each item is longer.
- Phrases needed more space between Spanish words. Now any item of 3 or more words is first read in word groups with a 0.35 second gap (small words stay attached to the next word), then read whole.
- The conversation was good. Left unchanged.
- The English voice sounded very robotic. Switched from the Piper English voice to Kokoro (af_bella). Awaiting Andy's verdict on version 2.

## Andy's feedback 2026-11-12 (applied in make_episode.py)
- Everything before the conversation was a little too fast. Pauses in the vocab, drill and recap sections are longer now: 3.0 s plus 0.32 s per word after the English prompt, 1.7 s between the two Spanish readings, 2.8 s after each item, 0.45 s between word groups; drills 2.7 s after the prompt and 2.0 s after the answer. Conversation unchanged.

## How to build an episode
1. Write `episodes/<date>.json` (copy the shape of `episodes/2026-11-10.json`).
2. Set up the voices in a folder `tts/` next to `make_episode.py` (the cloud workspace starts empty each session). All downloads come from GitHub, which is reachable; Hugging Face and PyPI are not.
   - Engine: `https://github.com/k2-fsa/sherpa-onnx/releases/download/v1.12.14/sherpa-onnx-v1.12.14-linux-x64-static.tar.bz2`, unpack and rename the folder to `tts/engine`.
   - Spanish voices, unpack into `tts/`: `https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-piper-<name>.tar.bz2` for `es_MX-claude-high` (female, also reads vocab) and `es_MX-ald-medium` (male).
   - English voice, unpack into `tts/`: `https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/kokoro-en-v0_19.tar.bz2` (about 320 MB).
3. Run `python3 make_episode.py episodes/<date>.json "Spanish Review <date>.mp3"` (about 5 minutes), then send the MP3.
4. (Since 2026-11-12) Pass a third argument to also get the captioned video: `python3 tools/make_episode.py tools/episodes/<date>.json episodes/<date>.mp3 episodes/<date>.mp4`. The video is black with white caption cards (English prompt, then the Spanish joins it; speaker names in the conversation), 1280x720, about 7 MB per episode. Cards are drawn with Pillow and stitched by ffmpeg; no extra Claude work.

## Status
- Episode 1 (2026-11-10 vocab, recap from 2026-11-06): version 1 and version 2 delivered 2026-11-11. Claude cannot listen to audio, so sound quality relies on Andy's feedback.
- Proposed, not yet built: a catch-up series by topic for the roughly 1,060 older cards, once Andy confirms the format.
