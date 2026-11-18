"""Runs inside the optional extras venv (Python 3.12). Prints one JSON line with the result.

  transcribe <media> <out_dir> [language|auto] [model]
  rmbg <image> <out_png>
  tts <text_file> <voice> <out_mp3> [rate]
"""
import asyncio
import glob
import json
import os
import sys
import time


def _cuda_dlls():
    """Expose pip-installed CUDA libraries (nvidia-cublas / nvidia-cudnn) to ctranslate2 on Windows."""
    if sys.platform != "win32":
        return
    for base in sys.path:
        for b in glob.glob(os.path.join(base, "nvidia", "*", "bin")):
            try:
                os.add_dll_directory(b)
                os.environ["PATH"] = b + os.pathsep + os.environ.get("PATH", "")
            except Exception:
                pass


def _ts(t):
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h):02}:{int(m):02}:{int(s):02},{int(round((s - int(s)) * 1000)):03}"


def transcribe(src, out_dir, language="auto", model_name="large-v3-turbo"):
    _cuda_dlls()
    from faster_whisper import WhisperModel
    lang = None if language in ("", "auto", None) else language
    t0 = time.time()
    model, device = None, "cuda"
    try:
        model = WhisperModel(model_name, device="cuda", compute_type="float16")
    except Exception:
        device = "cpu"
        model = WhisperModel(model_name, device="cpu", compute_type="int8")
    try:
        segments, info = model.transcribe(src, language=lang, vad_filter=True, beam_size=5)
        segments = list(segments)
    except Exception:
        if device == "cpu":
            raise
        device = "cpu"          # CUDA libs present but broken -> CPU
        model = WhisperModel(model_name, device="cpu", compute_type="int8")
        segments, info = model.transcribe(src, language=lang, vad_filter=True, beam_size=5)
        segments = list(segments)
    base = os.path.join(out_dir, os.path.splitext(os.path.basename(src))[0])
    with open(base + ".srt", "w", encoding="utf-8") as f:
        for i, s in enumerate(segments, 1):
            f.write(f"{i}\n{_ts(s.start)} --> {_ts(s.end)}\n{s.text.strip()}\n\n")
    text = "\n".join(s.text.strip() for s in segments)
    with open(base + ".txt", "w", encoding="utf-8") as f:
        f.write(text)
    return {"srt": base + ".srt", "txt": base + ".txt", "language": info.language,
            "duration": round(info.duration, 1), "device": device, "seconds": round(time.time() - t0, 1),
            "text": text[:6000]}


def rmbg(src, out):
    from PIL import Image
    from rembg import new_session, remove
    try:
        session = new_session("isnet-general-use")
    except Exception:
        session = new_session("u2net")
    img = Image.open(src).convert("RGBA")
    remove(img, session=session).save(out)
    return {"out": out}


def tts(text_file, voice, out, rate="+0%"):
    import edge_tts
    with open(text_file, encoding="utf-8") as f:
        text = f.read()

    async def go():
        await edge_tts.Communicate(text, voice, rate=rate).save(out)

    asyncio.run(go())
    return {"out": out}


def main():
    cmd, args = sys.argv[1], sys.argv[2:]
    try:
        fn = {"transcribe": transcribe, "rmbg": rmbg, "tts": tts}[cmd]
        res = {"ok": True, **fn(*args)}
    except Exception as e:
        res = {"ok": False, "error": f"{type(e).__name__}: {e}"}
    sys.stdout.write(json.dumps(res) + "\n")      # ASCII-safe regardless of console code page


if __name__ == "__main__":
    main()
