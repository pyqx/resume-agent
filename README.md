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

**Resume Agent** 是一个本地优先的全栈 AI 简历助手,核心是一个**单 Agent 推理循环**(规划 → 执行 → 观察 → 再规划),能够自主调用工具、评估结果并自我修正。专为**中文求职市场**设计,完整支持中文简历解析、JD 匹配和面试准备。

上传简历后,可以针对目标岗位做匹配分析、挖掘简历短板、生成面试题目和自我介绍,分析 GitHub 项目并生成 STAR 格式的简历条目,并将结果导出为 Markdown 或 PDF。

> 定位:**单用户本地工具**。后端默认只绑定 127.0.0.1,不含多用户鉴权;请勿直接暴露到公网。

---

## ✨ 功能特性

### 1. 📄 简历解析与管理
- 上传 **PDF、DOCX、Markdown/TXT** 简历(上限 10MB,文件名安全化处理)
- 多策略解析:PyMuPDF(PDF,含双栏检测与线性化)、python-docx(DOCX)、纯文本
- LLM 结构化提取 + 三级 JSON 容错(提取 → 修复 → 清洗重试),失败降级为规则抽取(置信度会相应降低)
- 字段附带置信度;仅有年份的日期会标记为"约",避免下游误判空窗期
- 简历列表 / 删除 / 重新加载;当前选中简历跨重启保持

### 2. 🎯 JD 匹配与分析
- 粘贴职位描述 → LLM 结构化提取硬性要求、加分项、关键词频率
- **逐条要求 LLM 评分**(有界并发):满足 / 部分满足(计半分)/ 未满足 / 无法评估,附证据与改进建议;单条评分失败会明确标记而不是静默计 0
- 关键词覆盖率:分词 + 词边界匹配(中文子串匹配),不再有 "go 命中 google" 式误报
- **JD 隐性信号检测**:22 条规则(含 996、大小周、奋斗者、抗压等中文信号),支持否定语抑制("不加班"不报警)
- 匹配结果缓存(按简历内容 + JD 指纹),重复分析秒回

### 3. 🧠 内容质量评估(通过 Agent 对话)
- 规则引擎:弱动词(扣分封顶)、敏感信息、页数、中英文空格、日期一致性、技术名词大小写 —— 全部基于真实渲染文本
- LLM 五维评分(STAR 完整性 / 量化密度 / 术语准确性 / 简洁性 / 叙事连贯),带分档 rubric,加权总分在服务端计算
- ATS 模拟:关键字段可提取性 + 格式检查 + 关键词覆盖
- LLM 不可用时明确降级(权重重归一),**不会返回假分数**

### 4. 💻 GitHub 项目分析
- 提交仓库 URL(支持 GitHub/GitLab/Gitee)→ **五阶段渐进式 SSE 分析**:
  1. 仓库元数据(支持 `GITHUB_TOKEN`,限流时明确提示而非返回假数据)
  2. 目录结构与技术栈(单次浅克隆,阶段间复用;凭据隔离;敏感文件排除)
  3. 依赖清单(tomllib 真实解析)+ Issue 机会扫描(过滤 PR,并行请求)
  4. 个性化改进建议(结合简历的目标岗位)
  5. 按需生成 **STAR 格式简历条目**
- 阶段结果缓存;任何阶段失败都会推送明确的 error 事件

### 5. 🗣 面试准备
- **面试问题生成**:STAR 深挖 / 技术追问 / 行为面 / 压力测试;提供 JD 时按岗位定向出题
- **自我介绍脚本**:短版(约 200 字)与长版(约 500 字),附核心信息点与表达技巧
- **简历弱点分析**:规则检测(空窗期 / 频繁跳槽 / 无量化成果 / 当前任期过短 / 无教育经历)+ LLM 生成诚实的应对话术;规则零命中时仍会做一次内容质量审查;近似日期不会制造假空窗
- 导出 Markdown / PDF(内置中文字体)

### 6. 🔄 智能聊天 Agent
- Plan→Act→Observe→Replan 推理循环(手写状态机),SSE 流式推送推理过程
- **33 个已注册工具**:简历读改增删、版本管理、JD 解析/匹配/信号/关键词、GitHub 五阶段、面试三件套、质量评估、记忆读写、网页搜索/抓取
- 工具权限强制执行:前置条件在执行时校验;删除类工具必须显式确认(`confirm=true`)
- 长期记忆:对话结束后自动提取用户事实(目标岗位、偏好、反馈),跨会话生效;后台定期去重合并
- 崩溃恢复:意外中断的会话可从检查点恢复已完成的工具调用记录
- 会话历史持久化(SQLite),多轮上下文注入

### 7. 📤 导出
- 简历导出 Markdown / HTML(已做 XSS 转义)/ PDF
- 面试内容导出 Markdown / PDF;PDF 基于 PyMuPDF 内置中文字体,按实际字宽折行

### 8. 🖥 前端界面
- **聊天首页**:推理链可视化(计划 → 工具调用 → 结果逐步展示)、停止生成、Markdown 渲染、会话跨页/刷新续接
- **JD 匹配页**:评分环、逐条明细("无法评估"态明确标注)、隐性信号卡、缺失关键词提示
- **面试准备页**:三类内容生成、JD 定向出题、一键复制、带时间戳的 Markdown/PDF 导出
- **GitHub 分析页**:五阶段渐进展示、限流提示、建议卡片(难度/工时/简历影响)、STAR 条目生成与复制
- **简历面板**:条目在线编辑/删除(带确认)、版本快照与字段级差异对比、导出工具栏;近似日期标注"(约)"

---

## 🔐 隐私与安全

- **PII 可逆掩码**:手机号、邮箱、身份证、薪资、微信在**发送给 LLM 前**替换为占位符,响应后自动还原(`SANITIZE_PII` 可关);日志层同样有不可逆脱敏过滤器
- **本地优先**:SQLite + 嵌入式 ChromaDB + 磁盘缓存,仅 LLM API 调用出网
- **SSRF 防护**:网页抓取工具拦截内网/回环/云元数据地址,重定向逐跳校验,响应体限 2MB
- **仓库克隆隔离**:禁用凭据助手与终端提示,私有仓库快速失败;`.env`/密钥类文件不进入分析
- **提示词注入防护**:简历、JD、GitHub 内容以不可信数据标记包裹,系统提示明确拒绝执行内容内指令
- 调试端点默认关闭(`DEBUG_ENDPOINTS=false`)

---

## 🛠 技术栈

| 层级 | 技术 | 用途 |
|------|------|------|
| **框架** | FastAPI + Uvicorn | 异步后端,SSE 流式 |
| **Agent** | 自定义状态机循环 | Plan→Act→Observe→Replan 编排 |
| **LLM** | Anthropic / OpenAI 兼容(DeepSeek 等) | 统一异步客户端:超时、退避重试、PII 掩码、JSON 提取 |
| **向量库** | ChromaDB(嵌入式) | 语义记忆检索 |
| **数据库** | SQLite(WAL) | 会话、消息、记忆元数据、检查点(简历与版本为本地 JSON 文件) |
| **缓存** | diskcache | 匹配报告与 GitHub 分析缓存 |
| **文档解析** | PyMuPDF、python-docx | PDF/DOCX 文本提取 |
| **前端** | Next.js 14 + React 18 + Tailwind | 聊天 / 匹配 / 面试 / GitHub 分析页面 |

---

## 🚀 快速开始

### 环境要求

- **Python 3.11+**、**Node.js 18+**、git(GitHub 分析功能需要)

### 后端启动

```bash
# 1. 安装依赖
pip install -e ".[dev]"

# 2. 配置环境变量
cp .env.example .env   # 编辑 .env,填入 LLM_API_KEY 等

# 3. 启动(数据库自动初始化与迁移)
uvicorn api.main:app --host 127.0.0.1 --port 8000
```

### 前端启动

```bash
cd frontend
npm install
npm run dev
```

前端 **http://localhost:3000**,API 自动代理到后端;后端地址可用 `NEXT_PUBLIC_API_BASE` 覆盖。

### 环境变量(完整清单见 `.env.example`)

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `LLM_PROVIDER` | `anthropic` | `anthropic` 或 `openai_compatible` |
| `LLM_API_KEY` | — | LLM API 密钥(必填) |
| `LLM_MODEL` | `claude-sonnet-4-6` | 模型名称 |
| `LLM_BASE_URL` | — | OpenAI 兼容模式的 API 地址 |
| `SANITIZE_PII` | `true` | LLM 出站 PII 掩码开关 |
| `GITHUB_TOKEN` | — | 可选;不设则受 60 次/小时限流 |
| `DEBUG_ENDPOINTS` | `false` | 调试解析端点开关 |
| `MAX_UPLOAD_SIZE_MB` | `10` | 上传大小限制 |

---

## 📁 项目结构

```
resume-agent/
├── agent/                    # Agent 核心
│   ├── loop.py               # P→A→O→R 状态机(轮次语义、幂等重试、降级回复)
│   ├── context.py            # 每轮重组装的上下文(记忆 + 动态工具门控)
│   ├── checkpoint.py         # 崩溃恢复检查点(干净结束自动清理)
│   ├── memory/               # 记忆系统(提取 → 双写 → 检索 → 巩固,全链路可用)
│   └── tools/                # 33 个工具 + 注册中心(执行时强制前置条件与确认)
├── api/                      # FastAPI
│   ├── main.py               # 入口、真实健康检查、全局异常处理
│   ├── deps.py               # DI 容器(加锁懒初始化、记忆巩固后台任务)
│   ├── session_manager.py    # 会话持久化(写锁、标题只设一次)
│   └── routes/               # chat(SSE) / resume / versions / jd / export / github(SSE) / interview / sessions
├── core/
│   ├── llm.py                # 统一异步 LLM 客户端 + 共享 JSON/模板/防注入工具函数
│   ├── config.py             # pydantic-settings(路径可覆盖、锚定项目根)
│   ├── resume/               # schema / 解析 / 脱敏 / 导出 / 版本管理
│   ├── jd/                   # 解析 / 匹配 / 信号检测 / 关键词覆盖
│   ├── interview/            # 问题 / 自我介绍 / 弱点(统一语言检测)
│   ├── github/               # 克隆 / 结构 / 依赖 / Issue / 建议 / 条目
│   └── evaluation/           # 渲染 / 规则 / LLM 评审 / ATS / 聚合
├── frontend/                 # Next.js(聊天 / JD 匹配 / 面试 / GitHub 分析)
├── tests/                    # pytest 单元测试
├── .env.example
└── pyproject.toml
```

---

## 🧪 测试与开发

```bash
pytest                    # 运行测试
ruff check .              # Python 静态检查
cd frontend && npm run lint && npm run typecheck
```

---

## 📄 License

MIT License

---

<p align="center">为中文求职市场的求职者打造 ❤️</p>
