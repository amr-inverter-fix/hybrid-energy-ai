"""Hardware profiler for the LOCAL machine this script runs on.

Detects CPU, architecture, RAM, GPU, VRAM, OS, disk space and usable
acceleration backends, using only the Python standard library and
read-only system commands. It never sends anything anywhere.

Run directly to print a JSON profile:
    python -m local_ai.hardware
"""
import json
import os
import platform
import re
import shutil
import subprocess
import sys

TIMEOUT = 15


def _run(cmd):
    """Run a read-only system command; return stdout or '' on any failure."""
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT)
        return (out.stdout or "") + (out.stderr or "")
    except Exception:
        return ""


def _ps(script):
    """Run a PowerShell one-liner on Windows; return '' elsewhere/on failure."""
    if platform.system() != "Windows":
        return ""
    return _run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script])


def _ram_bytes():
    if platform.system() == "Windows":
        out = _ps("(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory")
        m = re.search(r"(\d{6,})", out)
        if m:
            return int(m.group(1))
    if platform.system() == "Darwin":
        out = _run(["sysctl", "-n", "hw.memsize"])
        if out.strip().isdigit():
            return int(out.strip())
    # Linux / other unix
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) * 1024
    except Exception:
        pass
    if hasattr(os, "sysconf"):
        try:
            return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
        except Exception:
            pass
    return 0


def _cpu_model():
    sysname = platform.system()
    if sysname == "Windows":
        out = _ps("(Get-CimInstance Win32_Processor).Name")
        line = out.strip().splitlines()
        if line and line[0].strip():
            return line[0].strip()
    if sysname == "Darwin":
        out = _run(["sysctl", "-n", "machdep.cpu.brand_string"]).strip()
        if out:
            return out
        out = _run(["sysctl", "-n", "hw.model"]).strip()
        if out:
            return out
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.lower().startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except Exception:
        pass
    return platform.processor() or "unknown"


def _gpus():
    """Return a list of {name, vram_mb}. Best effort; empty list if none found."""
    gpus = []
    sysname = platform.system()
    if sysname == "Windows":
        out = _ps("Get-CimInstance Win32_VideoController | "
                  "Select-Object Name,AdapterRAM | ConvertTo-Json -Compress")
        try:
            data = json.loads(out[out.index("{"):]) if "{" in out else (json.loads(out) if out.strip().startswith("[") else None)
            if isinstance(data, dict):
                data = [data]
            for g in data or []:
                name = str(g.get("Name", "")).strip()
                ram = g.get("AdapterRAM") or 0
                try:
                    ram = int(ram)
                except Exception:
                    ram = 0
                # AdapterRAM overflows above ~4 GB on some drivers; note it.
                if name:
                    gpus.append({"name": name, "vram_mb": max(0, ram // (1024 * 1024)),
                                 "note": "Windows-reported VRAM; may be understated above 4 GB" if ram >= 2**32 // 2 else ""})
        except Exception:
            pass
    if sysname == "Darwin":
        out = _run(["system_profiler", "SPDisplaysDataType"])
        for block in re.split(r"\n\s*\n", out):
            m = re.search(r"Chipset Model:\s*(.+)", block)
            if m:
                v = re.search(r"VRAM.*?:\s*(\d+)\s*MB", block)
                gpus.append({"name": m.group(1).strip(), "vram_mb": int(v.group(1)) if v else 0, "note": ""})
    # nvidia-smi works on Windows and Linux and is exact
    if shutil.which("nvidia-smi"):
        out = _run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"])
        exact = []
        for line in out.strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 2 and parts[1].isdigit():
                exact.append({"name": parts[0], "vram_mb": int(parts[1]), "note": "nvidia-smi"})
        if exact:
            return exact
    if sysname == "Linux" and not gpus:
        out = _run(["sh", "-c", "lspci 2>/dev/null | grep -iE 'vga|3d|display'"])
        for line in out.strip().splitlines():
            name = line.split(":", 2)[-1].strip()
            if name:
                gpus.append({"name": name, "vram_mb": 0, "note": "VRAM not detected without vendor driver tools"})
    return gpus


def _acceleration(gpus, cpu_model):
    acc = ["cpu"]
    names = " ".join(g["name"].lower() for g in gpus)
    if shutil.which("nvidia-smi") or "nvidia" in names:
        acc.append("cuda")
    if platform.system() == "Darwin" and ("apple" in cpu_model.lower() or platform.machine() in ("arm64",)):
        acc.append("metal")
    if "amd" in names and shutil.which("rocm-smi"):
        acc.append("rocm")
    return acc


def profile():
    """Full hardware profile of the machine this code runs on."""
    gpus = _gpus()
    cpu = _cpu_model()
    ram = _ram_bytes()
    disk = shutil.disk_usage(os.path.expanduser("~"))
    return {
        "os": platform.system(),
        "os_version": platform.version(),
        "os_release": platform.release(),
        "machine": platform.machine(),
        "cpu_model": cpu,
        "cpu_arch": platform.machine(),
        "cpu_cores_physical": os.cpu_count() or 1,
        "ram_bytes": ram,
        "ram_gb": round(ram / (1024 ** 3), 1),
        "gpus": gpus,
        "gpu_vram_mb_max": max([g["vram_mb"] for g in gpus], default=0),
        "acceleration_backends": _acceleration(gpus, cpu),
        "disk_free_gb": round(disk.free / (1024 ** 3), 1),
        "python": sys.version.split()[0],
        "ollama_installed": shutil.which("ollama") is not None or _ollama_windows(),
    }


def _ollama_windows():
    if platform.system() != "Windows":
        return False
    local = os.environ.get("LOCALAPPDATA", "")
    return bool(local) and os.path.exists(os.path.join(local, "Programs", "Ollama", "ollama.exe"))


if __name__ == "__main__":
    print(json.dumps(profile(), indent=2, ensure_ascii=False))
