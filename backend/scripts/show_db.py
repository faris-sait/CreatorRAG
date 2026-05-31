"""Pretty-print the CreatoFlow database — no psql required.

Usage:
    python -m scripts.show_db            # videos + pairs summary
    python -m scripts.show_db --full     # also print transcripts
"""
from __future__ import annotations

import asyncio
import json
import sys

from app import db, qdrant_store


def _meta(v) -> dict:
    m = v["metadata"]
    return m if isinstance(m, dict) else json.loads(m)


async def main() -> None:
    full = "--full" in sys.argv
    await db.init_pool()
    async with db.pool().acquire() as c:
        vids = await c.fetch("SELECT * FROM videos ORDER BY created_at")
        pairs = await c.fetch("SELECT * FROM pairs ORDER BY created_at")

    print(f"\n📹 VIDEOS — {len(vids)} row(s)\n" + "=" * 80)
    for v in vids:
        m = _meta(v)
        print(f"{v['platform'].upper():9} {v['status']:8} @{m.get('creator')}")
        print(f"   id         {v['id']}")
        print(f"   followers  {m.get('follower_count')}")
        print(f"   views      {m.get('views')}   likes {m.get('likes')}   comments {m.get('comments')}")
        print(f"   engagement {v['engagement_rate']}%   chunks {v['num_chunks']}")
        print(f"   hashtags   {', '.join(m.get('hashtags') or []) or '—'}")
        print(f"   source     {m.get('source')}")
        print(f"   url        {v['url']}")
        if full and v["transcript"]:
            print(f"   transcript {v['transcript'][:500]}...")
        print("-" * 80)

    print(f"\n🔗 PAIRS — {len(pairs)} row(s)\n" + "=" * 80)
    for p in pairs:
        print(f"   {p['id']}   A={p['a_video_id']}  B={p['b_video_id']}")

    try:
        n = await qdrant_store.count()
        print(f"\n🧠 QDRANT — {n} vector(s) in '{qdrant_store.settings.qdrant_collection}'")
    except Exception as e:  # noqa: BLE001
        print(f"\n🧠 QDRANT — unavailable: {e}")

    await db.close_pool()


if __name__ == "__main__":
    asyncio.run(main())
