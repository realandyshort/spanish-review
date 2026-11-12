# spanish-review
Private weekly Spanish review podcast. Feed: https://realandyshort.github.io/spanish-review/feed.xml

- `episodes/YYYY-MM-DD.mp3` — published episodes (`feed.xml` is rebuilt from these by `tools/build_feed.py`)
- `tools/episodes/YYYY-MM-DD.json` — episode scripts; `tools/make_episode.py` turns one into an MP3
- `tools/tts/` — local text-to-speech engine and voices (not committed; sherpa-onnx v1.13.8 + Piper es_MX + Kokoro en)
- `claude/anki/` — Anki vocab exports the weekly job reads
- `claude/podcast/` — instructions the weekly job follows (`README.md`, `publishing.md`)

Published every Friday morning by a Claude Code scheduled task on Andy's Mac mini.
