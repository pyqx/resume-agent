# 🎯 Resume Agent

<h3 align="center">
  AI-powered resume analysis & interview preparation tool
</h3>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.11%2B-blue" alt="Python 3.11+"/>
  <img src="https://img.shields.io/badge/next.js-14-000?logo=next.js" alt="Next.js 14"/>
  <img src="https://img.shields.io/badge/license-MIT-green" alt="MIT License"/>
  <img src="https://img.shields.io/badge/status-beta-orange" alt="Status: Beta"/>
</p>

<div align="center">
  <a href="./README.md"><strong>🌐 中文文档</strong></a>
</div>

---

## Overview

**Resume Agent** is a local-first, full-stack AI resume assistant built around a single-agent reasoning loop (Plan → Act → Observe → Replan) that autonomously calls tools, evaluates results, and self-corrects. Designed for the Chinese job market with full Chinese resume parsing, JD matching, and interview preparation.

> Scope: a **single-user local tool**. The backend binds to 127.0.0.1 by default and has no multi-user auth — do not expose it to the public internet.

## Features

- **Resume parsing** — PDF (with two-column detection) / DOCX / Markdown; LLM structured extraction with three-level JSON repair and a rule-based fallback; per-field confidence; year-only dates flagged as approximate.
- **JD matching** — per-requirement LLM scoring with bounded concurrency (full / partial=0.5 / none / error), evidence + suggestions, tokenized keyword coverage, 22 hidden-signal rules (996, crunch-culture phrases, negation-aware), content-hash-keyed result caching.
- **Quality evaluation** — rule engine (weak verbs with capped deductions, sensitive info, dates, casing) running on real rendered text; five-dimension LLM judge with rubrics; ATS simulation; honest degradation when the LLM is unavailable (no fake scores).
- **GitHub analysis** — 5-stage progressive SSE pipeline (metadata → structure → dependencies/issues → personalized suggestions → STAR resume entry); token support, single clone reused across stages, credential isolation, secret-file exclusion, per-stage caching, explicit error events.
- **Interview prep** — targeted questions (JD-aware), 200/500-character self-intro scripts, weakness analysis with honest narratives; approximate dates never fabricate employment gaps.
- **Chat agent** — 33 registered tools with enforced preconditions and explicit confirmation for destructive actions; long-term memory (extract → dedupe → retrieve → consolidate); crash-recovery checkpoints; SSE reasoning stream.
- **Export** — Markdown / HTML (XSS-escaped) / PDF with built-in CJK fonts and width-measured line wrapping.
- **Web UI** — chat with a visible reasoning chain (plan → tool calls → results), stop button and session resume; JD match report with an explicit "could not evaluate" state and missing-keyword hints; interview prep with JD-targeted questions and one-click copy; a 5-stage GitHub analysis page; resume panel with inline entry editing, version snapshots/field-level diff, and export toolbar.

## Privacy & Security

- **Reversible PII masking**: phones/emails/IDs/salary/WeChat are replaced with placeholders **before** any LLM call and restored in responses (`SANITIZE_PII`); log handlers carry an irreversible PII filter.
- Local-first storage (SQLite WAL + embedded ChromaDB + diskcache); only LLM API calls leave the machine.
- SSRF guard on web fetching (private/loopback/metadata IPs blocked, per-hop redirect validation, 2MB body cap).
- Git clones run with credential helpers and prompts disabled; secret-bearing files are excluded from analysis.
- Untrusted content (resumes, JDs, GitHub data) is delimiter-wrapped with anti-injection instructions.
- Debug endpoints are off by default.

## Quick Start

```bash
# Backend
pip install -e ".[dev]"
cp .env.example .env        # fill in LLM_API_KEY etc.
uvicorn api.main:app --host 127.0.0.1 --port 8000

# Frontend
cd frontend && npm install && npm run dev
```

Frontend runs at **http://localhost:3000** (API proxied; override backend with `NEXT_PUBLIC_API_BASE`).

Key environment variables (full list in `.env.example`): `LLM_PROVIDER` (anthropic | openai_compatible), `LLM_API_KEY`, `LLM_MODEL`, `LLM_BASE_URL`, `SANITIZE_PII`, `GITHUB_TOKEN`, `DEBUG_ENDPOINTS`, `MAX_UPLOAD_SIZE_MB`.

## Development

```bash
pytest                    # backend tests
ruff check .              # lint
cd frontend && npm run lint && npm run typecheck
```

## License

MIT
