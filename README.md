<p align="center"><img src="app/ui/icon.svg" width="72" alt="3zT"></p>

<h1 align="center">3zT Agent</h1>

<p align="center">A private, local AI agent for Windows that plans, uses your PC (with your permission), edits and generates images and videos, and remembers your chats. Arabic-first (Saudi dialect), one installer, nothing else to set up.</p>

---

## Highlights

- **Three agents, one conversation.** Switch any time; the chat history stays.
  | Agent | Model | Runs on | Role |
  |---|---|---|---|
  | DeepSeek | `deepseek-flash` / `deepseek-v4-pro` (thinking mode) | Cloud API | The smartest one. Plans when you ask for a plan, executes with every tool when you ask it to do something. |
  | Executor | Qwen 3.5 9B (Q4_K_M + vision) | Your GPU | The official model with content restrictions: executes with tools, sees images and video, controls the PC. |
  | Uncensored | Inkling 2 Mini Uncensored (AtomicChat build of Thinking Machines' Inkling 2 Mini, + vision) | Your GPU | Same tools, no refusals. Approval layer and hard limits still apply. |
- **Everything in one installer.** Python, ffmpeg, yt-dlp, Node.js, llama.cpp (CUDA) and Real-ESRGAN ship inside the app. Models download once from inside the app (**Settings → Setup & downloads**) with progress and resume.
- **Smart use of VRAM and RAM.** One local model in the GPU at a time. The uncensored agent has a *fast* build that sits fully in a 12 GB card and a *quality* build that moves part of its experts to system RAM; *auto* picks quality only when enough RAM is free (4 GB always stay free for Windows) and falls back to fast if it does not fit or misbehaves. 8-bit KV cache and per-model context limits keep long chats from spilling over.
- **Saudi dialect.** Replies are written in Saudi Arabic; a reply that slips into another dialect is rewritten automatically.
- **Arabic + English text that stays in order.** Every paragraph, list item, table cell and the input box picks its direction from its content, so English words inside Arabic sentences no longer scramble the line.
- **Local image & video generation.** Built on [FreeVideo](https://github.com/FlashML-org/FreeVideo): MiniMax H3 videos with sound, H3 Image / Qwen-Image 2.1 pictures, picture editing and merging, picture-to-video, video outpainting. The app starts FreeVideo by itself and frees the chat model's VRAM while generating.
- **Agent skills.** Built-in skills plus:
  - **image-director** — brief → generate → inspect → fix, for pro pictures from casual requests.
  - **video-director** — shot list → AI clips / motion graphics → voice, music, captions → platform export.
  - **[ffmpeg-skill](https://github.com/kajisho5/ffmpeg-skill)** — 42 tested FFmpeg editing scripts with delivery checks.
  - **[HyperFrames](https://github.com/heygen-com/hyperframes)** — motion graphics and videos written in HTML, rendered locally.
  - **[agent-browser](https://github.com/vercel-labs/agent-browser)** — fast browser automation using your installed Edge/Chrome.
  - **[ponytail](https://github.com/DietrichGebert/ponytail)** — minimal, clean code when the agent writes scripts.
  - Anthropic's open-source skills (PDF, Word, Excel, PowerPoint, GIF, web design, web-app testing, skill creator). Install more from any GitHub folder with a `SKILL.md`.
- **Never silent.** A live status bar shows what the agent is doing with timers; empty or half-finished replies are retried automatically and every task ends with a summary.
- **Results in the chat.** Every image, video, audio or file the agent creates appears in the conversation with Open / Show-in-folder buttons.
- **One folder per chat.** Uploads and outputs live in `agent-workspace\chats\<chat>`; deleting a chat sends its folder and the files it created to the Recycle Bin.
- **Approval layer.** Reading, browsing and creating new files in the workspace happen freely. Editing existing files (with a diff preview), writing outside the workspace, moving, commands/scripts, launching programs and mouse/keyboard control ask first. Deleting always asks and goes to the Recycle Bin.
- **Content policy.** The executor refuses sexual/explicit content; the uncensored agent and DeepSeek have no app-side restrictions. Hard limits for every agent, enforced by the app itself before any generation: no sexual content involving minors, no sexual or degrading edits of real people's photos.
- **One-click shutdown.** Closing the window stops the model server, FreeVideo (if the app started it) and the app. Nothing keeps running in the background.

## Install

1. Download **`3zT-Agent-Setup-<version>.exe`** from the [Releases](../../releases) page and run it (no admin rights needed).
2. Open **3zT Agent**. The first time, it opens **Settings → Setup & downloads**: download the two local models (about 16 GB in total). You can chat with DeepSeek while they download.
3. Optional on the same screen: FreeVideo for image/video generation (40–60 GB), GPU speech-to-text libraries, and the higher-quality uncensored build.
4. Add your DeepSeek key in **Settings → DeepSeek** ([platform.deepseek.com](https://platform.deepseek.com/api_keys)).

## Requirements

- Windows 10/11 (64-bit), Microsoft Edge or Chrome
- NVIDIA GPU with 12 GB VRAM recommended, 16 GB RAM
- About 20 GB free disk for the app and models (+40–60 GB for FreeVideo)

## Tools

| Area | Tools |
|---|---|
| Files | list, read (txt/code/.docx/.xlsx), search by name, search inside files, write, exact edit, copy, move, delete to Recycle Bin, find duplicates |
| PC | PowerShell, Python, open files/apps/links, system status, screenshots, mouse click/drag/scroll, typing (any language), shortcuts, window focus, clipboard |
| Web | web search (no API key), read pages, download files and videos from YouTube/TikTok/X and more (yt-dlp), browser automation (agent-browser) |
| Video & audio | view frames, media info, one-call video operations, ffmpeg-skill, speech-to-text with SRT subtitles (faster-whisper), neural voice-over (edge-tts) |
| Images | view, background removal (rembg), 2x/4x upscaling (Real-ESRGAN), resize/crop/convert/compress and more |
| Generation | text-to-image, image editing/merging, text-to-video and image-to-video with sound, video outpainting, HTML motion graphics (HyperFrames) |
| Memory | `remember` saves lasting notes about you; editable in Settings |

## Shortcuts

`Enter` send · `Shift+Enter` new line · `Ctrl+N` new chat · `Ctrl+K` search chats · `Ctrl+,` settings · `Esc` stop / close. Drag & drop or paste files and images anywhere.

## Building from source

The installer is built by GitHub Actions (`.github/workflows/build.yml`) on every `v*` tag:
`build/build-runtime.ps1` assembles `runtime\` (Python 3.12 with the media/document packages, ffmpeg, yt-dlp,
Node.js 22 with hyperframes/agent-browser/docx/pptxgenjs, llama.cpp CUDA 12, Real-ESRGAN) and
`build/3zT-Agent.iss` packs it with Inno Setup. To run from a checkout, install Python 3.9+ and start
`3zT-Agent.vbs`; missing tools fall back to what is on `PATH`, and llama.cpp is downloaded on first use.

## Project layout

```
app/
  server.py      local HTTP server, window lifecycle, uploads, media streaming
  agent.py       agent loop, runs, approvals, context management, dialect check, VRAM management
  localai.py     llama.cpp server: model files, downloads, VRAM/RAM plan, start/stop
  llm.py         DeepSeek and local streaming clients (OpenAI-style SSE)
  setup_jobs.py  first-run downloads and add-ons with progress
  runtime.py     bundled tools on PATH for the app and every child process
  tools.py       tool definitions, approval rules, hard limits and execution
  pc.py          screen capture, mouse and keyboard (Win32 via ctypes)
  web.py         web search and page reader
  videotools.py  ready-made video/image operations with progress
  skills_mgr.py  skills loader / installer
  skills/        built-in skills (SKILL.md folders)
  media.py       ffmpeg helpers and the media extras
  freevideo.py   FreeVideo agent-API client (pictures, edits, videos)
  outpaint.py    video outpainting
  store.py       conversation storage
  stats.py       GPU / RAM / CPU monitor
  workers/       helper for speech-to-text, background removal and voice-over
  ui/            interface (HTML, CSS, JS — no build step)
build/           runtime build script and installer definition
```

Data lives in `%APPDATA%\3zT-Agent` (settings, chats, memory, log) and models in `%LOCALAPPDATA%\3zT-Agent\models`. The DeepSeek key never leaves your PC except to call DeepSeek.

## Built on

[llama.cpp](https://github.com/ggml-org/llama.cpp) · [Qwen 3.5](https://github.com/QwenLM) · [Inkling 2 Mini](https://thinkingmachines.ai) · [AtomicChat GGUF builds](https://huggingface.co/AtomicChat) · [DeepSeek](https://api-docs.deepseek.com) · [FreeVideo](https://github.com/FlashML-org/FreeVideo) · [ComfyUI](https://github.com/comfyanonymous/ComfyUI) · [MiniMax H3](https://huggingface.co/MiniMaxAI) · [Qwen-Image](https://github.com/QwenLM/Qwen-Image) · [HyperFrames](https://github.com/heygen-com/hyperframes) · [ffmpeg-skill](https://github.com/kajisho5/ffmpeg-skill) · [agent-browser](https://github.com/vercel-labs/agent-browser) · [ponytail](https://github.com/DietrichGebert/ponytail) · [faster-whisper](https://github.com/SYSTRAN/faster-whisper) · [rembg](https://github.com/danielgatis/rembg) · [Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN) · [edge-tts](https://github.com/rany2/edge-tts) · [yt-dlp](https://github.com/yt-dlp/yt-dlp) · [Anthropic Agent Skills](https://github.com/anthropics/skills) · [FFmpeg](https://ffmpeg.org) · [Inno Setup](https://jrsoftware.org/isinfo.php)
