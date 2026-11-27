"""Local model catalog and hardware-based recommendation.

Only open-weight models that permit local use under their own licenses.
Sizes are the Ollama Q4_K_M download sizes; RAM figures are a practical
minimum for comfortable CPU inference (model + context + OS headroom).

Arabic quality matters for this project: among compact open models the
Qwen2.5 family has the strongest Arabic/English bilingual performance,
so it is the default at every tier where it fits.
"""

# tier: 1 = lightweight, 2 = recommended default, 3 = stronger (optional)
CATALOG = [
    {
        "id": "qwen2.5:0.5b", "family": "Qwen", "params_b": 0.5,
        "download_mb": 400, "min_ram_gb": 2.0, "min_vram_gb": 0, "tier": 1,
        "license": "Apache 2.0", "license_url": "https://www.apache.org/licenses/LICENSE-2.0",
        "arabic": "basic", "ctx": 32768,
        "note": "Smallest usable assistant. Fast on any CPU; short answers.",
    },
    {
        "id": "qwen2.5:1.5b", "family": "Qwen", "params_b": 1.5,
        "download_mb": 1000, "min_ram_gb": 4.0, "min_vram_gb": 0, "tier": 1,
        "license": "Apache 2.0", "license_url": "https://www.apache.org/licenses/LICENSE-2.0",
        "arabic": "good for its size", "ctx": 32768,
        "note": "Lightweight tier default when 4 GB+ RAM is free.",
    },
    {
        "id": "llama3.2:3b", "family": "Llama", "params_b": 3.0,
        "download_mb": 2000, "min_ram_gb": 6.0, "min_vram_gb": 0, "tier": 2,
        "license": "Llama 3.2 Community License", "license_url": "https://www.llama.com/llama3_2/license/",
        "arabic": "limited", "ctx": 131072,
        "note": "Strong English reasoning; weaker Arabic than Qwen at this size.",
    },
    {
        "id": "gemma2:2b", "family": "Gemma", "params_b": 2.0,
        "download_mb": 1600, "min_ram_gb": 6.0, "min_vram_gb": 0, "tier": 1,
        "license": "Gemma Terms of Use", "license_url": "https://ai.google.dev/gemma/terms",
        "arabic": "limited", "ctx": 8192,
        "note": "Alternative lightweight option, English-focused.",
    },
    {
        "id": "qwen2.5:3b", "family": "Qwen", "params_b": 3.0,
        "download_mb": 1900, "min_ram_gb": 6.0, "min_vram_gb": 0, "tier": 2,
        "license": "Apache 2.0 (3B research variant: Qwen Research license)", "license_url": "https://huggingface.co/Qwen/Qwen2.5-3B-Instruct",
        "arabic": "good", "ctx": 32768,
        "note": "Recommended default: best Arabic/English balance that runs on a normal laptop.",
    },
    {
        "id": "qwen2.5:7b", "family": "Qwen", "params_b": 7.0,
        "download_mb": 4700, "min_ram_gb": 12.0, "min_vram_gb": 6, "tier": 3,
        "license": "Apache 2.0", "license_url": "https://www.apache.org/licenses/LICENSE-2.0",
        "arabic": "very good", "ctx": 32768,
        "note": "Stronger tier. Needs 16 GB RAM or a 6+ GB GPU to feel responsive.",
    },
    {
        "id": "llama3.1:8b", "family": "Llama", "params_b": 8.0,
        "download_mb": 4900, "min_ram_gb": 12.0, "min_vram_gb": 6, "tier": 3,
        "license": "Llama 3.1 Community License", "license_url": "https://www.llama.com/llama3_1/license/",
        "arabic": "limited", "ctx": 131072,
        "note": "Stronger English alternative for capable hardware.",
    },
]

EMBED_MODEL = {
    "id": "nomic-embed-text", "download_mb": 274, "min_ram_gb": 1.0,
    "license": "Apache 2.0", "license_url": "https://www.apache.org/licenses/LICENSE-2.0",
    "note": "Local embedding model for semantic search. English-optimized; "
            "Arabic retrieval is backed up by the built-in lexical (BM25) index, which needs no download.",
}

DEFAULT_TIER_ORDER = [3, 2, 1]


def _fits(m, ram_gb, vram_mb):
    if ram_gb and m["min_ram_gb"] > ram_gb:
        return False
    if m["min_vram_gb"] and vram_mb < m["min_vram_gb"] * 1024 and ram_gb < m["min_ram_gb"] + 4:
        return False
    return True


def recommend(profile):
    """Pick lightweight / recommended / stronger options from a hardware profile.

    Returns dict with the three slots (None when nothing fits), the chosen
    default, and human-readable reasons. Never recommends a model that does
    not fit; prefers the largest model that fits comfortably.
    """
    ram = profile.get("ram_gb", 0)
    vram = profile.get("gpu_vram_mb_max", 0)
    disk = profile.get("disk_free_gb", 0)
    slots = {"lightweight": None, "recommended": None, "stronger": None}
    reasons = []

    def best(tier):
        cands = [m for m in CATALOG if m["tier"] == tier and _fits(m, ram, vram)]
        # prefer Qwen (Arabic) then smaller download
        cands.sort(key=lambda m: (0 if m["family"] == "Qwen" else 1, m["download_mb"]))
        return cands[0] if cands else None

    slots["lightweight"] = best(1)
    slots["recommended"] = best(2) or slots["lightweight"]
    slots["stronger"] = best(3)

    default = slots["recommended"]
    if ram and ram < 2:
        reasons.append("Less than 2 GB RAM detected: no local LLM will run comfortably; "
                       "the dashboard and retrieval still work without it.")
        default = None
    elif default is None:
        reasons.append("No catalog model fits the detected RAM; consider closing other apps or adding RAM.")
    if default and disk < default["download_mb"] / 1024 + EMBED_MODEL["download_mb"] / 1024 + 2:
        reasons.append("Low disk space: free at least %.1f GB before downloading the model."
                       % (default["download_mb"] / 1024 + EMBED_MODEL["download_mb"] / 1024 + 2))
    if slots["stronger"] is None and ram >= 12:
        reasons.append("A 7-8B model would fit if a GPU with 6+ GB VRAM is usable; CPU-only 7B is slow.")
    if not vram:
        reasons.append("No usable GPU VRAM detected: inference will run on CPU (slower but fully offline).")
    return {
        "lightweight": slots["lightweight"],
        "recommended": slots["recommended"],
        "stronger": slots["stronger"],
        "default": default,
        "embed_model": EMBED_MODEL,
        "reasons": reasons,
        "catalog_note": "All listed models are open-weight and downloadable once for offline use; "
                        "each remains under its own license (see license_url).",
    }


def by_id(model_id):
    for m in CATALOG:
        if m["id"] == model_id:
            return m
    return None
