# DataIntelligence — AI-Powered Excel Platform

A production-ready, full-stack AI platform for Excel data cleaning, analytics, AI insights, and agent-driven data operations.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python Flask |
| AI / LLM | Groq API (llama3-70b-8192) |
| Database + Storage | Supabase (PostgreSQL + Storage) |
| Excel Processing | pandas, openpyxl, xlrd |
| Frontend | Vanilla JS + Chart.js (no framework dependency) |
| Deployment | Vercel |

---

## Quick Start

### 1. Clone & install

```bash
git clone <repo>
cd DATA-INTLLIGENCE-PLATFORM
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env and fill in GROQ_API_KEY, SUPABASE_URL, SUPABASE_KEY
```

### 3. Set up Supabase

1. Create a project at [supabase.com](https://supabase.com)
2. Open the **SQL Editor** and run the full contents of `supabase_schema.sql`
3. In **Storage**, create a bucket named `dataset-files` and set it to **Public**
4. Copy your project URL and anon/service-role key into `.env`

### 4. Run locally

```bash
python wsgi.py
```

Open [http://localhost:5000](http://localhost:5000)

---

## Deploy to Vercel

### One-time setup

```bash
npm i -g vercel
vercel login
```

### Deploy

```bash
vercel --prod
```

### Set environment variables on Vercel

```bash
vercel env add GROQ_API_KEY
vercel env add SUPABASE_URL
vercel env add SUPABASE_KEY
vercel env add SECRET_KEY
vercel env add FLASK_ENV   # set to: production
```

Or set them in the Vercel dashboard under **Project → Settings → Environment Variables**.

---

## Project Structure

```
DATA-INTLLIGENCE-PLATFORM/
├── app/
│   ├── __init__.py          # Flask app factory
│   ├── config.py            # Configuration classes
│   │
│   ├── routes/              # Flask Blueprints
│   │   ├── upload.py        # POST /api/upload/
│   │   ├── data.py          # GET  /api/data/preview/:id
│   │   ├── dashboard.py     # GET  /api/dashboard/:id
│   │   ├── agent.py         # POST /api/agent/run
│   │   ├── insights.py      # GET  /api/insights/:id
│   │   ├── reports.py       # GET  /api/reports/:id
│   │   ├── history.py       # GET  /api/history/:id
│   │   └── downloads.py     # GET  /api/downloads/excel|csv/:id
│   │
│   ├── agents/              # AI Agent (Brain + Hands)
│   │   ├── excel_agent.py   # Main orchestrator
│   │   ├── planner.py       # Thin wrapper
│   │   └── tools.py         # 15 validated data tools
│   │
│   ├── services/            # Core business logic
│   │   ├── excel_service.py     # Read, detect, preview, analyse
│   │   ├── cleaning_service.py  # Safe automatic cleaning
│   │   ├── groq_service.py      # Groq AI (brain + insights)
│   │   ├── supabase_service.py  # DB + file storage
│   │   ├── version_service.py   # Version lifecycle
│   │   ├── dashboard_service.py # Dynamic KPIs + charts
│   │   ├── insights_service.py  # Stats + AI explanations
│   │   └── export_service.py    # Excel/CSV downloads
│   │
│   ├── models/schemas.py    # Data model dataclasses
│   ├── utils/helpers.py     # Shared utilities
│   │
│   ├── templates/index.html # Single-page application shell
│   └── static/
│       ├── css/main.css     # Modern SaaS dark UI
│       └── js/app.js        # Frontend application logic
│
├── supabase_schema.sql      # Run this in Supabase SQL editor
├── wsgi.py                  # Entry point (Vercel + gunicorn)
├── vercel.json              # Vercel deployment config
├── requirements.txt         # Pinned Python dependencies
├── .env.example             # Environment variable template
└── .gitignore
```

---

## Complete User Workflow

```
Upload Excel
    ↓ Auto-detect workbook, sheets, columns, types
    ↓ Data quality analysis (duplicates, blanks, missing values)
    ↓ Safe automatic cleaning (ONLY real issues, never over-cleans)
    ↓ Save original + cleaned versions to Supabase
    ↓
Dashboard  →  AI Insights  →  Reports
    ↓
Download cleaned Excel / CSV
    ↓
AI Agent: natural-language commands
    ↓ Groq Brain understands intent
    ↓ Validated tool executes actual data operation
    ↓ New version created + saved to Supabase
    ↓ Dashboard / Insights / Reports updated
    ↓
Download agent-processed Excel / CSV
    ↓
Full version history — every version recoverable
```

---

## AI Agent — Available Tools

| Tool | Description |
|------|-------------|
| `remove_duplicates` | Remove exact duplicate rows (optionally by column subset) |
| `remove_blank_rows` | Remove completely empty rows |
| `find_missing_values` | Report missing values per column |
| `clean_column` | Trim, lowercase, uppercase, titlecase a column |
| `rename_column` | Rename a column |
| `standardize_values` | Standardise string casing in a column |
| `filter_data` | Filter rows by column condition (eq, contains, gt, lt…) |
| `sort_data` | Sort by column ascending or descending |
| `group_data` | Group by column with aggregation (sum, mean, count…) |
| `calculate_metric` | Compute total, mean, min, max on a numeric column |
| `create_summary` | Generate descriptive statistics summary |
| `generate_chart_data` | Prepare chart-ready data |
| `generate_insights` | Trigger AI insight regeneration |
| `export_excel` | Signal Excel download ready |
| `export_csv` | Signal CSV download ready |

---

## Cleaning Rules (Golden Rule)

The cleaning service **only** fixes issues that are:
1. Definitively detected
2. Safe to correct
3. Justified by actual data problems

It will **never**:
- Remove rows that aren't duplicates
- Fill in missing values with guesses
- Rename columns that aren't broken
- Change capitalisation without cause
- Normalise business-meaningful data

If data is already clean: **"Data is already clean. No changes were made."**

---

## Data Versioning

Every state of the data is preserved as a separate version:

| Version | Type | Description |
|---------|------|-------------|
| v1 | `original` | Original uploaded file — never modified |
| v2 | `auto_cleaned` | After safe automatic cleaning |
| v3+ | `agent_processed` | After each AI Agent command |

Each version stores: rows before/after, operation summary, Excel + CSV files in Supabase Storage, timestamps, and parent version reference.

---

## Security

- API keys (`GROQ_API_KEY`, `SUPABASE_KEY`) are server-side only — never in frontend code
- File uploads validated for type and size (max 50 MB)
- Filenames sanitized with `werkzeug.utils.secure_filename`
- No arbitrary code execution — agent uses only the 15 validated tools
- All Supabase queries use the official Python SDK (parameterized)

---

## Environment Variables Reference

| Variable | Required | Description |
|----------|----------|-------------|
| `GROQ_API_KEY` | Yes | Groq API key from console.groq.com |
| `SUPABASE_URL` | Yes | Your Supabase project URL |
| `SUPABASE_KEY` | Yes | Supabase anon or service-role key |
| `SECRET_KEY` | Yes | Flask session secret (random string) |
| `FLASK_ENV` | No | `development` or `production` |
| `GROQ_MODEL` | No | Override Groq model (default: llama3-70b-8192) |
| `TMP_DIR` | No | Temp directory (default: `/tmp`) |
