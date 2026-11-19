---
name: web-research
description: Research anything online - search, read several sources, compare, summarize with links; also download files and videos from YouTube, TikTok, X, Instagram. Arabic triggers - ابحث، دور، وش أحدث، قارن، لخص، نزل، حمل من يوتيوب.
---
# Web research

1. `web_search` with a short, specific query (try English for technical topics, Arabic for local topics).
2. Open the 2-4 best results with `fetch_url` (official sites, docs, GitHub, reputable news) - never answer from snippets alone when details matter.
3. If results conflict, search again with a more specific query.
4. Answer in Arabic: the conclusion first, then key points, then a "المصادر" list with the links you actually read.
5. Dates matter: mention the date/version of what you found.

## Downloads
- `download` with the page URL handles YouTube/TikTok/X/Instagram (best quality MP4) and direct file links. audio_only=true gives MP3.
- After downloading, use `media_info` to confirm and tell the user the file name and size.
