# Publishing the podcast to Overcast

Each episode goes to Andy's Overcast through an RSS feed hosted on a free GitHub Pages site.

- GitHub user: realandyshort. Repository: `spanish-review` (public). Created 2026-11-12, Pages on, deploy from branch `main`, root.
- Feed address (Andy confirmed it works in Overcast on 2026-11-12): `https://realandyshort.github.io/spanish-review/feed.xml`
- Repo layout: `feed.xml` at the root, MP3s in `episodes/` named `YYYY-MM-DD.mp3`, tools in `tools/`. `tools/build_feed.py` (copy here as `claude/podcast/build_feed.py`) rebuilds `feed.xml` from every MP3 in `episodes/`; the episode title comes from the MP3 title tag, the date from the file name.

## To publish an episode
1. Get push access to `realandyshort/spanish-review` (if the session has an add_repo style tool, request the repo with push access), then clone it.
2. Copy the new MP3 to `episodes/<date>.mp3`, copy the episode JSON to `tools/episodes/`, run `python3 tools/build_feed.py` from the repo root, commit, push to `main`.
3. Check `https://realandyshort.github.io/spanish-review/feed.xml` lists the new episode a minute or two later.
4. Add a line to the log below.

Andy wants this automated. He does not want to upload files by hand each week.

## History
- 2026-11-12: the Cowork session that built episode 1 could not push. First it had no linked GitHub account; after Andy linked it, the error became "GitHub access to this repository is not enabled for this session" and that session had no tool to attach a repo. Andy uploaded the first files by hand through GitHub's web page.
- 2026-11-12: a Friday scheduled task was created to build and publish weekly. Whether a scheduled session can push is unproven until its first run.
- 2026-11-12: first run of the Cowork scheduled task. It built episode 2 but could not push. Cloning worked (the repo is public). `git push origin main` failed with: "remote: access denied by the git proxy: realandyshort/spanish-review is not in this session's authorized repository set, so the proxy will not inject a credential for it. To fix, add the repository to the session's sources." (HTTP 403). The session had no tool for adding a repository; three tool searches found none. So a scheduled session cannot push unless the repository is added to the scheduled task's sources when the task is set up. The MP3 and rebuilt feed.xml were sent to Andy as files to upload by hand. Note for the next run: if 2026-11-12.mp3 is missing from the repo's `episodes/` folder, Andy has not uploaded it yet; the episode JSON is in the project and the MP3 can be rebuilt from it.

## Published episodes (keep this current; it prevents repeats)
| File | Covers session dates | Recap drawn from | Published |
|---|---|---|---|
| episodes/2026-11-10.mp3 | 2026-11-10 | 2026-11-06 | 2026-11-12, by hand |
| episodes/2026-11-12.mp3 | 2026-11-06 | 2026-11-03 (travel and restaurant items) | 2026-11-12, by hand (Claude Code session pushed it) |

## Automation since 2026-11-12 (current setup)
- The Cowork scheduled task is paused. Publishing now runs as a **Claude Code scheduled task on Andy's Mac mini** (task id `spanish-review-weekly`, Fridays 8:05am Pacific). It works in the local clone `~/Developer/spanish-review` and pushes with the GitHub login in the Mac's keychain, so no repo-access step is needed.
- The voices and engine are installed once on the mini at `tools/tts/` (gitignored). Engine is sherpa-onnx **v1.13.8**; v2.x removed the built-in phonemizer that `make_episode.py` uses, so do not upgrade it.
- Vocab lives in this repo under `claude/anki/`. Each run also copies any new `spanish_anki_*.csv` from `~/Downloads` into `claude/anki/` before deciding what to build.
- Two feeds: `feed.xml` (audio, Overcast) and `feed-video.xml` (captioned MP4, Apple Podcasts: `https://realandyshort.github.io/spanish-review/feed-video.xml`). `tools/build_feed.py` writes both. Each run builds the MP3 and the MP4. Video episode IDs include a short hash of the MP4, so a re-rendered video shows up as a fresh episode in Apple Podcasts (the app otherwise keeps the copy it already fetched).
- Every Friday an episode is built: that week's sessions (CSVs dated in the past 7 days) plus a general review of older material. The table above records what each episode covered so reviews rotate instead of repeating. After publishing, the run adds a row to the table.

## Next episode plan (the run follows this, then deletes the note)
- 2026-11-14: Andy asked for a general review across ALL lessons so far (every CSV in claude/anki, including 00_All_Topics_Combined.csv). No single week's focus; mix topics and grammar concepts, keep it 10 to 15 minutes.
