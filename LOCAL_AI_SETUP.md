# Local AI Setup — خطوة واحدة / one command

Runs the private engineering assistant on YOUR laptop. No account, no
subscription, no API keys, no internet needed after the one-time download.

## English

### Windows (recommended path)

1. Get this repository onto your laptop:
   `git clone https://github.com/amr-inverter-fix/hybrid-energy-ai`
   (or Code → Download ZIP and extract it).
2. Double-click **`SETUP_WINDOWS.bat`**. It will:
   - install Python if missing (via winget),
   - install Ollama (the local model runtime) if missing,
   - install the small Python components (FastAPI, uvicorn, scikit-learn),
   - profile your hardware (CPU, RAM, GPU, disk),
   - recommend and download the right model once (~0.4-2 GB),
   - verify the model actually answers before finishing.
3. Any time afterwards: double-click **`START_LOCAL_AI.bat`**. It starts the
   local AI and opens the dashboard's **Local AI** page.

### macOS / Linux

```
cd hybrid-energy-ai
bash setup_mac_linux.sh     # once
./start_local_ai.sh         # every time you want the local AI
```

### What you need

- Any normal laptop: 4 GB free RAM and 4 GB free disk are enough for the
  recommended model; 2 GB RAM works with the lightweight model.
- Internet only for the one-time download. After that everything is offline.
- A GPU is NOT required (CPU inference). With a 6+ GB VRAM GPU the setup
  offers a stronger model.

### Using it

- Open the dashboard → **Local AI**: chat in Arabic or English, see your
  hardware and the recommended model, index project documents, add your own
  documents (manuals, notes) to the knowledge base.
- **Learning Center**: see accepted/rejected records, train candidate models,
  promote or roll back. These actions ask for the training token in
  `local_ai_data/training_token` (a file on your computer; open it with
  Notepad and paste it once per browser tab).
- The whole dashboard keeps working if the local AI is off.

### Offline use

After setup, disconnect from the internet and everything still works: the
model, retrieval over the knowledge base, the learning pipeline, and the
dashboard itself (open `app.html` locally or keep using the hosted page; it
only needs the internet for the page itself and for optional weather).

### Uninstall

Delete the repo folder and run `ollama rm <model>` (or uninstall Ollama).
Nothing else was installed system-wide except Python packages with `--user`.

---

## بالعربي

### ويندوز

1. حمّل المشروع على اللابتوب (Code → Download ZIP وفك الضغط، أو git clone).
2. دوس دبل-كليك على **SETUP_WINDOWS.bat** مرة واحدة. هيعمل كل حاجة:
   يثبّت بايثون وOllama لو مش موجودين، يفحص جهازك (معالج، رام، كارت شاشة،
   مساحة)، يختار أنسب نموذج، يحمّله مرة واحدة، ويتأكد إنه شغال.
3. بعد كده في أي وقت: دبل-كليك على **START_LOCAL_AI.bat** — بيفتح اللوحة على
   صفحة **Local AI** (الذكاء المحلي).

### هتحتاج إيه

- لابتوب عادي: ٤ جيجا رام فاضية و٤ جيجا مساحة تكفي للنموذج المقترح، ولو الجهاز
  أضعف في نموذج أخف.
- إنترنت مرة واحدة بس وقت التحميل. بعدها كله يشتغل **بدون نت**.
- مش محتاج كارت شاشة.

### الاستخدام

- صفحة **الذكاء المحلي**: اسأل بالعربي أو الإنجليزي، والإجابات بتتولد على
  جهازك وبتذكر مصادرها من ملفات المشروع. تقدر تضيف مستنداتك (كتالوجات، ملاحظات).
- صفحة **التعلم المستمر**: تشوف البيانات المقبولة والمرفوضة، تدرب نموذج جديد،
  توافق على الترقية أو ترجع لإصدار قديم. هتطلب منك التوكن الموجود في ملف
  `local_ai_data/training_token` على جهازك.
- لو الذكاء المحلي مقفول، اللوحة تفضل شغالة عادي.

### الخصوصية

مفيش حسابات، مفيش اشتراكات، مفيش أي بيانات بتخرج من جهازك. النموذج بيشتغل
محليًا ١٠٠٪.
