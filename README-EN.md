# 🎯 Resume Agent

<h3 align="center">
  AI-powered resume analysis, JD matching, and interview preparation tool
</h3>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.11%2B-blue" alt="Python 3.11+"/>
  <img src="https://img.shields.io/badge/next.js-14-000?logo=next.js" alt="Next.js 14"/>
  <img src="https://img.shields.io/badge/license-MIT-green" alt="MIT License"/>
  <img src="https://img.shields.io/badge/status-beta-orange" alt="Status: Beta"/>
</p>

---

<div align="center">
  <a href="./README.md"><strong>🇨🇳 中文文档</strong></a>
</div>

---

## 📖 Overview

**Resume Agent** is a full-stack AI assistant for job seekers, built around a **single-Agent deep-reasoning loop** (Plan → Act → Observe → Replan). Instead of a simple LLM chat wrapper, it uses an autonomous agent that plans multi-step tasks, calls tools, evaluates results, and self-corrects.

Designed for the **Chinese job market**, with full support for Chinese-language resumes, JD parsing, and interview preparation.

---

## ✨ Features

### 1. 📄 Resume Parsing & Management
- Upload **PDF, DOCX, or Markdown** resumes
- Multi-strategy parsing: PyMuPDF (PDF), python-docx (DOCX), plain text (MD)
- LLM-driven structured extraction with per-field confidence scoring
- Resume list management (load, switch, delete)
- Debug parse endpoint for step-by-step extraction tracing

### 2. 🎯 JD Matching & Analysis
- Paste a job description → structured extraction of requirements, nice-to-haves, and keyword frequency
- **Two-stage matching**: vector recall (low cost) → LLM rerank (high precision)
- Per-requirement match levels (full / partial / none) with evidence and suggestions
- **Hidden signal detection**: risky phrases, culture clues, urgency indicators
- Visual match report: score ring, requirement details, signal interpretation cards

### 3. 🧠 Content Optimization (via Agent Chat)
- STAR completeness analysis
- Weak verb detection and replacement suggestions
- Quantitative density recommendations
- **Rule + LLM dual evaluation** — local rules catch 80% of issues in milliseconds, LLM handles deeper semantics
- ATS compatibility simulation

### 4. 💻 GitHub Project Analysis
- Submit a GitHub repo URL → **5-stage progressive SSE analysis**:
  1. Repository metadata
  2. Directory structure analysis
  3. Dependency & Issue/PR deep analysis
  4. Development direction suggestions (LLM-generated)
  5. Ready → on-demand **STAR-format resume entry** generation
- Real-time SSE streaming, results appear incrementally per stage

### 5. 🗣 Interview Preparation
- **Question generation** — 4 categories: STAR deep-dives, technical follow-ups, behavioral, pressure tests, plus company-specific tips
- **Self-introduction scripts** — tailored to resume + target role (short 60s / long 180s)
- **Weakness analysis** — identify resume gaps with risk ratings and narrative strategies (including sample responses)
- Export results as **Markdown or PDF**

### 6. 🔄 Intelligent Chat Agent
- LangGraph-style **Plan→Act→Observe→Replan** reasoning loop
- SSE streaming with step-by-step reasoning display
- Tool invocation: resume CRUD, JD matching, web search, quality evaluation
- Session history management (save / load / auto-resume)

### 7. 📤 Export
- Export resumes as **Markdown, HTML, or PDF**
- Export interview content (questions, scripts, weakness analysis) as Markdown / PDF
- PDF generation uses PyMuPDF's built-in CJK font, no external font dependencies

---

## 🏗 Architecture

```
┌──────────────────────────────────────────────────────┐
│                  Frontend (Next.js 14)                 │
│  ┌──────────┐  ┌──────────┐  ┌───────────────────┐   │
│  │ Chat     │  │ JD Match │  │ Interview Prep    │   │
│  │ (SSE)    │  │ Page     │  │ Page              │   │
│  └────┬─────┘  └────┬─────┘  └───────┬───────────┘   │
│       │              │                │               │
│       └──────────────┴────────────────┘               │
│                       │  API Client (/lib/api.ts)      │
└───────────────────────┼──────────────────────────────┘
                        │ HTTP / SSE
┌───────────────────────┼──────────────────────────────┐
│             Backend (FastAPI, Python 3.11+)            │
│  ┌──────────────────────────────────────────────────┐ │
│  │              API Layer (api/routes/)               │ │
│  │  /chat  /resume  /jd  /export  /github  /interview│ │
│  └──────────────────────┬───────────────────────────┘ │
│                         │                              │
│  ┌──────────────────────┴───────────────────────────┐ │
│  │              Agent Core (agent/)                   │ │
│  │  ┌──────────┐  ┌──────────┐  ┌────────────────┐  │ │
│  │  │ Planner  │  │  Loop    │  │  Context       │  │ │
│  │  │ (2-level)│  │(P→A→O→R) │  │  Assembler     │  │ │
│  │  └──────────┘  └────┬─────┘  └────────┬───────┘  │ │
│  │                     │                  │           │ │
│  │  ┌──────────────────┴──────────────────┴────────┐ │ │
│  │  │           Tool System (agent/tools/)          │ │ │
│  │  │  Resume│JD│GitHub│Interview│Web│Quality      │ │ │
│  │  └──────────────────────┬───────────────────────┘ │ │
│  │                         │                          │ │
│  │  ┌──────────────────────┴───────────────────────┐ │ │
│  │  │         Memory System (agent/memory/)         │ │ │
│  │  │  ChromaDB (vectors) + SQLite (metadata)      │ │ │
│  │  └──────────────────────┬───────────────────────┘ │ │
│  │                         │                          │ │
│  │  ┌──────────────────────┴───────────────────────┐ │ │
│  │  │         Core Logic (core/)                    │ │ │
│  │  │  Resume│JD│Interview│GitHub│Eval│Cache       │ │ │
│  │  └──────────────────────────────────────────────┘ │ │
│  └──────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────┘
```

---

## 🛠 Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Framework** | FastAPI + Uvicorn | Async Python backend with SSE streaming |
| **Agent** | Custom LangGraph-style loop | Plan→Act→Observe→Replan orchestration |
| **LLM** | Anthropic Claude / OpenAI-compatible | Unified client, multi-provider support |
| **Vector DB** | ChromaDB (embedded) | Semantic memory and resume/JD retrieval |
| **Database** | SQLite (WAL mode) | Metadata, sessions, checkpoint persistence |
| **Cache** | diskcache | LLM response caching |
| **Documents** | PyMuPDF, python-docx | Resume text extraction from PDF, DOCX |
| **Frontend** | Next.js 14 + React 18 + Tailwind CSS | Modern SSR/CSR hybrid UI |
| **Streaming** | Server-Sent Events (SSE) | Real-time agent responses and multi-stage analysis |

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.11+**
- **Node.js 18+**

### Backend Setup

```bash
# 1. Clone
git clone https://github.com/pyqx/resume-agent.git && cd resume-agent

# 2. Create virtual environment
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/Mac:
# source .venv/bin/activate

# 3. Install dependencies
pip install -e ".[dev]"

# 4. Configure .env with your LLM provider and API key

# 5. Initialize database
python -c "from core.database import init_db; import asyncio; asyncio.run(init_db())"

# 6. Start backend
uvicorn api.main:app --reload --host 127.0.0.1 --port 8000
```

### Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Frontend at **http://localhost:3000**, API proxied to **http://localhost:8000**.

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROVIDER` | `openai_compatible` | `anthropic` or `openai_compatible` |
| `LLM_API_KEY` | — | Your LLM API key |
| `LLM_MODEL` | `deepseek-v4-flash` | Model identifier |
| `LLM_BASE_URL` | `https://api.deepseek.com` | API base URL (OpenAI-compatible) |
| `HOST` | `127.0.0.1` | Backend bind address |
| `PORT` | `8000` | Backend port |

---

## 📁 Project Structure

```
resume-agent/
├── agent/                    # Agent core (the "brain")
│   ├── loop.py               # P→A→O→R loop (state machine)
│   ├── planner.py            # Two-level planner
│   ├── context.py            # Context assembler
│   ├── checkpoint.py         # Fault-tolerant checkpointing
│   ├── memory/               # ChromaDB + SQLite memory system
│   └── tools/                # Tool system (resume, JD, GitHub, interview, web, quality)
├── api/                      # FastAPI backend
│   ├── main.py               # Entry point, middleware, routes
│   ├── deps.py               # DI wiring
│   ├── session_manager.py    # Session persistence
│   ├── middleware/            # CORS / logging / privacy sanitizer
│   └── routes/               # chat, resume, jd, export, github, interview, sessions
├── core/                     # Business logic
│   ├── config.py             # pydantic-settings
│   ├── database.py           # SQLite init
│   ├── llm.py                # Unified LLM client
│   ├── cache.py              # diskcache
│   ├── vector_store.py       # ChromaDB
│   ├── resume/               # Parser, schema, exporter
│   ├── jd/                   # Parser, matcher, signal detector
│   ├── interview/            # Question/intro/weakness generation
│   ├── github/               # Progressive analysis orchestrator
│   └── evaluation/           # ATS sim, rules engine, scorer
├── frontend/                 # Next.js 14
│   ├── app/                  # Chat / JD Match / Interview Prep pages
│   ├── components/           # Chat, Resume, Match report, Layout components
│   ├── contexts/             # React context providers
│   ├── hooks/                # useSSE, useResume
│   └── lib/api.ts            # Typed API client
├── prompts/                  # Versioned YAML prompt templates
├── data/                     # Runtime data (gitignored)
├── tests/
├── .env                      # Config (gitignored)
├── pyproject.toml
├── README.md                 # Chinese docs
└── README-EN.md              # English docs (this file)
```

---

## 🔐 Privacy & Security

- **Privacy sanitization middleware** — phone numbers, emails, and social IDs are masked **before** being sent to the LLM, with re-identification mapping applied to responses
- **Local-first storage** — SQLite + embedded ChromaDB, full data control
- **No external service dependencies** — no external database or vector DB service required; only LLM API calls leave your machine
- **Configurable LLM provider** — use Anthropic Claude or any OpenAI-compatible endpoint

---

## 🧪 Testing

```bash
pytest
pytest --cov=agent --cov=core --cov=api
pytest tests/unit/
pytest tests/integration/
```

---

## 🧰 Development

```bash
pip install -e ".[dev]"
uvicorn api.main:app --reload --host 127.0.0.1 --port 8000   # backend
cd frontend && npm run dev                                      # frontend
ruff check .                                                     # lint
```

---

## 📄 License

MIT License

---

<p align="center">Built for job seekers navigating the Chinese tech market ❤️</p>
