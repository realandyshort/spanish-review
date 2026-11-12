#!/usr/bin/env python3
"""Rebuild feed.xml from the MP3s in episodes/ (named YYYY-MM-DD.mp3). Run from the repo root:
   python3 tools/build_feed.py"""
import glob, os, subprocess, datetime, email.utils
from xml.sax.saxutils import escape
BASE = "https://realandyshort.github.io/spanish-review"
def probe(p, key):
    return subprocess.run(["ffprobe", "-v", "error", "-show_entries", key, "-of", "default=nw=1:nk=1", p],
                          capture_output=True, text=True).stdout.strip()
items = []
for p in sorted(glob.glob("episodes/*.mp3"), reverse=True):
    date = os.path.basename(p)[:10]
    title = probe(p, "format_tags=title") or f"Spanish Review {date}"
    secs = int(float(probe(p, "format=duration")))
    when = datetime.datetime.strptime(date, "%Y-%m-%d").replace(hour=15, tzinfo=datetime.timezone.utc)
    url = f"{BASE}/{p}"
    items.append(f"""    <item>
      <title>{escape(title)}</title>
      <guid isPermaLink="false">spanish-review-{date}</guid>
      <pubDate>{email.utils.format_datetime(when)}</pubDate>
      <enclosure url="{url}" length="{os.path.getsize(p)}" type="audio/mpeg"/>
      <itunes:duration>{secs}</itunes:duration>
      <description>{escape(title)}</description>
    </item>""")
open("feed.xml", "w", encoding="utf-8").write(f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
  <channel>
    <title>Andy's Spanish Review</title>
    <link>{BASE}/</link>
    <language>en-us</language>
    <description>Personal weekly Spanish vocabulary review and conversation practice.</description>
    <itunes:author>Andy</itunes:author>
    <itunes:block>Yes</itunes:block>
    <itunes:explicit>false</itunes:explicit>
{chr(10).join(items)}
  </channel>
</rss>
""")
print(f"feed.xml written with {len(items)} episode(s)")
