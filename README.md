# 🎯 Resume Agent — 简历助手

<h3 align="center">
  AI 驱动的智能简历分析与面试准备工具
</h3>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.11%2B-blue" alt="Python 3.11+"/>
  <img src="https://img.shields.io/badge/next.js-14-000?logo=next.js" alt="Next.js 14"/>
  <img src="https://img.shields.io/badge/license-MIT-green" alt="MIT License"/>
  <img src="https://img.shields.io/badge/status-beta-orange" alt="Status: Beta"/>
</p>

---

<div align="center">
  <a href="./README-EN.md"><strong>🌐 English README</strong></a>
</div>

---

## 📖 项目简介

**Resume Agent** 是一个全栈 AI 简历助手，核心采用**单 Agent 深度推理循环**（规划 → 执行 → 观察 → 再规划），能够自主调用工具、评估结果并自我修正。专为**中文求职市场**设计，完整支持中文简历解析、JD 匹配和面试准备。

核心能力：上传简历后，可以针对目标岗位进行匹配分析、挖掘简历短板、生成面试题目和自我介绍，并支持将分析结果导出为 Markdown 或 PDF。

---

## ✨ 功能特性

### 1. 📄 简历解析与管理
- 上传 **PDF、DOCX、Markdown** 格式简历
- 多策略解析：PyMuPDF（PDF）、python-docx（DOCX）、纯文本（MD）
- LLM 驱动结构化提取，字段附带置信度评分
- 简历列表管理、删除、重新加载
- 调试解析接口，分步查看提取中间结果

### 2. 🎯 JD 匹配与分析
- 粘贴职位描述 → 结构化提取硬性要求、加分项、关键词频率
- **两阶段匹配**：向量召回（低成本）→ LLM 重排序（高精度）
- 逐条要求匹配度评分（满足 / 部分满足 / 未满足），附证据与改进建议
- **JD 隐性信号检测**：危险短语、文化倾向、紧急程度提示
- 匹配结果可视化：评分环图、匹配明细、信号解读卡片

### 3. 🧠 内容深度优化（通过 Agent 对话）
- STAR 完整性分析
- 弱动词检测与替换建议
- 量化密度建议
- **规则 + LLM 双轨评估** — 规则引擎毫秒级捕获常见问题，LLM 处理深层语义
- ATS 兼容性模拟检查

### 4. 💻 GitHub 项目分析
- 提交 GitHub 仓库 URL → **五阶段渐进式 SSE 分析**：
  1. 仓库元数据获取
  2. 目录结构分析
  3. 依赖与 Issue/PR 深度分析
  4. 个人发展方向与改进建议（LLM 生成）
  5. 准备就绪 → 按需生成 **STAR 格式简历条目**
- SSE 实时流式推送，每阶段结果逐步呈现

### 5. 🗣 面试准备
- **面试问题生成** — 4 类题目：STAR 深挖追问、技术深度追问、行为面试题、压力测试题，附带公司针对性建议
- **自我介绍脚本** — 根据简历 + 目标岗位定制短版（60s）和长版（180s）
- **简历弱点分析** — 检测简历中的短板，生成风险评级与应对策略（含参考话术）
- 支持导出为 **Markdown / PDF**

### 6. 🔄 智能聊天 Agent
- 类 LangGraph **Plan→Act→Observe→Replan** 推理循环
- SSE 流式实时响应，推理过程逐步展示
- 工具调用：简历 CRUD、JD 匹配、网络搜索、质量评估
- 会话历史管理（保存/加载/自动续期）

### 7. 📤 导出
- 简历导出为 **Markdown、HTML、PDF**
- 面试内容（问题、自我介绍、弱点分析）导出为 Markdown / PDF
- PDF 导出基于 PyMuPDF 内置中文字体，无需额外字库

---

## 🏗 系统架构

```
┌──────────────────────────────────────────────────────┐
│                    前端 (Next.js 14)                    │
│  ┌──────────┐  ┌──────────┐  ┌───────────────────┐   │
│  │ 聊天首页  │  │ JD 匹配  │  │ 面试准备          │   │
│  │ (SSE)    │  │ 页面     │  │ 页面              │   │
│  └────┬─────┘  └────┬─────┘  └───────┬───────────┘   │
│       │              │                │               │
│       └──────────────┴────────────────┘               │
│                       │ API 客户端 (/lib/api.ts)       │
└───────────────────────┼──────────────────────────────┘
                        │ HTTP / SSE
┌───────────────────────┼──────────────────────────────┐
│             后端 (FastAPI, Python 3.11+)               │
│  ┌──────────────────────────────────────────────────┐ │
│  │              API 层 (api/routes/)                  │ │
│  │  /chat  /resume  /jd  /export  /github  /interview│ │
│  └──────────────────────┬───────────────────────────┘ │
│                         │                              │
│  ┌──────────────────────┴───────────────────────────┐ │
│  │              Agent 核心 (agent/)                   │ │
│  │  ┌──────────┐  ┌──────────┐  ┌────────────────┐  │ │
│  │  │ 规划器    │  │  循环    │  │  上下文         │  │ │
│  │  │ (双层)   │  │(P→A→O→R) │  │  组装器         │  │ │
│  │  └──────────┘  └────┬─────┘  └────────┬───────┘  │ │
│  │                     │                  │           │ │
│  │  ┌──────────────────┴──────────────────┴────────┐ │ │
│  │  │           工具系统 (agent/tools/)              │ │ │
│  │  │  简历 ｜ JD ｜ GitHub ｜ 面试 ｜ 网页 ｜ ...  │ │ │
│  │  └──────────────────────┬───────────────────────┘ │ │
│  │                         │                          │ │
│  │  ┌──────────────────────┴───────────────────────┐ │ │
│  │  │          记忆系统 (agent/memory/)              │ │ │
│  │  │  ChromaDB (向量)  +  SQLite (元数据)          │ │ │
│  │  └──────────────────────┬───────────────────────┘ │ │
│  │                         │                          │ │
│  │  ┌──────────────────────┴───────────────────────┐ │ │
│  │  │          核心逻辑 (core/)                      │ │ │
│  │  │  简历 ｜ JD ｜ 面试 ｜ GitHub ｜ 评估 ｜ 缓存 │ │ │
│  │  └──────────────────────────────────────────────┘ │ │
│  └──────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────┘
```

### Agent 循环流程

```
                    ┌─────────┐
                    │  开始   │
                    └────┬────┘
                         ▼
              ┌─────────────────────┐
         ┌───│ 规划: 接下来做什么?  │
         │   │ (回复 / 追问 /       │
         │   │  调用工具)           │
         │   └──────────┬──────────┘
         │              ▼
         │   ┌─────────────────────┐
         │   │ 执行: 运行工具       │◄──── 指数退避
         │   │ (并行、重试)         │      重试
         │   └──────────┬──────────┘
         │              ▼
         │   ┌─────────────────────┐
         │   │ 观察: 评估结果       │
         │   │ (成功 / 部分成功    │
         │   │  / 失败)            │
         │   └──────────┬──────────┘
         │              │
         │    ┌─────────┴──────────┐
         │    ▼                    ▼
         │ 还需继续?        任务完成
         │                  或需用户?
         │    │                    │
         └────┘                    ▼
                           ┌─────────────┐
                           │ 输出 / 结束  │
                           └─────────────┘
```

---

## 🛠 技术栈

| 层级 | 技术 | 用途 |
|------|------|------|
| **框架** | FastAPI + Uvicorn | 异步 Python 后端，支持 SSE 流式 |
| **Agent** | 自定义 LangGraph 风格循环 | Plan→Act→Observe→Replan 编排 |
| **LLM** | Anthropic Claude / OpenAI 兼容 | 统一客户端，支持多供应商 |
| **向量库** | ChromaDB（嵌入式） | 语义记忆和 JD/简历向量检索 |
| **数据库** | SQLite（WAL 模式） | 元数据、会话、检查点持久化 |
| **缓存** | diskcache | LLM 响应缓存（降低延迟与成本） |
| **文档解析** | PyMuPDF、python-docx | PDF/DOCX 简历文本提取 |
| **前端** | Next.js 14 + React 18 + Tailwind CSS | 现代混合渲染 UI |
| **流式** | Server-Sent Events (SSE) | 实时 Agent 响应与多阶段分析推送 |

---

## 🚀 快速开始

### 环境要求

- **Python 3.11+**
- **Node.js 18+**（前端）

### 后端启动

```bash
# 1. 克隆仓库
git clone https://github.com/pyqx/resume-agent.git && cd resume-agent

# 2. 创建虚拟环境
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/Mac:
# source .venv/bin/activate

# 3. 安装 Python 依赖
pip install -e ".[dev]"

# 4. 配置环境变量
# 编辑 .env 文件，设置 LLM 供应商和 API Key

# 5. 初始化数据库
python -c "from core.database import init_db; import asyncio; asyncio.run(init_db())"

# 6. 启动后端服务
uvicorn api.main:app --reload --host 127.0.0.1 --port 8000
```

### 前端启动

```bash
# 1. 进入前端目录
cd frontend

# 2. 安装依赖
npm install

# 3. 启动开发服务器
npm run dev
```

前端运行在 **http://localhost:3000**，API 请求自动代理到 **http://localhost:8000**。

### 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `LLM_PROVIDER` | `openai_compatible` | `anthropic` 或 `openai_compatible` |
| `LLM_API_KEY` | — | LLM API 密钥 |
| `LLM_MODEL` | `deepseek-v4-flash` | 模型名称 |
| `LLM_BASE_URL` | `https://api.deepseek.com` | API 地址（OpenAI 兼容模式） |
| `HOST` | `127.0.0.1` | 后端绑定地址 |
| `PORT` | `8000` | 后端端口 |
| `CORS_ORIGINS` | `["http://localhost:3000"]` | 允许的 CORS 来源 |

---

## 📁 项目结构

```
resume-agent/
├── agent/                    # Agent 核心（"大脑"）
│   ├── loop.py               # 主 P→A→O→R 循环（状态机）
│   ├── planner.py            # 战略 + 战术双层规划器
│   ├── context.py            # 上下文组装器
│   ├── checkpoint.py         # 容错检查点
│   ├── memory/               # ChromaDB + SQLite 记忆系统
│   │   ├── extractor.py      # LLM 事实提取
│   │   ├── consolidator.py   # 去重与冲突检测
│   │   ├── retriever.py      # 语义检索
│   │   ├── store.py          # 双写存储
│   │   └── models.py         # 数据模型
│   └── tools/                # 工具系统
│       ├── registry.py       # 注册中心
│       ├── resume_tools.py   # 简历 CRUD
│       ├── jd_tools.py       # JD 匹配
│       ├── interview_tools.py
│       ├── github_tools.py   # GitHub 5 阶段分析
│       ├── web_tools.py      # 网页搜索/抓取
│       ├── memory_tools.py   # 记忆读写
│       ├── quality_tools.py  # 质量评估
│       └── base.py           # 基类
├── api/                      # FastAPI 后端
│   ├── main.py               # 入口、中间件、路由注册
│   ├── deps.py               # 依赖注入
│   ├── session_manager.py    # 会话持久化
│   ├── middleware/            # CORS / 日志 / 隐私脱敏
│   └── routes/
│       ├── chat.py           # SSE 流式聊天
│       ├── resume.py         # 简历 CRUD + 上传 + 解析
│       ├── jd.py             # JD 解析、匹配、信号
│       ├── export.py         # Markdown/HTML/PDF 导出
│       ├── github.py         # GitHub SSE 分析
│       ├── interview.py      # 面试题/自我介绍/弱点
│       └── sessions.py       # 会话历史
├── core/                     # 业务逻辑
│   ├── config.py             # pydantic-settings
│   ├── database.py           # SQLite 初始化
│   ├── llm.py                # 统一 LLM 客户端
│   ├── cache.py              # diskcache
│   ├── vector_store.py       # ChromaDB
│   ├── logging_setup.py      # 日志配置
│   ├── resume/               # 解析、Schema、导出
│   ├── jd/                   # 解析、匹配、信号检测
│   ├── interview/            # 题目/自我介绍/弱点
│   ├── github/               # 分析编排器
│   └── evaluation/           # ATS 模拟、规则引擎、评分
├── frontend/                 # Next.js 14
│   ├── app/
│   │   ├── page.tsx          # 聊天首页（上传 + 对话）
│   │   ├── match/page.tsx    # JD 匹配页面
│   │   └── interview/page.tsx # 面试准备页面
│   ├── components/
│   │   ├── chat/             # 聊天面板、消息气泡、推理链
│   │   ├── resume/           # 简历展示、段落卡片
│   │   ├── match/            # 匹配报告（评分环）
│   │   └── layout/           # 侧边栏导航
│   ├── contexts/             # React Context 状态管理
│   ├── hooks/                # useSSE、useResume
│   └── lib/api.ts            # API 客户端
├── prompts/                  # YAML 提示词模板
│   ├── agent/                # 系统/规划器/记忆提取
│   ├── interview/            # 面试/自我介绍
│   ├── github/               # 建议/简历条目
│   └── evaluation/           # LLM 评判准则
├── data/                     # 运行时数据（gitignore）
├── tests/                    # 测试
├── .env                      # 环境配置（gitignore）
├── pyproject.toml
├── README-EN.md              # 英文文档
└── README.md                 # 中文文档（本文件）
```

---

## 🔐 隐私与安全

- **隐私脱敏中间件** — 手机号、邮箱、社交账号等在发送给 LLM **前**自动掩码，响应后再通过映射还原
- **本地优先存储** — SQLite + 嵌入式 ChromaDB，数据完全自控
- **无外部服务依赖** — 不依赖外部数据库或向量数据库服务，仅 LLM API 调用涉及数据传输
- **可配置 LLM 供应商** — 支持 Anthropic Claude 或 OpenAI 兼容接口

---

## 🧪 测试

```bash
pytest
pytest --cov=agent --cov=core --cov=api
pytest tests/unit/
pytest tests/integration/
```

---

## 🧰 开发

```bash
pip install -e ".[dev]"
uvicorn api.main:app --reload --host 127.0.0.1 --port 8000   # 后端开发
cd frontend && npm run dev                                      # 前端开发
ruff check .                                                     # Python 代码检查
```

---

## 📄 License

MIT License

---

<p align="center">为中文求职市场的求职者打造 ❤️</p>
