---
name: subtitles-voice
description: Subtitles and audio - transcribe speech to text, make SRT subtitles, translate subtitles, burn subtitles into video, voice-over / text-to-speech in Arabic or English, extract or clean audio. Arabic triggers - ترجمة، تفريغ، كتابة الكلام، سب تايتل، تعليق صوتي، صوت، دبلجة.
---
# Subtitles & voice

## Make subtitles
1. `transcribe` the video/audio (language "ar", "en" or "auto"). It writes `.srt` + `.txt` in the chat folder and returns the text.
2. To translate: `read_file` the .srt, translate ONLY the text lines (keep numbers and timestamps exactly), `write_file` a new `name.ar.srt` (or .en.srt).
3. To burn into the video: `video` operation=burn_subtitles with subtitles=<srt path>. Arabic renders right-to-left automatically with a font that supports Arabic.

## Voice-over
- `text_to_speech` with voice:
  - Arabic: ar-SA-HamedNeural (male), ar-SA-ZariyahNeural (female), ar-EG-ShakirNeural (Egyptian male)
  - English: en-US-AndrewNeural, en-US-AvaNeural, en-GB-RyanNeural
- rate "+10%" faster, "-10%" slower.
- Put the voice on a video: `video` operation=replace_audio (replace) or use ffmpeg `amix` to mix with existing music:
  `-i video.mp4 -i voice.mp3 -filter_complex "[0:a]volume=0.25[m];[m][1:a]amix=inputs=2:duration=first[a]" -map 0:v -map "[a]" -c:v copy out.mp4`

## Audio cleanup (ffmpeg)
- Remove hum/noise: `-af "highpass=f=80,lowpass=f=12000,afftdn=nf=-25"`
- Even loudness: `video` operation=normalize_audio (loudnorm).
