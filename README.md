# 🎯 Resume Agent — 简历助手

<h3 align="center">
  AI-powered career narrative advisor · 智能简历深度优化引擎
</h3>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.11%2B-blue" alt="Python 3.11+"/>
  <img src="https://img.shields.io/badge/next.js-14-000?logo=next.js" alt="Next.js 14"/>
  <img src="https://img.shields.io/badge/license-MIT-green" alt="MIT License"/>
  <img src="https://img.shields.io/badge/status-beta-orange" alt="Status: Beta"/>
</p>

---

## 📖 Overview

**Resume Agent** is a full-stack, AI-driven resume assistant built around a **single-Agent deep-reasoning loop** (Plan → Act → Observe → Replan). Rather than wrapping an LLM behind a simple chat interface, it employs an autonomous agent that plans multi-step tasks, calls tools, evaluates results, and adapts — enabling nuanced career narrative coaching that goes far beyond template filling.

Designed specifically for the **Chinese job market**, it supports Chinese-language resumes, JD parsing, and interview preparation in Chinese.

### What makes it different

| Approach | Typical App | Resume Agent |
|----------|-------------|--------------|
| Reasoning | Single LLM call, no iteration | Plan → Act → Observe → Replan loop with self-correction |
| Memory | Stateless or short context | mem0-style persistent memory (ChromaDB + SQLite) |
| Tool use | None or fixed pipeline | Dynamic tool selection based on context |
| Fault tolerance | None | 4-layer resilience (retry → degrade → checkpoint → human handoff) |
| Privacy | Sends full data to LLM | Privacy sanitization middleware masks PII before LLM calls |

---

## ✨ Features

### 1. 📄 Smart Resume Parsing & Management
- Upload **PDF, DOCX, or Markdown** resumes
- Multi-strategy parsing (pymupdf for PDF, python-docx for DOCX, OCR fallback)
- Structured output with confidence scoring per field
- **Copy-on-Write versioning** — fork versions from master; only diffs consume storage
- WYSIWYG editor with inline editing and version diff viewer

### 2. 🎯 JD Matching & Analysis
- Paste a job description → get structured extraction of requirements, responsibilities, and hidden signals
- **Two-stage matching**: vector recall (cost-efficient) → LLM rerank (precise)
- Per-requirement match score with detailed reasoning
- Hidden signal detection (red flags, culture indicators, urgency cues)
- Keyword extraction for resume tailoring

### 3. 🧠 Content Deep Optimization
- STAR completeness analysis for each experience entry
- Weak verb detection and replacement suggestions
- Quantitative density scoring
- **Rule + LLM dual evaluation** — 80% of issues caught by local rules (milliseconds), 20% need LLM judgment (seconds)
- ATS compatibility simulation

### 4. 🎨 Format & Export
- Multiple templates (professional, modern, minimal, ATS-optimized)
- Export to **Markdown, HTML, or PDF**
- ATS-friendly output validation

### 5. 💻 GitHub Project Analysis
- Submit a GitHub repository URL → progressive 5-stage analysis:
  1. Directory structure understanding
  2. Dependency analysis
  3. Issue/PR pattern analysis
  4. Development direction suggestions
  5. **STAR resume entry generation** from real project contributions
- SSE streaming — results appear incrementally as each stage completes

### 6. 🗣 Interview Preparation
- **Question generation** — 4 categories: technical, behavioral, project experience, HR-focused
- **Self-introduction script** — tailored to resume + target role
- **Weakness analysis** — detect resume gaps and generate narrative strategies

### 7. 🔄 Intelligent Chat Agent
- Conversational interface with full agent reasoning visible
- SSE streaming for real-time responses
- Session history management
- Context-aware tool invocation (resume CRUD, JD matching, web search, quality evaluation)

---

## 🏗 Architecture

```
┌──────────────────────────────────────────────────────┐
│                    Frontend (Next.js 14)               │
│  ┌──────────┐  ┌──────────┐  ┌───────────────────┐   │
│  │ Chat UI  │  │ JD Match │  │ Interview Prep    │   │
│  │ (SSE)    │  │ Page     │  │ Page              │   │
│  └────┬─────┘  └────┬─────┘  └───────┬───────────┘   │
│       │              │                │               │
│       └──────────────┴────────────────┘               │
│                       │  API Client (/lib/api.ts)      │
└───────────────────────┼──────────────────────────────┘
                        │ HTTP / SSE
┌───────────────────────┼──────────────────────────────┐
│            Backend (FastAPI, Python 3.11+)             │
│  ┌──────────────────────────────────────────────────┐ │
│  │              API Layer (api/routes/)              │ │
│  │  /chat  /resume  /jd  /export  /github  /interview│ │
│  └──────────────────────┬───────────────────────────┘ │
│                         │                              │
│  ┌──────────────────────┴───────────────────────────┐ │
│  │              Agent Core (agent/)                   │ │
│  │  ┌──────────┐  ┌──────────┐  ┌────────────────┐  │ │
│  │  │ Planner  │  │  Loop    │  │  Context        │  │ │
│  │  │ (2-level)│  │(P→A→O→R) │  │  Assembler      │  │ │
│  │  └──────────┘  └────┬─────┘  └────────┬───────┘  │ │
│  │                     │                  │           │ │
│  │  ┌──────────────────┴──────────────────┴────────┐ │ │
│  │  │           Tool System (agent/tools/)          │ │ │
│  │  │  Resume │ JD │ GitHub │ Interview │ Web │ ...│ │ │
│  │  └─────────────────────────┬────────────────────┘ │ │
│  │                            │                        │ │
│  │  ┌─────────────────────────┴────────────────────┐ │ │
│  │  │         Memory System (agent/memory/)          │ │ │
│  │  │  ChromaDB (vectors)  +  SQLite (metadata)     │ │ │
│  │  └─────────────────────────┬────────────────────┘ │ │
│  │                            │                        │ │
│  │  ┌─────────────────────────┴────────────────────┐ │ │
│  │  │         Core Logic (core/)                    │ │ │
│  │  │  Resume│JD│Interview│GitHub│Evaluation│Cache │ │ │
│  │  └─────────────────────────────────────────────┘ │ │
│  └──────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────┘
```

### Agent Loop Detail

```
                    ┌─────────┐
                    │  START  │
                    └────┬────┘
                         ▼
              ┌─────────────────────┐
         ┌───│ PLAN: What to do?    │
         │   │ (respond / ask /     │
         │   │  call tools)         │
         │   └──────────┬──────────┘
         │              ▼
         │   ┌─────────────────────┐
         │   │ ACT: Execute tools   │◄──── Exponential
         │   │ (parallel, retry)    │      backoff retry
         │   └──────────┬──────────┘
         │              ▼
         │   ┌─────────────────────┐
         │   │ OBSERVE: Evaluate   │
         │   │ (success / partial  │
         │   │  / failure)         │
         │   └──────────┬──────────┘
         │              │
         │    ┌─────────┴──────────┐
         │    ▼                    ▼
         │ Needs more      Task complete
         │ action?         or need user?
         │    │                    │
         └────┘                    ▼
                           ┌─────────────┐
                           │ END / OUTPUT │
                           └─────────────┘
```

---

## 🛠 Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Framework** | FastAPI + Uvicorn | Async Python backend with SSE streaming |
| **Agent** | Custom LangGraph-style loop | Plan→Act→Observe→Replan orchestration |
| **LLM** | Anthropic Claude / OpenAI-compatible | Unified client supporting both providers |
| **Vector DB** | ChromaDB (embedded) | Semantic memory and JD/resume retrieval |
| **Database** | SQLite (WAL mode) | Metadata, sessions, checkpoint persistence |
| **Cache** | diskcache | LLM response caching (cost reduction) |
| **Documents** | PyMuPDF, python-docx | Resume parsing from PDF, DOCX, Markdown |
| **Frontend** | Next.js 14 + React 18 + Tailwind CSS | Modern SSR/CSR hybrid UI |
| **Streaming** | Server-Sent Events (SSE) | Real-time agent response streaming |

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.11+**
- **Node.js 18+** (for frontend)
- **Poetry** or **pip** (Python package manager)

### Backend Setup

```bash
# 1. Clone the repository
git clone <repo-url> && cd resume-agent

# 2. Create a virtual environment
python -m venv .venr
source .venv/bin/activate  # Linux/Mac
# or: .venv\Scripts\activate  # Windows

# 3. Install Python dependencies
pip install -e ".[dev]"

# 4. Configure environment
cp .env.example .env
# Edit .env — set your LLM provider and API key

# 5. Initialize the database
python -c "from core.database import init_db; import asyncio; asyncio.run(init_db())"

# 6. Start the backend server
uvicorn api.main:app --reload --host 127.0.0.1 --port 8000
```

### Frontend Setup

```bash
# 1. Navigate to frontend
cd frontend

# 2. Install dependencies
npm install

# 3. Start development server
npm run dev
```

The frontend runs at **http://localhost:3000** and proxies API requests to **http://localhost:8000** via Next.js rewrites.

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROVIDER` | `openai_compatible` | `anthropic` or `openai_compatible` |
| `LLM_API_KEY` | — | Your LLM API key |
| `LLM_MODEL` | `deepseek-v4-flash` | Model identifier |
| `LLM_BASE_URL` | `https://api.deepseek.com` | API base URL (OpenAI-compatible) |
| `LLM_TEMPERATURE` | `0.7` | LLM generation temperature |
| `LLM_MAX_TOKENS` | `4096` | Max tokens per response |
| `HOST` | `127.0.0.1` | Backend bind address |
| `PORT` | `8000` | Backend port |
| `CORS_ORIGINS` | `["http://localhost:3000"]` | Allowed CORS origins |

---

## 📁 Project Structure

```
resume-agent/
├── agent/                  # Agent core (the "brain")
│   ├── loop.py             # Main P→A→O→R loop (state machine)
│   ├── planner.py          # Strategic + Tactical two-level planner
│   ├── context.py          # Context assembler (system + memory + state)
│   ├── checkpoint.py       # Fault-tolerant checkpoint save/load
│   ├── memory/             # mem0-style memory system
│   │   ├── extractor.py    # LLM-based fact extraction
│   │   ├── consolidator.py # Merge, dedup, conflict detection
│   │   ├── retriever.py    # Semantic search + type filtering
│   │   ├── store.py        # ChromaDB + SQLite dual-write
│   │   └── models.py       # Memory data models
│   └── tools/              # Agent tool system
│       ├── registry.py     # Tool registry (register, filter, execute)
│       ├── resume_tools.py # Resume CRUD + version tools
│       ├── jd_tools.py     # JD matching tools
│       ├── interview_tools.py
│       ├── github_tools.py # GitHub analysis tools (5 stages)
│       ├── web_tools.py    # Web search/fetch tools
│       ├── memory_tools.py # Memory read/write tools
│       ├── quality_tools.py
│       └── base.py         # BaseTool, ToolMetadata, ToolResult
├── api/                    # FastAPI backend
│   ├── main.py             # App entry, middleware, route registration
│   ├── deps.py             # Dependency injection (wires object graph)
│   ├── session_manager.py  # Conversation session persistence
│   ├── middleware/
│   │   ├── cors.py
│   │   ├── logging.py      # JSON structured logging
│   │   └── sanitizer.py    # Privacy sanitization middleware
│   └── routes/
│       ├── chat.py         # SSE streaming + non-streaming chat
│       ├── resume.py       # Resume CRUD + upload + debug-parse
│       ├── jd.py           # JD parse, match, signals, keywords
│       ├── export.py       # PDF/Markdown/HTML export + templates
│       ├── github.py       # GitHub progressive analysis (SSE)
│       ├── interview.py    # Questions, self-intro, weakness analysis
│       └── sessions.py     # Session history CRUD
├── core/                   # Business logic (agent-agnostic)
│   ├── config.py           # pydantic-settings (reads .env)
│   ├── database.py         # SQLite WAL-mode init + schema
│   ├── llm.py              # Unified LLM client
│   ├── cache.py            # diskcache init/get
│   ├── vector_store.py     # ChromaDB embedded init
│   ├── logging_setup.py    # Rotating file + console logger
│   ├── resume/             # Resume parsing, schema, versioning, export
│   ├── jd/                 # JD parsing, matching, signal detection
│   ├── interview/          # Question/intro/weakness generation
│   ├── github/             # GitHub analysis orchestrator
│   └── evaluation/         # ATS simulation, LLM judge, rules, scorer
├── frontend/               # Next.js 14 App Router
│   ├── app/
│   │   ├── page.tsx        # Main chat page
│   │   ├── match/page.tsx  # JD matching page
│   │   └── interview/page.tsx  # Interview prep page
│   ├── components/
│   │   ├── chat/           # ChatPanel, MessageBubble, ReasoningChain
│   │   ├── resume/         # ResumeEditor, DiffViewer, SectionCard
│   │   ├── match/          # MatchReport (score ring, detail cards)
│   │   └── layout/         # Sidebar (navigation + session history)
│   ├── contexts/           # ResumeContext, PageStateContext
│   ├── hooks/              # useSSE, useResume
│   └── lib/api.ts          # Typed API client
├── prompts/                # YAML prompt templates (versioned)
│   ├── agent/              # System, planner, memory extractor prompts
│   ├── interview/          # Question, intro prompts
│   ├── github/             # Suggestion, resume entry prompts
│   └── evaluation/         # LLM judge scoring guidelines
├── data/                   # Runtime data (gitignored)
│   ├── chroma/             # ChromaDB persistent storage
│   ├── cache/              # diskcache storage
│   ├── logs/               # Application logs
│   └── uploads/            # Uploaded resume files
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/           # Sample resumes, JDs
├── .env                    # Environment configuration
├── pyproject.toml          # Python project config + dependencies
├── ResumeAgent-PRD.md      # Product Requirements Document
└── ResumeAgent-Architecture.md  # Architecture Design Document
```

---

## 🔐 Privacy & Security

Resume Agent was designed with **privacy by default**:

- **Privacy sanitization middleware** — sensitive information (phone numbers, email addresses, social IDs) is masked **before** any data reaches the LLM, with re-identification mapping applied to responses
- **Local-first storage** — SQLite and embedded ChromaDB mean no external database dependencies and full data control
- **No external vector DB** — ChromaDB runs embedded, no data leaves your machine except LLM API calls
- **Configurable LLM provider** — use Anthropic Claude with explicit data usage policies, or run through a local/compatible endpoint

---

## 🧪 Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=agent --cov=core --cov=api

# Run specific test categories
pytest tests/unit/
pytest tests/integration/
```

---

## 🧰 Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run backend in development mode
uvicorn api.main:app --reload --host 127.0.0.1 --port 8000

# Run frontend in development mode
cd frontend && npm run dev

# Lint
ruff check .               # Python
cd frontend && npm run lint # TypeScript
```

---

## 🗺 Roadmap

- [x] Resume parsing (PDF/DOCX/MD)
- [x] JD structured parsing & matching
- [x] Agent chat with reasoning loop
- [x] GitHub project analysis
- [x] Interview preparation tools
- [x] Multiple export formats (Markdown/HTML/PDF)
- [x] Version management with diff viewing
- [ ] Post-submission application tracking
- [ ] Multi-language resume support
- [ ] Batch JD analysis & comparison
- [ ] Resume score & improvement suggestions dashboard

---

## 📚 Design Documents

- **[Product Requirements Document](./ResumeAgent-PRD.md)** — Full feature specification and user stories
- **[Architecture Design Document](./ResumeAgent-Architecture.md)** — Detailed technical architecture, data flow, and design decisions

---

## 📄 License

This project is licensed under the **MIT License**. See `LICENSE` for details.

---

<p align="center">
  Built with ❤️ for job seekers navigating the Chinese tech market
</p>
