# Instagram fixtures (demo kill-switch)

Instagram is the one flaky dependency in this project. To guarantee a live demo
never hard-fails on an IG block, the app can serve a **cached reel** from this
folder instead of hitting Apify.

When it's used:
- `USE_FIXTURES=true` (default) → all Instagram URLs are served from here.
- `USE_FIXTURES=false` + valid `APIFY_TOKEN` → live Apify, but if Apify fails
  and a matching fixture exists, the app **automatically falls back** to it.

## File format

`instagram/<shortcode>.json`, falling back to `instagram/default.json`. The
shortcode is the segment after `/reel/` or `/p/` in the URL. Shape:

```json
{
  "title": "...", "creator": "username", "follower_count": 248000,
  "views": 1840000, "likes": 132400, "comments": 2870,
  "hashtags": ["..."], "upload_date": "2026-04-12", "duration": 47,
  "transcript_segments": [{"start": 0.0, "end": 3.4, "text": "..."}]
}
```

Either provide `transcript_segments` directly (fully offline, no Whisper) or
`"audio_file": "myreel.mp3"` pointing at a file in `fixtures/audio/` for the
pipeline to transcribe via Whisper.

## Regenerating a real fixture

With an Apify token, capture a real reel once and save it so the demo is
reproducible:

```bash
# pseudo: run apify/instagram-scraper for the reel + profile-scraper for followers,
# then write the normalized fields above to instagram/<shortcode>.json
```

This is cached **input** data, not hard-coded output — every transcript chunk,
embedding, retrieval, and answer is still produced dynamically at runtime.
