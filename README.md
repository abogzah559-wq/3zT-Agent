<p align="center"><img src="app/ui/icon.svg" width="72" alt="3zT"></p>

<h1 align="center">3zT Agent</h1>

<p align="center">A private, local AI agent for Windows that plans, uses your PC (with your permission), edits and generates images and videos, and remembers your chats.</p>

---

## Highlights

- **Three agents, one conversation.** Switch any time; the chat history stays.
  | Agent | Model | Runs on | Role |
  |---|---|---|---|
  | DeepSeek | DeepSeek `deepseek-flash` / `deepseek-v4-pro` (thinking mode) | Cloud API | The smartest one. Plans when you ask for a plan, executes with every tool when you ask it to do something. |
  | Executor | Qwen 3.5 9B (`qwen3.5:9b`) | Your GPU (Ollama) | The official model with content restrictions: executes with tools, sees images and video, controls the PC. |
  | Uncensored | Qwen 3.5 9B abliterated (`huihui_ai/qwen3.5-abliterated:9b`) | Your GPU (Ollama) | Same tools, no refusals, unrestricted image/video generation. Approval layer and hard limits still apply. |
- **Plan or execute, your call.** Ask DeepSeek for a plan and it writes one; one click then lets DeepSeek run it or hands it to the local executor.
- **Local image & video generation.** Built on [FreeVideo](https://github.com/FlashML-org/FreeVideo): MiniMax H3 videos with sound (up to 60 s, from 8 GB VRAM), H3 Image pictures up to 16 MP or Qwen-Image 2.1, picture editing and merging (up to 4 inputs), picture-to-video. Results land in the chat. The app starts FreeVideo by itself and frees the chat model's VRAM while generating.
- **DeepSeek can see.** Images and video frames are described by the local vision model before reaching DeepSeek.
- **Agent skills.** Built-in skills (AI generation, video editing & repair, images, subtitles & voice, web research, PC control, file organizing, Windows admin) plus Anthropic's open-source skills (PDF, Word, Excel, PowerPoint, GIF, web design, web-app testing, skill creator). Install more from any GitHub folder with a `SKILL.md`.
- **Reliable media operations.** Tested one-call video operations (trim, compress to a target size, vertical 9:16, merge, GIF, subtitles burn-in, logo, smooth 60 fps, repair presets for flicker/noise/halos/banding, AI upscaling) and image operations, with live progress.
- **Never silent.** A live status bar shows what the agent is doing with timers; empty or half-finished replies are retried automatically and every task ends with a summary.
- **Results in the chat.** Every image, video, audio or file the agent creates appears in the conversation with Open / Show-in-folder buttons.
- **One folder per chat.** Uploads and outputs live in `agent-workspace\chats\<chat>`; deleting a chat sends its folder and the files it created to the Recycle Bin.
- **Tasks survive refreshes.** Runs live on the server; the window can reload or reconnect and resume the live stream.
- **Approval layer.** Reading, browsing and creating new files in the workspace happen freely. Editing existing files (with a diff preview), writing outside the workspace, moving, commands/scripts, launching programs and mouse/keyboard control ask first (with an “always for this session” option). Deleting always asks and goes to the Recycle Bin.
- **Content policy per agent.** The executor refuses sexual/explicit content; the uncensored agent and DeepSeek have no app-side restrictions (optional LoRAs can be applied to their pictures). Hard limits for every agent: no sexual content involving minors, no sexual or degrading edits of real people's photos.
- **One-click shutdown.** Closing the window unloads the models from VRAM and stops the server, Ollama and the FreeVideo instance the app started. Nothing keeps running in the background.

## Tools

| Area | Tools |
|---|---|
| Files | list, read (txt/code/.docx/.xlsx), search by name, search inside files, write, exact edit, copy, move, delete to Recycle Bin, find duplicates |
| PC | PowerShell, Python, open files/apps/links, system status, screenshots, mouse click/drag/scroll, typing (any language), shortcuts, window focus, clipboard |
| Web | web search (no API key), read pages, download files and videos from YouTube/TikTok/X and more (yt-dlp) |
| Video & audio | view frames, media info, ffmpeg editing, speech-to-text with SRT subtitles (faster-whisper large-v3-turbo on GPU), neural voice-over (edge-tts) |
| Images | view, background removal (rembg), 2x/4x upscaling (Real-ESRGAN), resize/crop/convert/compress and more |
| Generation | text-to-image, image editing/merging, text-to-video and image-to-video with sound (FreeVideo: MiniMax H3, H3 Image, Qwen-Image 2.1) |
| Memory | `remember` saves lasting notes about you; editable in Settings |

## Install

1. Run **`install.bat`** once. It installs Ollama, Python, ffmpeg and yt-dlp with winget, tunes Ollama for a 12 GB GPU, downloads both Qwen models and creates the **3zT Agent** desktop shortcut.
2. Optional: **`install-extras.bat`** for subtitles, background removal, voice-over, upscaling and the document skills (isolated Python 3.12 environment + Node packages).
3. Optional: **`install-freevideo.bat`** for image/video generation. It downloads the FreeVideo launcher and opens it once to install ComfyUI and the models (about 40–60 GB).
   Upgrading from v1.1? **`remove-old-video-setup.cmd`** removes the old separate ComfyUI + SDXL/Wan setup (it shows what it found and asks before removing anything).
4. Open the app from the desktop shortcut, then add your DeepSeek key in **Settings → DeepSeek** ([platform.deepseek.com](https://platform.deepseek.com/api_keys)).

Missing local models are also downloaded automatically, with progress, the first time an agent needs them.

## Requirements

- Windows 10/11, Microsoft Edge (or Chrome)
- NVIDIA GPU with 12 GB VRAM recommended (tested target: RTX 4070 Super), 16 GB RAM
- Python 3.9+ (the app itself uses only the standard library)

## How the GPU stays smooth

- Only one local model sits in VRAM at a time; the agent you switch to loads, the others unload.
- While you use DeepSeek, the executor can stay loaded for an instant switch back (Settings).
- Image/video generation temporarily unloads the chat model, runs FreeVideo, asks it to free VRAM and reloads the chat model.
- Long chats are trimmed safely: old tool output is shortened first, then the oldest turns are dropped; only the latest images are kept.
- Live VRAM, RAM, CPU and GPU temperature in the sidebar.

## Shortcuts

`Enter` send · `Shift+Enter` new line · `Ctrl+N` new chat · `Ctrl+K` search chats · `Ctrl+,` settings · `Esc` stop / close. Drag & drop or paste files and images anywhere.

## Project layout

```
app/
  server.py     local HTTP server, window lifecycle, uploads, media streaming
  agent.py      agent loop, runs, approvals, context management, VRAM management
  llm.py        DeepSeek (SSE) and Ollama (NDJSON) streaming clients
  tools.py      tool definitions, approval rules and execution
  pc.py         screen capture, mouse and keyboard (Win32 via ctypes)
  web.py        web search and page reader
  videotools.py ready-made video/image operations with progress
  skills_mgr.py skills loader / installer
  skills/       built-in skills (SKILL.md folders)
  media.py      ffmpeg helpers and the optional extras
  freevideo.py  FreeVideo agent-API client (pictures, edits, videos)
  store.py      conversation storage
  stats.py      GPU / RAM / CPU monitor
  workers/      helper that runs inside the extras environment
  ui/           interface (HTML, CSS, JS — no build step)
scripts/        install, start and stop scripts
```

Data lives in `%APPDATA%\3zT-Agent` (settings, chats, memory, log). The DeepSeek key never leaves your PC except to call DeepSeek.

## Built on

[Ollama](https://github.com/ollama/ollama) · [Qwen 3.5](https://github.com/QwenLM) · [DeepSeek](https://api-docs.deepseek.com) · [huihui-ai abliterated models](https://huggingface.co/huihui-ai) · [FreeVideo](https://github.com/FlashML-org/FreeVideo) · [ComfyUI](https://github.com/comfyanonymous/ComfyUI) · [MiniMax H3](https://huggingface.co/MiniMaxAI) · [Qwen-Image](https://github.com/QwenLM/Qwen-Image) · [faster-whisper](https://github.com/SYSTRAN/faster-whisper) · [rembg](https://github.com/danielgatis/rembg) · [Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN) · [edge-tts](https://github.com/rany2/edge-tts) · [yt-dlp](https://github.com/yt-dlp/yt-dlp) · [Anthropic Agent Skills](https://github.com/anthropics/skills) · [FFmpeg](https://ffmpeg.org)
