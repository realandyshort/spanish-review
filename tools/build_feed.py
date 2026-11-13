#!/usr/bin/env python3
"""Rebuild the podcast feeds from the files in episodes/ (named YYYY-MM-DD.mp3 / .mp4). Run from the repo root:
   python3 tools/build_feed.py
Writes feed.xml (audio, for Overcast etc.) and feed-video.xml (captioned video, for Apple Podcasts)."""
import glob, os, subprocess, datetime, email.utils, hashlib
from xml.sax.saxutils import escape
BASE = "https://realandyshort.github.io/spanish-review"

def probe(p, key):
    return subprocess.run(["ffprobe", "-v", "error", "-show_entries", key, "-of", "default=nw=1:nk=1", p],
                          capture_output=True, text=True).stdout.strip()

def write_feed(out, ext, mime, title):
    items = []
    for p in sorted(glob.glob(f"episodes/*.{ext}"), reverse=True):
        date = os.path.basename(p)[:10]
        ep_title = probe(p, "format_tags=title") or f"Spanish Review {date}"
        secs = int(float(probe(p, "format=duration")))
        when = datetime.datetime.strptime(date, "%Y-%m-%d").replace(hour=15, tzinfo=datetime.timezone.utc)
        url = f"{BASE}/{p}"
        # video guid carries a short hash of the file, so a re-rendered video shows up as a fresh episode in apps
        tag = "" if ext == "mp3" else "-video-" + hashlib.md5(open(p, "rb").read()).hexdigest()[:8]
        items.append(f"""    <item>
      <title>{escape(ep_title)}</title>
      <guid isPermaLink="false">spanish-review-{date}{tag}</guid>
      <pubDate>{email.utils.format_datetime(when)}</pubDate>
      <enclosure url="{url}" length="{os.path.getsize(p)}" type="{mime}"/>
      <itunes:duration>{secs}</itunes:duration>
      <description>{escape(ep_title)}</description>
    </item>""")
    open(out, "w", encoding="utf-8").write(f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
  <channel>
    <title>{escape(title)}</title>
    <link>{BASE}/</link>
    <language>en-us</language>
    <description>Personal weekly Spanish vocabulary review and conversation practice.</description>
    <itunes:author>Andy</itunes:author>
    <itunes:image href="{BASE}/artwork.jpg"/>
    <image><url>{BASE}/artwork.jpg</url><title>{escape(title)}</title><link>{BASE}/</link></image>
    <itunes:block>Yes</itunes:block>
    <itunes:explicit>false</itunes:explicit>
{chr(10).join(items)}
  </channel>
</rss>
""")
    print(f"{out} written with {len(items)} episode(s)")

write_feed("feed.xml", "mp3", "audio/mpeg", "Andy's Spanish Review")
write_feed("feed-video.xml", "mp4", "video/mp4", "Andy's Spanish Review (Video)")
