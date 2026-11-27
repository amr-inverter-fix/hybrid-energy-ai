"""Setup assistant: profile THIS computer, recommend a model, download it once
through the local Ollama runtime, verify it answers offline, and save config.

Called by SETUP_WINDOWS.bat / setup_mac_linux.sh, but can also be run directly:
    python -m local_ai.setup_assistant            # full guided setup
    python -m local_ai.setup_assistant --profile  # only print the hardware profile
"""
import json
import os
import shutil
import subprocess
import sys
import time

from .hardware import profile
from .model_catalog import recommend, EMBED_MODEL
from .server import CONFIG_PATH, DATA_DIR, load_config, save_config, OLLAMA


def say(msg, ar=""):
    print(msg)
    if ar:
        print(ar)


def run(cmd, timeout=3600):
    print("  > " + " ".join(cmd))
    return subprocess.run(cmd, timeout=timeout).returncode == 0


def ollama_cmd():
    if shutil.which("ollama"):
        return "ollama"
    local = os.environ.get("LOCALAPPDATA", "")
    win = os.path.join(local, "Programs", "Ollama", "ollama.exe")
    if os.path.exists(win):
        return win
    return None


def wait_ollama(seconds=30):
    import urllib.request
    for _ in range(seconds):
        try:
            urllib.request.urlopen(OLLAMA + "/api/tags", timeout=2)
            return True
        except Exception:
            time.sleep(1)
    return False


def main():
    if "--profile" in sys.argv:
        print(json.dumps(profile(), indent=2, ensure_ascii=False))
        return 0

    say("== Hybrid Energy AI - local AI setup ==",
        "== إعداد الذكاء الاصطناعي المحلي ==")

    say("\n[1/5] Reading your computer's hardware...",
        "\n[١/٥] فحص مواصفات الجهاز...")
    p = profile()
    rec = recommend(p)
    print(json.dumps({"cpu": p["cpu_model"], "ram_gb": p["ram_gb"],
                      "gpus": [g["name"] for g in p["gpus"]],
                      "disk_free_gb": p["disk_free_gb"],
                      "backends": p["acceleration_backends"]}, indent=2, ensure_ascii=False))
    for r in rec["reasons"]:
        print("  note: " + r)

    default = rec["default"]
    if not default:
        say("\nNo local model fits this hardware. The dashboard and its built-in "
            "answers still work; you can re-run this setup after freeing RAM.",
            "\nالجهاز لا يسمح بتشغيل نموذج محلي. اللوحة ستعمل بدونه.")
        return 2
    say("\nRecommended model for this computer: %s (%s, ~%d MB download once)"
        % (default["id"], default["license"], default["download_mb"]),
        "\nالنموذج المقترح: %s (تحميل مرة واحدة ثم يعمل بدون إنترنت)" % default["id"])
    if rec["lightweight"]:
        print("  lighter option:  " + rec["lightweight"]["id"])
    if rec["stronger"]:
        print("  stronger option: " + rec["stronger"]["id"] +
              "  (change HYBRID_CHAT_MODEL later if you want it)")

    say("\n[2/5] Checking the local model runtime (Ollama)...",
        "\n[٢/٥] التحقق من مشغّل النماذج المحلي...")
    oc = ollama_cmd()
    if not oc:
        say("Ollama is not installed. Install it first (the setup script normally "
            "does this step): https://ollama.com/download - then run this again.",
            "برنامج Ollama غير مثبت. ثبّته ثم أعد تشغيل الإعداد.")
        return 3
    subprocess.Popen([oc, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not wait_ollama():
        say("The Ollama service did not start. Open the Ollama app once, then retry.",
            "خدمة Ollama لم تبدأ. افتح برنامج Ollama مرة ثم أعد المحاولة.")
        return 4

    say("\n[3/5] Downloading the model (once; afterwards everything works offline)...",
        "\n[٣/٥] تحميل النموذج (مرة واحدة فقط)...")
    if not run([oc, "pull", default["id"]]):
        say("Model download failed. Check your internet connection and retry; "
            "partial downloads resume.", "فشل تحميل النموذج. تحقق من الإنترنت وأعد المحاولة.")
        return 5
    embed_ok = run([oc, "pull", EMBED_MODEL["id"]])
    if not embed_ok:
        print("  (embedding model skipped; lexical search still works offline)")

    say("\n[4/5] Verifying the model answers...",
        "\n[٤/٥] التأكد من أن النموذج يعمل...")
    import urllib.request
    body = json.dumps({"model": default["id"],
                       "prompt": "In one short sentence: what does a hybrid wind-solar "
                                 "system with a battery do?",
                       "stream": False,
                       "options": {"num_predict": 80}}).encode()
    req = urllib.request.Request(OLLAMA + "/api/generate", data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            j = json.loads(r.read().decode())
        print("  model said: " + j.get("response", "").strip()[:200])
    except Exception as e:
        say("Verification inference failed: %s" % e, "فشل اختبار النموذج.")
        return 6

    say("\n[5/5] Saving configuration...",
        "\n[٥/٥] حفظ الإعدادات...")
    cfg = load_config()
    cfg["chat_model"] = os.environ.get("HYBRID_CHAT_MODEL", default["id"])
    cfg["embed_model"] = EMBED_MODEL["id"] if embed_ok else None
    save_config(cfg)

    say("\nDone. Start the local AI with START_LOCAL_AI.bat (Windows) or "
        "./start_local_ai.sh (Mac/Linux), then open the dashboard and go to "
        "'Local AI'. No internet, account or subscription is needed from now on.",
        "\nتم. شغّل START_LOCAL_AI ثم افتح اللوحة وادخل صفحة Local AI. "
        "لا حاجة لإنترنت أو حساب من الآن.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
