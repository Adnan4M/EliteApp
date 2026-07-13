# Elite AI Study Assistant

Search a whole curriculum instantly: type a word, get every page it appears on,
opened one page at a time with the term highlighted — even though **97% of the
curriculum is scanned images with no text layer**.

Two clients share one core:

- **Telegram bot** (`bot.py`) — works today.
- **Prep-year mobile app** — a **Flutter** client on a **FastAPI backend**
  (`backend/`). The backend reuses the bot's OCR index, search, and highlight
  renderer, and adds email/password auth, per-semester activation codes,
  progress, and ranking. The app shows **server-rendered highlighted page
  images**, so it ships no PDFs.

## How it actually works

The four textbooks (`chem/hist/phys/bbio.pdf`) are image scans; only `bio.pdf`
has a real text layer. So:

1. **Indexing** (`indexer.py`) renders each page at 300 DPI and runs **Tesseract
   OCR** (Arabic model) to recover text *and per-word bounding boxes*. Pages with
   a native text layer skip OCR. Output: one JSONL file per subject in `indexes/`.
2. **Search** (`services/search_engine.py`) matches a normalized query against the
   indexed words. Arabic normalization folds hamza/harakat/alef variants, so
   `بلمره` matches the printed `البلمرة`.
3. **Display** (`services/pdf_engine.py`) renders *only the matching page* from the
   original PDF and draws highlight boxes from the stored OCR coordinates. The
   student always sees the pristine scan; OCR text is only the search index.

## Setup

```bash
# 1. Install Tesseract + Arabic model (one time)
winget install UB-Mannheim.TesseractOCR
#    then place tessdata_best 'ara.traineddata' in ./tessdata/ (with configs/)

# 2. Python deps
python -m venv venv && venv\Scripts\pip install -r requirements.txt

# 3. Secrets — copy and fill in
copy .env.example .env      # set BOT_TOKEN (get a fresh one from @BotFather)

# 4. Build the search index (OCR — minutes for the full corpus)
python indexer.py                 # all books; skips unchanged ones
python indexer.py --subject الكيمياء --limit 20   # quick smoke test

# 5. Run
python bot.py
```

## Configuration (`.env`)

| Key | Purpose |
|-----|---------|
| `BOT_TOKEN` | Telegram bot token (**never commit**) |
| `AI_PROVIDER` / `GEMINI_API_KEY` | Summary/Explanation/Questions (not yet wired) |
| `ADMIN_IDS` | Comma-separated Telegram IDs for admin commands |
| `DATABASE_URL` | `sqlite:///elite.db` in dev; PostgreSQL in prod |
| `TESSERACT_CMD` / `TESSDATA_PREFIX` | OCR binary + language data |

## Layout

```
bot.py               entry point: logging, DB init, handler registration
config.py            env-backed Settings (validated once)
database.py          engine, session_scope(), in-place column migration
indexer.py           OCR + text-layer indexing -> indexes/*.jsonl
curriculum.yaml      grade/subject -> PDF + OCR language map
services/
  ocr_engine.py      Tesseract wrapper -> text + word boxes
  pdf_engine.py      render pages, draw highlights (PyMuPDF + Pillow)
  search_engine.py   keyword search + optional FAISS semantic rerank
  search_session.py  short-lived store bridging the 64-byte callback limit
  user_service.py    registration, trial/subscription access checks
handlers/
  start.py           /start
  text_router.py     THE single text handler (menu, grade, search input)
  search_flow.py     inline-button flow: 4 options, page nav, highlights
models/              SQLAlchemy: user, progress, subscription, daily_word
```

## Running the app backend

```bash
uvicorn backend.main:app --reload --port 8000
# interactive API docs at http://localhost:8000/docs
```

Key endpoints (all JWT-protected except register/login):

| Method + path | Purpose |
|---|---|
| `POST /auth/register`, `POST /auth/login` | email/password → JWT; register starts a 7-day first-semester trial |
| `GET /me?semester=first` | profile: 5 subjects, progress %, rank, lock state |
| `POST /progress` | update a chapter's percentage |
| `GET /search/suggest?semester=&q=` | autocomplete from indexed words |
| `POST /search?semester=&keyword=` | ranked page locations + extractive summary |
| `GET /search/page?query_id=&position=` | **highlighted page as a PNG** |
| `POST /search/summary?semester=&keyword=` | AI summary (extractive fallback if no key) |
| `POST /search/explanation?semester=&keyword=` | AI: simple → advanced → real-life → related |
| `POST /search/questions?semester=&keyword=&count=&refresh=` | AI: N shuffled MCQs, one correct each (`refresh=true` bypasses cache) |
| `POST /codes/redeem` | unlock a semester with a single-use code |
| `POST /admin/codes` (`X-Admin-Key`) | issue activation codes |
| `POST /admin/subjects/{sem}/{subject}/pdf` (`X-Admin-Key`) | upload a PDF; OCR-indexes it in the background |
| `GET /admin/subjects/{sem}/{subject}/pdf` (`X-Admin-Key`) | indexing status (`indexing`/`ready`/`error`, page counts) |

**Uploading curriculum:** `POST` a `.pdf` (multipart `file`, optional `ocr_lang`
form field) for a subject. The server detects whether the PDF has a text layer,
saves it under `uploads/`, and OCR-indexes it in a background thread; poll the
`GET` status endpoint until `ready`, after which students can search it. This is
how second-semester content (and any curriculum change) gets added — no redeploy.

Access is gated per semester: the free trial covers **first** semester only;
**second** stays locked (subject list shows `locked: true`, search returns `402`)
until a code is redeemed.

## Status

**Shared core:** ✅ OCR indexing, Arabic-tolerant search, page render + highlight.

**Bot:** ✅ registration (6 grades), 7-day trial with **access enforcement** (locked
after expiry), search → highlighted page + nav, AI summary/explanation/quiz-polls,
**progress tracking** (subjects → chapters → mark done), **daily word + 72h reminders**
(APScheduler), **admin commands** (`/stats /users /broadcast /activatesub /deactivatesub`).
⏳ weekly report; Settings screen.

**App backend:** ✅ auth, per-semester trial + code gating, search + suggest,
server-rendered highlighted page images, progress, ranking, admin codes,
notifications, support, admin PDF upload → background OCR index → searchable,
**modular AI (summary / explanation / MCQs), curriculum-grounded**, admin overview
(subject/book status, code listing, stats, manual grant/revoke), AI model fallback +
"daily limit reached" handling. ⏳ second-semester curriculum; rate limiting.

**AI:** provider-agnostic (`services/ai/`); Gemini implemented. Set `GEMINI_API_KEY`
(+ optional `GEMINI_MODEL`, default `gemini-flash-latest`) in `.env` to enable. Without
a key, summary falls back to an extractive baseline and explanation/questions return
`503`. Every generation is grounded in the actual indexed page text.

Results are **cached to disk** (`cache/ai/`) by `(feature, scope, keyword)`: a cold
Gemini call is ~15 s, a cache hit is instant and free. The bot renders questions as
**native Telegram quiz polls** (self-grading). The questions cache is a **growing
pool** — "Generate More" / `refresh=true` generates new questions (the model is told
which already exist), appends them, and never overwrites the original set.

Set `GEMINI_MODEL_FALLBACK` to a second model to survive the free tier's per-model
daily quota: on a `429`/`404` the provider skips straight to the fallback (each model
has its own quota bucket), retrying only genuinely transient errors on the primary.

**App (Flutter client):** ✅ scaffolded in `../app` (17 files: auth, 4-tab shell,
search → highlighted-page carousel, summary/explanation/quiz, code redemption).
⏳ not yet compiled — needs the Flutter SDK installed (`flutter create .` +
`flutter analyze`). See `../app/README.md`.

## Known follow-ups

- `curriculum.yaml` parks every book under البكالوريا; assign real grades.
- The old bot token was committed in plaintext — **revoke it in @BotFather.**
- `bio.pdf` is an English Cambridge combined-science book, not Arabic biology.
