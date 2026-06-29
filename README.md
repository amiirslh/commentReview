# FlyToday Comment Review API

A Persian comment moderation service that detects offensive and inappropriate text.
It combines a **hard-coded phrase blocklist**, **PII detection**, a **trained SVM model**,
and an optional **Claude AI stage** to flag content before it is published.

---

## How It Works

Every text goes through a five-stage pipeline. The first stage that triggers stops evaluation.

```
Input text
    │
    ▼
Stage 1 — Hard-block list (Persian + English + transliterations)
    │  config/Hard_code_phrases.json  (Redis-cached)
    │  Bypass-resistant: "ک ی ر" and "k i r" both collapse to "kir" before matching
    │
    ▼
Stage 2 — PII / spam detection  (language-agnostic)
    │  phone_number  →  not_ok   (Iranian mobile: 09XXXXXXXXX / +989X… / Persian digits)
    │  national_id   →  suspicious  (valid 10-digit کد ملی, checksum-verified)
    │  email_address →  suspicious
    │  url           →  suspicious  (http/https/ftp/www links)
    │  bank_card     →  suspicious  (16-digit card, Luhn-validated)
    │  iban          →  suspicious  (IR + 24 digits)
    │
    ▼
Stage 3a — English profanity  (runs when language = english / mixed)
    │  better_profanity library — comprehensive English offensive word list
    │  Checks full sentence AND individual tokens
    │
    ▼
Stage 3b — Persian ML model  (runs when language = persian / mixed)
    │  SVM classifier, character TF-IDF, trained on 8 818 labelled samples
    │  confidence ≥ 0.85  →  not_ok  (returned immediately, AI skipped)
    │  confidence ≥ 0.50  →  suspicious  (falls through to AI)
    │
    ▼
Stage 4 — Claude AI model  (runs when ANTHROPIC_API_KEY is set)
    │  Claude Opus 4.8 — deep contextual understanding of Persian & English
    │  Catches rude tone, indirect insults, and culturally-specific offences
    │  that pattern-matching and ML models miss
    │  result: not_ok / suspicious / ok
    │
    ▼
Stage 5 — Clean  →  ok
```

**Language auto-detection** counts Persian Unicode characters (U+0600–U+06FF) vs
Latin characters. Ratio ≥ 65 % Persian → `persian`; ≤ 25 % → `english`; in between → `mixed`.
Mixed text runs both Stage 3a and 3b.

The model trains automatically on **first startup** (~3 min) and is stored in a
Docker volume — restarts and code updates do not retrigger training.

---

## Prerequisites

| Tool | Minimum version |
|------|----------------|
| Docker | 20.10 |
| Docker Compose | v2 (the `docker compose` command, not `docker-compose`) |

---

## Quick Start

```bash
# 1. Clone the repo
git clone <repo-url>
cd commentReview

# 2. (Optional) customise settings — see Environment Variables section
cp .env.example .env

# 3. Build and start
docker compose up -d

# 4. Watch the logs — first run trains the model (~3 minutes)
docker compose logs -f web
```

When you see `Starting server on 0.0.0.0:8000...` the API is ready.

---

## Daily Commands

```bash
# Start in background
docker compose up -d

# Stop (keeps data volumes)
docker compose down

# View live logs
docker compose logs -f

# View only the app logs
docker compose logs -f web

# Restart the app (e.g. after editing config/Hard_code_phrases.json)
docker compose restart web

# Rebuild after a code change, then restart
docker compose up -d --build
```

---

## API Reference

### POST `/api/check-text/`

Checks a piece of text for offensive or suspicious content.
Supports **Persian**, **English**, and **mixed-language** input.

**Request**

```
POST http://localhost:8000/api/check-text/
Content-Type: application/json

{ "text": "your text here" }
```

---

**Response fields**

| Field | Type | Description |
|-------|------|-------------|
| `result` | string | `ok` / `not_ok` / `suspicious` (see below) |
| `confidence` | float | 0.0–1.0 — how certain the model is |
| `language` | string | `persian` / `english` / `mixed` / `unknown` |
| `reason` | string\|null | Why it was blocked: `hard_block` / `phone_number` / `national_id` / `email_address` / `url` / `bank_card` / `iban` / `english_profanity` / `ml_model` / `ai_model` |
| `matched_text` | string\|null | The specific word/phrase that triggered detection |
| `normalized_tokens` | array | Tokens after bypass-collapse (e.g. `ک ی ر` → `کیر`) |
| `ai_explanation` | string\|null | Short English explanation from the AI stage (null when AI did not trigger) |

**`result` values**

| Value | Meaning | Action |
|-------|---------|--------|
| `ok` | Clean text | Publish |
| `not_ok` | Clearly offensive/rude | Reject |
| `suspicious` | Borderline — model leans offensive but not confident | Review manually |

---

**Example — clean Persian**

```bash
curl -X POST http://localhost:8000/api/check-text/ \
  -H "Content-Type: application/json" \
  -d '{"text": "سلام دوست عزیز، امیدوارم روز خوبی داشته باشی"}'
```
```json
{
  "text": "سلام دوست عزیز، امیدوارم روز خوبی داشته باشی",
  "result": "ok",
  "confidence": 0.0,
  "language": "persian",
  "matched_text": null,
  "reason": null,
  "normalized_tokens": ["سلام", "دوست", "عزیز", "امیدوارم", "روز", "خوبی", "داشته", "باشی"]
}
```

**Example — hard-block (Persian explicit phrase)**

```bash
curl -X POST http://localhost:8000/api/check-text/ \
  -H "Content-Type: application/json" \
  -d '{"text": "این آدم کش است"}'
```
```json
{
  "text": "این آدم کش است",
  "result": "not_ok",
  "confidence": 1.0,
  "language": "persian",
  "matched_text": "کش",
  "reason": "hard_block",
  "normalized_tokens": ["این", "آدم", "کش", "است"]
}
```

**Example — bypass attempt (spaced letters)**

```bash
curl -X POST http://localhost:8000/api/check-text/ \
  -H "Content-Type: application/json" \
  -d '{"text": "ک ر توی دهنت"}'
```
```json
{
  "result": "not_ok",
  "reason": "hard_block",
  "matched_text": "کر",
  "language": "persian"
}
```
The system collapses `ک ر` → `کر` before matching, so spacing tricks don't work.

**Example — English profanity**

```bash
curl -X POST http://localhost:8000/api/check-text/ \
  -H "Content-Type: application/json" \
  -d '{"text": "you stupid asshole"}'
```
```json
{
  "result": "not_ok",
  "confidence": 1.0,
  "language": "english",
  "matched_text": "you stupid asshole",
  "reason": "english_profanity"
}
```

**Example — mixed Persian + English**

```bash
curl -X POST http://localhost:8000/api/check-text/ \
  -H "Content-Type: application/json" \
  -d '{"text": "این یه shit مزخرفه"}'
```
```json
{
  "result": "not_ok",
  "language": "persian",
  "matched_text": "shit",
  "reason": "hard_block"
}
```

**Example — mobile phone number (rejected)**

```bash
curl -X POST http://localhost:8000/api/check-text/ \
  -H "Content-Type: application/json" \
  -d '{"text": "برای خرید با ۰۹۱۲ ۳۴۵ ۶۷۸۹ تماس بگیرید"}'
```
```json
{
  "text": "برای خرید با ۰۹۱۲ ۳۴۵ ۶۷۸۹ تماس بگیرید",
  "result": "not_ok",
  "confidence": 1.0,
  "language": "persian",
  "matched_text": "09123456789",
  "reason": "phone_number",
  "normalized_tokens": ["برای", "خرید", "با", "09123456789", "تماس", "بگیرید"],
  "ai_explanation": null
}
```
Detected as spam/advertisement. Works with Persian digits, `+98` format, and spaced digits.

**Example — Iranian national code (suspicious)**

```bash
curl -X POST http://localhost:8000/api/check-text/ \
  -H "Content-Type: application/json" \
  -d '{"text": "کد ملی من ۰۰۱۲۳۴۵۶۷۸ است"}'
```
```json
{
  "text": "کد ملی من ۰۰۱۲۳۴۵۶۷۸ است",
  "result": "suspicious",
  "confidence": 1.0,
  "language": "persian",
  "matched_text": "0012345678",
  "reason": "national_id",
  "normalized_tokens": [...],
  "ai_explanation": null
}
```

**Example — suspicious URL (spam link)**

```json
{
  "result": "suspicious",
  "confidence": 1.0,
  "matched_text": "https://suspicious-site.ir/discount",
  "reason": "url",
  "ai_explanation": null
}
```

**Example — suspicious (borderline)**

```json
{
  "result": "suspicious",
  "confidence": 0.62,
  "language": "persian",
  "matched_text": "...",
  "reason": "ml_model",
  "ai_explanation": null
}
```
Confidence is between 0.50 and 0.85 — the model leans offensive but isn't certain.
Recommended action: queue for manual review.

**Example — caught by AI (contextually rude, no explicit swear words)**

```bash
curl -X POST http://localhost:8000/api/check-text/ \
  -H "Content-Type: application/json" \
  -d '{"text": "برو گم شو، به تو ربطی نداره"}'
```
```json
{
  "text": "برو گم شو، به تو ربطی نداره",
  "result": "not_ok",
  "confidence": 0.95,
  "language": "persian",
  "matched_text": null,
  "reason": "ai_model",
  "normalized_tokens": ["برو", "گم", "شو", "به", "تو", "ربطی", "نداره"],
  "ai_explanation": "dismissive rude phrase telling someone to get lost"
}
```
No explicit swear word — the hard-block list and SVM would pass this, but the AI stage
understands context and tone.

---

## Environment Variables

Copy `.env.example` to `.env` and edit before deploying to production.

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | insecure dev key | Django secret key — **must change in production** |
| `DEBUG` | `False` | Set `True` only for local development |
| `ALLOWED_HOSTS` | `*` | Comma-separated hostnames. Use `*` in dev, real hostnames in prod |
| `PORT` | `8000` | Host port the API listens on |
| `REDIS_HOST` | `redis` | Redis hostname (no need to change in Docker) |
| `REDIS_PORT` | `6379` | Redis port |
| `ANTHROPIC_API_KEY` | *(empty)* | Anthropic API key — enables Stage 3 AI check. Leave blank to skip |
| `AI_MODEL` | `claude-opus-4-8` | Claude model for AI moderation. Use `claude-haiku-4-5` for lower cost |

---

## Maintenance

### Update the blocklist

Edit `config/Hard_code_phrases.json`, then restart the app:

```bash
docker compose restart web
```

The file is read from disk on every cold start; Redis cache is cleared automatically.

### Retrain the model from scratch

```bash
# Delete the saved model from the volume, then restart
docker compose exec web rm -f swear_persian/models/model.pkl
docker compose restart web
# Training starts automatically and takes ~3 minutes
docker compose logs -f web
```

### Open a shell inside the container

```bash
docker compose exec web sh
```

### Run Django management commands

```bash
docker compose exec web python manage.py shell
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
```

### Check Redis cache

```bash
# List all cached keys
docker compose exec redis redis-cli keys '*'

# Clear the hard-code phrase cache (forces file reload on next request)
docker compose exec redis redis-cli del hard_code_phrases
```

### View resource usage

```bash
docker stats comment_review_api comment_review_redis
```

---

## Project Structure

```
commentReview/
├── api/
│   ├── views.py              # Core logic: pipeline orchestration
│   ├── pii_checker.py        # Stage 2: PII / spam detection (phone, national ID, …)
│   ├── ai_checker.py         # Stage 4: Claude AI integration
│   └── urls.py               # Route: POST /api/check-text/
├── config/
│   └── Hard_code_phrases.json  # Explicit blocklist (edit to update)
├── swear_persian/
│   ├── swear_detector.py     # PersianSwearDetector (train / predict)
│   ├── dataset/
│   │   └── dataset.json      # 8 818 labelled training samples
│   └── models/               # model.pkl lives here (Docker volume)
├── FlyTodayCommentReview/
│   ├── settings.py           # Django config (reads from env vars)
│   └── urls.py               # Root URL config
├── Dockerfile
├── docker-compose.yml
├── entrypoint.sh             # Wait for Redis → train → migrate → serve
├── requirements.txt
└── .env.example              # Template for environment variables
```

---

## Troubleshooting

**API returns `"Model not loaded"` after start**
The model is still training. Watch the logs: `docker compose logs -f web`.
Training takes roughly 3 minutes on the first run.

**Port 8000 is already in use**
Change the port in `.env`:
```
PORT=8080
```
Then restart: `docker compose up -d`.

**Redis connection errors in logs**
The app falls back to reading the blocklist from disk, so it still works.
Check that the redis container is healthy:
```bash
docker compose ps
```

**Need to start completely fresh**
```bash
docker compose down -v   # removes containers AND volumes (deletes saved model + redis data)
docker compose up -d
```
