"""Resource monitor: GPU (nvidia-smi), RAM and CPU."""
import shutil
import subprocess
import sys
import threading
import time

_cache = {"t": 0.0, "v": None}
_cpu_prev = {"idle": 0, "total": 0}
_lock = threading.Lock()


def _ram():
    if sys.platform == "win32":
        import ctypes

        class MS(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        m = MS()
        m.dwLength = ctypes.sizeof(MS)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
        return round((m.ullTotalPhys - m.ullAvailPhys) / 2**30, 1), round(m.ullTotalPhys / 2**30, 1)
    try:
        with open("/proc/meminfo") as f:
            info = dict(line.split(":", 1) for line in f)
        tot = int(info["MemTotal"].split()[0]) / 2**20
        av = int(info["MemAvailable"].split()[0]) / 2**20
        return round(tot - av, 1), round(tot, 1)
    except Exception:
        return None, None


def _cpu():
    """CPU % since the previous call."""
    try:
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes
            idle, kern, user = wintypes.FILETIME(), wintypes.FILETIME(), wintypes.FILETIME()
            ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kern), ctypes.byref(user))
            f = lambda t: (t.dwHighDateTime << 32) | t.dwLowDateTime  # noqa: E731
            i, total = f(idle), f(kern) + f(user)          # kernel time includes idle
        else:
            with open("/proc/stat") as fh:
                vals = [int(x) for x in fh.readline().split()[1:]]
            i, total = vals[3] + vals[4], sum(vals)
        di, dt = i - _cpu_prev["idle"], total - _cpu_prev["total"]
        _cpu_prev.update(idle=i, total=total)
        if dt <= 0:
            return None
        return max(0, min(100, round(100 * (1 - di / dt))))
    except Exception:
        return None


def _gpu():
    if not shutil.which("nvidia-smi"):
        return None
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.used,memory.total,utilization.gpu,temperature.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
            creationflags=0x08000000 if sys.platform == "win32" else 0)
        name, used, total, util, temp = [x.strip() for x in r.stdout.strip().splitlines()[0].split(",")]
        return {"name": name, "vram_used": round(int(used) / 1024, 1), "vram_total": round(int(total) / 1024, 1),
                "util": int(util), "temp": int(temp)}
    except Exception:
        return None


def get():
    with _lock:
        if time.time() - _cache["t"] < 1.5 and _cache["v"]:
            return _cache["v"]
        ru, rt = _ram()
        v = {"ram_used": ru, "ram_total": rt, "cpu": _cpu(), "gpu": _gpu()}
        _cache.update(t=time.time(), v=v)
        return v
