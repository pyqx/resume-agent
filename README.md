# 🎯 Resume Agent — 简历助手

<h3 align="center">
  AI 驱动的智能简历深度优化引擎 · 你的职业叙事顾问
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

**Resume Agent** 是一个全栈 AI 简历助手，核心是一个**单 Agent 深度推理循环**（规划 → 执行 → 观察 → 再规划）。它并非简单的 LLM 聊天界面，而是一个能够自主规划多步任务、调用工具、评估结果并自我修正的智能体，提供远超模板填充的深度职业叙事指导。

专为**中文求职市场**设计，完整支持中文简历解析、中文 JD 匹配和中文面试准备。

### 与传统方案对比

| 维度 | 传统应用 | Resume Agent |
|------|----------|--------------|
| 推理方式 | 单次 LLM 调用，无迭代 | 规划→执行→观察→再规划，带自我修正 |
| 记忆能力 | 无状态或短上下文 | mem0 风格持久记忆（ChromaDB + SQLite） |
| 工具使用 | 无或固定流程 | 根据上下文动态选择工具 |
| 容错机制 | 无 | 四层韧性（重试→降级→检查点→人工交接） |
| 隐私保护 | 完整发送数据给 LLM | 隐私脱敏中间件，LLM 调用前掩码处理 |

---

## ✨ 功能特性

### 1. 📄 智能简历解析与管理
- 上传 **PDF、DOCX、Markdown** 格式简历
- 多策略解析（pymupdf 解析 PDF、python-docx 解析 DOCX、OCR 降级方案）
- 结构化输出，每个字段附带置信度评分
- **写时复制（Copy-on-Write）版本管理** — 从主版本派生子版本，仅存储差异
- 所见即所得编辑器，支持内联编辑和版本差异对比

### 2. 🎯 JD 匹配与分析
- 粘贴职位描述 → 自动提取要求、职责和隐藏信号
- **两阶段匹配**：向量召回（低成本）→ LLM 重排序（高精度）
- 逐条需求的匹配度评分，附详细推理
- 隐藏信号检测（危险信号、文化倾向、紧急程度）
- 关键词提取，辅助简历针对性调整

### 3. 🧠 内容深度优化
- 每条经历的 STAR 完整性分析
- 弱动词检测与替换建议
- 量化密度评分
- **规则 + LLM 双轨评估** — 80% 问题由本地规则毫秒级捕获，20% 需 LLM 判断
- ATS（申请者追踪系统）兼容性模拟

### 4. 🎨 格式与导出
- 多种模板（专业、现代、简约、ATS 优化）
- 导出为 **Markdown / HTML / PDF**
- ATS 友好输出验证

### 5. 💻 GitHub 项目分析
- 提交 GitHub 仓库 URL → 五阶段渐进式分析：
  1. 目录结构理解
  2. 依赖分析
  3. Issue/PR 模式分析
  4. 改进方向建议
  5. **从真实项目贡献生成 STAR 简历条目**
- SSE 流式输出 — 每个阶段完成后结果逐步呈现

### 6. 🗣 面试准备
- **问题生成** — 4 类题目：技术、行为、项目经验、HR 向
- **自我介绍脚本** — 根据简历 + 目标职位定制
- **弱点分析** — 发现简历短板，生成应对策略

### 7. 🔄 智能聊天 Agent
- 对话式交互，完整展示 Agent 推理过程
- SSE 流式实时响应
- 会话历史管理
- 上下文感知工具调用（简历 CRUD、JD 匹配、网络搜索、质量评估）

---

## 🏗 系统架构

```
┌──────────────────────────────────────────────────────┐
│                    前端 (Next.js 14)                    │
│  ┌──────────┐  ┌──────────┐  ┌───────────────────┐   │
│  │ 聊天界面  │  │ JD 匹配  │  │ 面试准备          │   │
│  │ (SSE)    │  │ 页面     │  │ 页面              │   │
│  └────┬─────┘  └────┬─────┘  └───────┬───────────┘   │
│       │              │                │               │
│       └──────────────┴────────────────┘               │
│                       │  API 客户端 (/lib/api.ts)      │
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
│  │  │  简历 │ JD │ GitHub │ 面试 │ 网页 │ ...      │ │ │
│  │  └─────────────────────────┬────────────────────┘ │ │
│  │                            │                        │ │
│  │  ┌─────────────────────────┴────────────────────┐ │ │
│  │  │          记忆系统 (agent/memory/)              │ │ │
│  │  │  ChromaDB (向量)  +  SQLite (元数据)          │ │ │
│  │  └─────────────────────────┬────────────────────┘ │ │
│  │                            │                        │ │
│  │  ┌─────────────────────────┴────────────────────┐ │ │
│  │  │          核心逻辑 (core/)                      │ │ │
│  │  │  简历│JD│面试│GitHub│评估│缓存               │ │ │
│  │  └─────────────────────────────────────────────┘ │ │
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
| **Agent** | 自定义类 LangGraph 循环 | 规划→执行→观察→再规划编排 |
| **LLM** | Anthropic Claude / OpenAI 兼容 | 统一客户端，支持多供应商 |
| **向量库** | ChromaDB (嵌入式) | 语义记忆和 JD/简历检索 |
| **数据库** | SQLite (WAL 模式) | 元数据、会话、检查点持久化 |
| **缓存** | diskcache | LLM 响应缓存（降低成本） |
| **文档解析** | PyMuPDF, python-docx | 从 PDF、DOCX、Markdown 解析简历 |
| **前端** | Next.js 14 + React 18 + Tailwind CSS | 现代混合渲染 UI |
| **流式** | Server-Sent Events (SSE) | 实时 Agent 响应流式推送 |

---

## 🚀 快速开始

### 环境要求

- **Python 3.11+**
- **Node.js 18+**（前端）
- **pip**（Python 包管理器）

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
# (参考下方环境变量说明)

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

前端运行在 **http://localhost:3000**，API 请求通过 Next.js 代理转发到 **http://localhost:8000**。

### 环境变量说明

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `LLM_PROVIDER` | `openai_compatible` | `anthropic` 或 `openai_compatible` |
| `LLM_API_KEY` | — | 你的 LLM API 密钥 |
| `LLM_MODEL` | `deepseek-v4-flash` | 模型名称 |
| `LLM_BASE_URL` | `https://api.deepseek.com` | API 基础地址（OpenAI 兼容模式） |
| `LLM_TEMPERATURE` | `0.7` | 生成温度 |
| `LLM_MAX_TOKENS` | `4096` | 每次响应最大 Token 数 |
| `HOST` | `127.0.0.1` | 后端绑定地址 |
| `PORT` | `8000` | 后端端口 |
| `CORS_ORIGINS` | `["http://localhost:3000"]` | 允许的 CORS 来源 |

---

## 📁 项目结构

```
resume-agent/
├── agent/                  # Agent 核心（"大脑"）
│   ├── loop.py             # 主 P→A→O→R 循环（状态机）
│   ├── planner.py          # 战略 + 战术双层规划器
│   ├── context.py          # 上下文组装器（系统提示 + 记忆 + 状态）
│   ├── checkpoint.py       # 容错检查点保存/恢复
│   ├── memory/             # mem0 风格记忆系统
│   │   ├── extractor.py    # LLM 驱动的事实提取
│   │   ├── consolidator.py # 合并、去重、冲突检测
│   │   ├── retriever.py    # 语义搜索 + 类型过滤
│   │   ├── store.py        # ChromaDB + SQLite 双写
│   │   └── models.py       # 记忆数据模型
│   └── tools/              # Agent 工具系统
│       ├── registry.py     # 工具注册中心
│       ├── resume_tools.py # 简历 CRUD + 版本工具
│       ├── jd_tools.py     # JD 匹配工具
│       ├── interview_tools.py  # 面试工具
│       ├── github_tools.py # GitHub 分析工具（5 阶段）
│       ├── web_tools.py    # 网页搜索/抓取工具
│       ├── memory_tools.py # 记忆读写工具
│       ├── quality_tools.py # 质量评估工具
│       └── base.py         # BaseTool、ToolMetadata、ToolResult
├── api/                    # FastAPI 后端
│   ├── main.py             # 入口、中间件、路由注册
│   ├── deps.py             # 依赖注入
│   ├── session_manager.py  # 对话会话持久化
│   ├── middleware/
│   │   ├── cors.py
│   │   ├── logging.py      # JSON 结构化日志
│   │   └── sanitizer.py    # 隐私脱敏中间件
│   └── routes/
│       ├── chat.py         # SSE 流式 + 非流式聊天
│       ├── resume.py       # 简历 CRUD + 上传 + 调试解析
│       ├── jd.py           # JD 解析、匹配、信号、关键词
│       ├── export.py       # PDF/Markdown/HTML 导出 + 模板
│       ├── github.py       # GitHub 渐进式分析（SSE）
│       ├── interview.py    # 题目、自我介绍、弱点分析
│       └── sessions.py     # 会话历史 CRUD
├── core/                   # 业务逻辑（与 Agent 无关）
│   ├── config.py           # pydantic-settings（读取 .env）
│   ├── database.py         # SQLite WAL 模式初始化 + 建表
│   ├── llm.py              # 统一 LLM 客户端
│   ├── cache.py            # diskcache 初始化/读取
│   ├── vector_store.py     # ChromaDB 嵌入式初始化
│   ├── logging_setup.py    # 轮转文件 + 控制台日志
│   ├── resume/             # 简历解析、Schema、版本、导出
│   ├── jd/                 # JD 解析、匹配、信号检测
│   ├── interview/          # 题目/自我介绍/弱点生成
│   ├── github/             # GitHub 分析编排器
│   └── evaluation/         # ATS 模拟、LLM 评判、规则引擎、评分
├── frontend/               # Next.js 14 App Router
│   ├── app/
│   │   ├── page.tsx        # 主聊天页面
│   │   ├── match/page.tsx  # JD 匹配页面
│   │   └── interview/page.tsx  # 面试准备页面
│   ├── components/
│   │   ├── chat/           # ChatPanel、MessageBubble、ReasoningChain
│   │   ├── resume/         # ResumeEditor、DiffViewer、SectionCard
│   │   ├── match/          # MatchReport（评分环、详情卡片）
│   │   └── layout/         # Sidebar（导航 + 会话历史）
│   ├── contexts/           # ResumeContext、PageStateContext
│   ├── hooks/              # useSSE、useResume
│   └── lib/api.ts          # 类型化 API 客户端
├── prompts/                # YAML 提示词模板（版本化管理）
│   ├── agent/              # 系统、规划器、记忆提取提示词
│   ├── interview/          # 题目、自我介绍提示词
│   ├── github/             # 建议、简历条目提示词
│   └── evaluation/         # LLM 评判评分准则
├── data/                   # 运行时数据（gitignore）
│   ├── chroma/             # ChromaDB 持久化存储
│   ├── cache/              # diskcache 存储
│   ├── logs/               # 应用日志
│   └── uploads/            # 上传的简历文件
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/           # 样本简历、JD
├── .env                    # 环境配置（已 gitignore）
├── pyproject.toml          # Python 项目配置 + 依赖
├── README-EN.md            # 英文文档
└── README.md               # 中文文档（本文件）
```

---

## 🔐 隐私与安全

Resume Agent 遵循**默认隐私优先**的设计原则：

- **隐私脱敏中间件** — 电话号码、邮箱、社交账号等敏感信息在**发送给 LLM 前**进行掩码处理，响应结果再通过映射还原
- **本地优先存储** — SQLite + 嵌入式 ChromaDB，无需外部数据库，数据完全自控
- **无外部向量数据库** — ChromaDB 以内嵌方式运行，除了 LLM API 调用外，数据不离开你的机器
- **可配置 LLM 供应商** — 可使用 Anthropic Claude（有明确数据使用政策），也可通过兼容接口连接本地部署的模型

---

## 🧪 测试

```bash
# 运行所有测试
pytest

# 带覆盖率运行
pytest --cov=agent --cov=core --cov=api

# 运行指定测试类别
pytest tests/unit/
pytest tests/integration/
```

---

## 🧰 开发

```bash
# 安装开发依赖
pip install -e ".[dev]"

# 开发模式启动后端
uvicorn api.main:app --reload --host 127.0.0.1 --port 8000

# 开发模式启动前端
cd frontend && npm run dev

# 代码检查
ruff check .               # Python
cd frontend && npm run lint # TypeScript
```

---

## 🗺 路线图

- [x] 简历解析（PDF / DOCX / MD）
- [x] JD 结构化解析与匹配
- [x] Agent 聊天与推理循环
- [x] GitHub 项目分析
- [x] 面试准备工具
- [x] 多种格式导出（Markdown / HTML / PDF）
- [x] 版本管理与差异对比
- [ ] 投递后申请追踪
- [ ] 多语言简历支持
- [ ] 批量 JD 分析与横向对比
- [ ] 简历评分与改进建议面板

---

## 📄 许可证

本项目基于 **MIT License** 开源。

---

<p align="center">
  为中文求职市场求职者精心打造 ❤️
</p>
