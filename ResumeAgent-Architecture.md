# 简历助手 Agent — 技术架构设计文档

> 版本: v1.0 | 日期: 2026-05-23 | 配套 PRD: [ResumeAgent-PRD.md](./ResumeAgent-PRD.md)

---

## 目录

1. [架构总览](#1-架构总览)
2. [Agent 核心循环](#2-agent-核心循环)
3. [工具系统设计](#3-工具系统设计)
4. [Memory 系统设计](#4-memory-系统设计)
5. [长时序规划与容错](#5-长时序规划与容错)
6. [技术栈选型](#6-技术栈选型)
7. [关键模块设计](#7-关键模块设计)
8. [项目目录结构](#8-项目目录结构)
9. [部署方案](#9-部署方案)
10. [附录：面试叙事参考](#10-附录面试叙事参考)

---

## 1. 架构总览

### 1.1 设计原则

本项目的核心定位：**单 Agent，深推理** —— 在一个 Agent 内实现复杂推理链、长时序任务规划、精细化工具编排和单点容错。

与 Multi-Agent 架构追求"广度"不同，单 Agent 架构追求的是"深度"：

| 维度 | Multi-Agent 方案 | 本方案（单 Agent 深度） |
|------|-----------------|----------------------|
| 核心挑战 | Agent 间协调通信 | 长链推理的稳定性与自我纠错 |
| 决策模式 | 分发 → 收集 | Plan → Act → Observe → Replan 循环 |
| 容错策略 | Agent 冗余 | Checkpoint 恢复 + 策略降级 + 幂等 |
| 记忆系统 | 各 Agent 独立记忆 | 统一的 mem0 风格结构化记忆 |
| 部署复杂度 | 高（多服务协作） | 低（单进程，嵌入式中数据库） |

### 1.2 架构全景图

```
┌──────────────────────────────────────────────────────────────┐
│                     Frontend (Next.js 14)                     │
│  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌─────────────┐  │
│  │ 会话界面   │ │ 简历编辑器 │ │ 匹配报告   │ │ 版本管理    │  │
│  │ (SSE 流式) │ │ (所见即得) │ │ (可视化)   │ │ (差异对比)  │  │
│  └───────────┘ └───────────┘ └───────────┘ └─────────────┘  │
└──────────────────────────┬───────────────────────────────────┘
                           │ HTTP + SSE (Server-Sent Events)
┌──────────────────────────▼───────────────────────────────────┐
│                    Backend (FastAPI)                          │
│                                                               │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │                   Agent Core Loop                        │ │
│  │                                                          │ │
│  │   ┌────────┐   ┌────────┐   ┌──────────┐   ┌────────┐  │ │
│  │   │ CONTEXT│──▶│  PLAN  │──▶│   ACT    │──▶│OBSERVE │  │ │
│  │   │ASSEMBLE│   │ (推理) │   │(工具调用) │   │(评估)  │  │ │
│  │   └────────┘   └────────┘   └──────────┘   └────────┘  │ │
│  │        ▲                                        │        │ │
│  │        │              ┌──────────┐              │        │ │
│  │        └──────────────│ REPLAN   │◀─────────────┘        │ │
│  │                       │ (修正计划)│  目标未达成/工具异常   │ │
│  │                       └──────────┘                       │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                               │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────────┐  │
│  │  Tool    │ │ Memory   │ │ Strategy │ │  Evaluation    │  │
│  │ Registry │ │ System   │ │ Planner  │ │  Framework     │  │
│  │          │ │          │ │          │ │                │  │
│  │ 注册/发现 │ │ mem0风格 │ │ 分层规划  │ │ LLM-as-Judge  │  │
│  │ 声明式定义│ │ 记忆管理 │ │ 长任务拆分│ │ + 规则校验    │  │
│  └──────────┘ └──────────┘ └──────────┘ └────────────────┘  │
│                                                               │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │                  Fault Tolerance Layer                   │ │
│  │  L1: 工具重试(指数退避) → L2: 策略降级 → L3: Checkpoint →│ │
│  │  L4: 降级到人工                                          │ │
│  └─────────────────────────────────────────────────────────┘ │
└──────────────────────────┬───────────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────────┐
│                   数据层 (嵌入式, 零依赖)                       │
│                                                               │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────┐  │
│  │ SQLite (WAL) │  │ ChromaDB     │  │ Local File System  │  │
│  │ 结构化数据    │  │ 向量检索     │  │ 简历文件/缓存       │  │
│  │ + diskcache   │  │ (mem0 后端)  │  │                    │  │
│  └──────────────┘  └──────────────┘  └────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

---

## 2. Agent 核心循环

### 2.1 Plan → Act → Observe → Replan

Agent 的核心不是一次 LLM 调用，而是一个**带自我纠错能力的推理循环**。每一次与用户的交互都经历完整的四阶段循环，直到达到目标或需要用户输入。

#### 2.1.1 Context Assembler（上下文组装器）

每次进入 Plan 阶段前，Assembler 负责搭建完整的推理上下文：

```
Context = SystemPrompt + Memory Context + Working State + Tool Manifest

System Prompt:
  - Agent 角色定义（"你是一位资深简历顾问..."）
  - 行为约束（"不改动事实，仅优化表达"）
  - 输出格式要求

Memory Context (从 ChromaDB 检索):
  - 用户 Profile: 技能栈、教育背景、工作经历、求职方向
  - 用户 Preference: 风格偏好、目标行业、已确认的叙事策略
  - 最近 Feedback: 近期接受/拒绝过哪些建议

Working State (从 SQLite 加载):
  - 当前正在编辑的简历结构化数据
  - 最近的 JD 匹配报告（如果有）
  - 未完成的战略计划（如果是从 Checkpoint 恢复）

Tool Manifest:
  - 当前可用工具的列表、签名、适用场景描述
  - 仅包含当前状态下有意义的工具（如没有 GitHub URL 时不暴露 GitHub 工具）
```

#### 2.1.2 循环状态机

```
                        ┌────────────────────────┐
                        │        START            │
                        │   用户输入 / 定时触发    │
                        └───────────┬────────────┘
                                    │
                                    ▼
                        ┌────────────────────────┐
                        │   CONTEXT ASSEMBLER     │
                        │  组装上下文              │
                        └───────────┬────────────┘
                                    │
                                    ▼
                        ┌────────────────────────┐
                        │        PLAN             │
                        │  ┌──────────────────┐   │
                        │  │ LLM 推理:         │   │
                        │  │ - 用户意图是什么?  │   │
                        │  │ - 当前进展到哪?    │   │
                        │  │ - 下一步做什么?    │   │
                        │  │ - 需要调用哪些工具? │   │
                        │  └──────────────────┘   │
                        └───────────┬────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    │               │               │
                    ▼               ▼               ▼
            ┌──────────┐   ┌──────────────┐  ┌──────────────┐
            │ 需要用户  │   │ 调用工具      │  │ 直接回复      │
            │ 输入      │   │ (单/多工具)   │  │ (简单问答)    │
            └─────┬────┘   └──────┬───────┘  └──────┬───────┘
                  │               │                 │
                  ▼               ▼                 │
            ┌──────────┐   ┌──────────┐            │
            │ 暂停循环  │   │   ACT    │            │
            │ 等待用户  │   │ 执行工具  │            │
            └──────────┘   └─────┬────┘            │
                                 │                 │
                                 ▼                 │
                        ┌──────────┐               │
                        │ OBSERVE  │◀──────────────┘
                        │ ┌───────┐│
                        │ │评估结果││
                        │ │- 成功? ││
                        │ │- 是否达││
                        │ │  成目标││
                        │ │- 需要重││
                        │ │  试?   ││
                        │ └───┬───┘│
                        └─────┼────┘
                              │
              ┌───────────────┼───────────────┐
              │               │               │
              ▼               ▼               ▼
        ┌──────────┐  ┌──────────┐  ┌──────────────┐
        │ 目标达成  │  │ 工具失败  │  │ 需要更多步骤  │
        │ → 结束   │  │ → REPLAN │  │ → 下一轮PLAN │
        └──────────┘  └──────────┘  └──────────────┘
```

#### 2.1.3 Replan 阶段的设计细节

Replan 不是简单地"重试"，而是**分析失败原因后调整策略**：

```
失败场景分类:

1. 工具参数错误
   → 修正参数后重试（不增加重试计数器的"严重度"）

2. 外部服务异常 (API 限流、网络超时)
   → 指数退避重试，最多 3 次
   → 仍然失败 → 降级策略或告知用户

3. 工具返回结果不满足预期
   → 分析是工具选错了，还是前置条件不满足？
   → 工具选错 → 换一个工具
   → 前置条件不满足 → 先调用满足前置条件的工具

4. 达到最大重试次数
   → 标记当前步骤为 BLOCKED
   → 向用户解释原因，请求人工介入
```

### 2.2 推理链示例

以"优化简历中的一段工作经历"为例，展示完整的推理链：

```
用户: "帮我把这段经历改得更专业"

---
Turn 1 - PLAN:
  思考: 用户要优化一段经历。我需要先确认要改哪一段（如果有多个经历），
        然后做 STAR 评估，再提出改写方案。
  计划: [read_current_entry, evaluate_star_completeness]

Turn 1 - ACT:
  → read_current_entry(entry_id=3)
    返回: {content: "负责公司后端服务的开发与维护，使用Python和Django框架",
            company: "某科技公司", period: "2023.03-至今"}
  → evaluate_star_completeness(entry_text)
    返回: {star_score: 1/4, missing: ["Situation", "Task", "Result"],
            issues: ["无量化成果", "仅描述职责未体现个人贡献"]}

Turn 1 - OBSERVE:
  评估: STAR 评分仅 1/4，缺失 S/T/R 三个维度。下一步应该做深度追问。
  目标: 未达成，需要更多信息。

---
Turn 2 - PLAN:
  思考: 需要追问缺失的 STAR 维度。按优先级：先问 Result（量化成果）
        再问 Situation（业务背景），最后问 Task（具体任务）。
  计划: [ask_clarifying_question 优先级最高的缺失维度]

Turn 2 - ACT:
  → ask_clarifying_question(question="你提到的'后端服务的开发与维护'，有没有可以量化的成果？
        比如服务了多少用户、接口 QPS 是多少、有没有做过什么性能优化？")

--- (等待用户回答)

用户: "服务了大概 50 万用户，我把接口响应时间从 500ms 优化到了 100ms"

---
Turn 3 - PLAN:
  思考: 用户提供了量化数据。现在可以尝试生成优化后的条目。
  计划: [optimize_entry(原始+新信息)]

Turn 3 - ACT:
  → optimize_entry(original, new_info)
    返回: {optimized_text: "主导公司核心后端服务的架构升级，支撑 50 万+ 日活用户。
           通过数据库索引优化与查询重构，将核心接口响应时间从 500ms 降至 100ms（P99），提升 80%。"}

Turn 3 - OBSERVE:
  评估: 改写完成。需要做质量检查。

---
Turn 4 - PLAN:
  计划: [evaluate_quality(optimized_text)]

Turn 4 - ACT:
  → evaluate_quality(optimized_text)
    返回: {score: 8.5/10, checks: {star: "pass", verb_strength: "pass",
           quantitative: "pass", length: "pass"}}

Turn 4 - OBSERVE:
  评估: 质量评分 8.5/10，通过。可以展示给用户确认。
  目标: 达成。
```

---

## 3. 工具系统设计

### 3.1 设计目标

在单 Agent 架构中，工具定义了 Agent 的能力边界。工具设计遵循三个原则：

1. **自描述**：Agent 仅通过工具的声明式元数据即可判断何时、如何使用它
2. **可降级**：每个工具定义自己的失败模式和降级策略
3. **最小权限**：Agent 只能调用当前任务必要的工具子集（动态 Tool Manifest）

### 3.2 工具基类设计

```python
# agent/tools/base.py

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class ToolCategory(Enum):
    RESUME = "resume"
    JD = "jd"
    GITHUB = "github"
    QUALITY = "quality"
    MEMORY = "memory"


class Difficulty(Enum):
    LIGHT = "light"      # < 5s, 纯计算
    MEDIUM = "medium"    # 5-30s, 涉及外部 API
    HEAVY = "heavy"      # 30s+, 如 GitHub 仓库分析


@dataclass
class ToolMetadata:
    """工具的声明式元数据 —— Agent 通过读取这些信息做调用决策"""
    name: str
    category: ToolCategory
    description: str                              # 一句话描述
    usage_guide: str                              # Agent 阅读的使用指南（何时用、何时不用）
    preconditions: list[str] = field(default_factory=list)
    estimated_time: Difficulty = Difficulty.LIGHT
    is_idempotent: bool = True
    requires_user_confirmation: bool = False      # 是否需要在调用前请求用户确认


@dataclass
class ToolResult:
    success: bool
    data: Optional[Any] = None
    error_code: Optional[str] = None   # RATE_LIMITED, PARAM_ERROR, EXTERNAL_ERROR, etc.
    error_message: Optional[str] = None
    is_retryable: bool = False
    fallback_suggestion: Optional[str] = None  # 给 Agent 的降级建议


class BaseTool(ABC):
    """Agent 工具基类"""

    @property
    @abstractmethod
    def metadata(self) -> ToolMetadata:
        ...

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        ...

    def to_openai_schema(self) -> dict:
        """生成 OpenAI function-calling 兼容的 schema"""
        pass

    def to_llm_description(self) -> str:
        """生成给 LLM 阅读的工具描述文本"""
        meta = self.metadata
        return f"""Tool: {meta.name}
Category: {meta.category.value}
When to use: {meta.usage_guide}
Preconditions: {', '.join(meta.preconditions) or 'none'}
Estimated time: {meta.estimated_time.value}
Idempotent: {meta.is_idempotent}"""
```

### 3.3 工具注册表

```python
# agent/tools/registry.py

class ToolRegistry:
    """统一的工具注册、发现与动态筛选"""

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool):
        self._tools[tool.metadata.name] = tool

    def get_manifest(self, context: dict) -> list[BaseTool]:
        """根据当前上下文，返回可用的工具子集

        例如：
        - 用户没有上传简历 → 不暴露简历解析以外的简历工具
        - 用户没有提供 GitHub URL → 不暴露 GitHub 工具
        - 用户没有确认脱敏策略 → 不暴露需要发送敏感信息的工具
        """
        available = []
        for tool in self._tools.values():
            if self._is_applicable(tool, context):
                available.append(tool)
        return available

    def get_llm_manifest_text(self, context: dict) -> str:
        """生成当前可用工具的文本描述，注入到 System Prompt 中"""
        tools = self.get_manifest(context)
        return "\n\n".join(t.to_llm_description() for t in tools)
```

### 3.4 工具清单

#### Resume Tools（简历工具）

| 工具名 | 分类 | 功能 | 耗时 | 幂等 |
|--------|------|------|------|------|
| `parse_resume_file` | resume | 多策略解析上传的简历文件（PDF/DOCX/MD）为结构化数据 | medium | 是 |
| `read_resume_section` | resume | 读取当前简历的指定区块（教育/工作/项目/技能） | light | 是 |
| `update_resume_entry` | resume | 修改某条经历的内容 | light | 否 |
| `add_resume_entry` | resume | 新增一条经历 | light | 否 |
| `delete_resume_entry` | resume | 删除一条经历（需用户确认） | light | 否 |
| `create_resume_draft` | resume | 基于记忆中的信息，创建简历初稿 | medium | 否 |
| `export_resume` | resume | 导出为 PDF/Markdown | medium | 是 |

#### JD Tools（岗位匹配工具）

| 工具名 | 分类 | 功能 | 耗时 | 幂等 |
|--------|------|------|------|------|
| `parse_jd_text` | jd | 结构化解析 JD 文本 | light | 是 |
| `match_jd_to_resume` | jd | 逐条匹配 JD 要求与简历内容，生成匹配报告 | medium | 是 |
| `analyze_keyword_coverage` | jd | ATS 关键词覆盖率分析 | light | 是 |
| `detect_jd_signals` | jd | 识别 JD 中的隐性要求信号 | light | 是 |

#### GitHub Tools（开源分析工具）

| 工具名 | 分类 | 功能 | 耗时 | 幂等 |
|--------|------|------|------|------|
| `fetch_repo_metadata` | github | 获取仓库 Stars/语言/描述/最近活动 | light | 是 |
| `analyze_repo_structure` | github | 分析目录结构和模块划分 | medium | 是 |
| `analyze_repo_dependencies` | github | 依赖分析（过时/漏洞） | medium | 否 |
| `scan_issues_for_opportunities` | github | 从 Issue 列表筛选可切入的二开点 | medium | 否 |
| `generate_dev_suggestions` | github | 结合用户方向，生成多方向二开建议 | heavy | 否 |
| `compose_resume_entry_from_github` | github | 将二开方案编为 STAR 简历条目 | light | 否 |

#### Quality Tools（质量评估工具）

| 工具名 | 分类 | 功能 | 耗时 | 幂等 |
|--------|------|------|------|------|
| `evaluate_star_completeness` | quality | 评估一条经历的 STAR 完整性（1-4分） | light | 是 |
| `evaluate_entry_quality` | quality | LLM-as-Judge 综合质量评分（输出 0-10 分 + 分维评估） | medium | 是 |
| `check_verb_strength` | quality | 规则检测弱动词（负责/参与/协助） | light | 是 |
| `check_sensitive_info` | quality | 检测简历中的敏感信息（手机号/身份证/薪资） | light | 是 |
| `run_full_quality_audit` | quality | 全量质量审查，生成优先级改进清单 | medium | 否 |

#### Memory Tools（记忆工具）

| 工具名 | 分类 | 功能 | 耗时 | 幂等 |
|--------|------|------|------|------|
| `search_memory` | memory | 语义检索相关记忆 | light | 是 |
| `get_user_profile` | memory | 获取用户完整 Profile | light | 是 |
| `get_user_preferences` | memory | 获取用户偏好 | light | 是 |
| `forget_memory` | memory | 用户主动删除某条记忆 | light | 否 |

### 3.5 工具调用容错

```
工具调用流程:

  Agent 决定调用 tool_xxx(param=value)
         │
         ▼
  ┌─────────────────┐
  │  Pre-check      │  ← 验证前置条件
  │  (前置条件校验)  │
  └────────┬────────┘
           │ pass
           ▼
  ┌─────────────────┐
  │  Execute        │
  │  最多重试 3 次    │  ← 指数退避: 1s → 2s → 4s
  └────────┬────────┘
           │ fail after retries
           ▼
  ┌─────────────────┐
  │  Degrade        │  ← 尝试降级策略 (如用缓存、简化分析)
  └────────┬────────┘
           │ also fails
           ▼
  ┌─────────────────┐
  │  Return Error   │  ← 返回结构化错误给 Agent
  │  + Suggestion   │     Agent 在 Replan 阶段据此调整
  └─────────────────┘
```

---

## 4. Memory 系统设计

### 4.1 设计目标（参考 mem0）

本项目的记忆系统参考 [mem0](https://github.com/mem0ai/mem0) 的设计哲学：

- **记忆是结构化事实，不是对话日志**：从对话中自动提取事实（技能、偏好、经历），而非存储原始文本
- **记忆自动演化**：新增 → 冲突检测 → 合并/更新 → 遗忘不重要的
- **语义检索驱动**：基于 ChromaDB 做向量相似度检索
- **分层记忆类型**：核心事实 / 偏好 / 临时上下文 / 反馈

### 4.2 记忆类型定义

```
┌─────────────────────────────────────────────────────────────┐
│                    记忆类型与特性                             │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  🔴 User Profile (核心事实)                            │  │
│  │                                                       │  │
│  │  存储内容:                                             │  │
│  │    - 技能栈: [{"skill": "Python", "years": 3,         │  │
│  │                "level": "advanced"}, ...]              │  │
│  │    - 教育: {学校, 专业, 学历, 入学-毕业时间}           │  │
│  │    - 工作经历: [{公司, 岗位, 起止时间, 关键成果}]      │  │
│  │    - 求职方向: {岗位, 行业, 技术栈偏好, 薪资期望}      │  │
│  │    - 个人项目: [{名称, 技术栈, 链接, 描述}]            │  │
│  │                                                       │  │
│  │  特性:                                                 │  │
│  │    - 高持久度 (除非用户主动修改，否则长期保留)          │  │
│  │    - 强一致性 (新增事实与已有事实冲突时→请求用户确认)    │  │
│  │    - 版本化 (Profile 的每次变更可追溯)                  │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  🟡 Preference (用户偏好)                              │  │
│  │                                                       │  │
│  │  存储内容:                                             │  │
│  │    - "偏好简洁风格，不喜欢过度包装"                     │  │
│  │    - "英文简历统一使用过去时"                           │  │
│  │    - "不投外包岗位"                                     │  │
│  │    - "对 ATS 兼容性要求高"                              │  │
│  │                                                       │  │
│  │  特性:                                                 │  │
│  │    - 中持久度                                          │  │
│  │    - 自动合并: 多次表达相似偏好 → 提升置信度            │  │
│  │    - 动态权重: 近期偏好权重高于历史偏好                  │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  🟢 Session Context (会话上下文)                        │  │
│  │                                                       │  │
│  │  存储内容:                                             │  │
│  │    - 当前编辑的简历版本 ID                              │  │
│  │    - 最近一次 JD 匹配结果                               │  │
│  │    - 当前会话的活跃 Intent                              │  │
│  │    - Strategic Plan 执行进度                            │  │
│  │                                                       │  │
│  │  特性:                                                 │  │
│  │    - 低持久度 (会话结束后部分提升为 Profile/Preference)   │  │
│  │    - 与 Agent Checkpoint 协同工作                       │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  🔵 Feedback History (反馈信号)                         │  │
│  │                                                       │  │
│  │  存储内容:                                             │  │
│  │    - 接受/拒绝了哪些改写建议                            │  │
│  │    - 哪种表达风格被接受率更高                            │  │
│  │    - "上次你说不喜欢过度包装，这次我调整了语气"          │  │
│  │                                                       │  │
│  │  特性:                                                 │  │
│  │    - 用于调整 Agent 的策略偏好                          │  │
│  │    - 聚合统计 (不是单条记忆，而是趋势分析)               │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### 4.3 Memory Lifecycle

```
┌────────────────────────────────────────────────────────────────┐
│                      Memory Lifecycle                           │
│                                                                │
│  ┌──────────────────┐                                          │
│  │  Conversation     │  用户与 Agent 的每一轮对话               │
│  │  Turn             │                                         │
│  └────────┬─────────┘                                          │
│           │                                                     │
│           ▼                                                     │
│  ┌──────────────────┐                                          │
│  │  Memory Extractor │  LLM 从对话中提取候选记忆                 │
│  │  (LLM-based)      │  输出格式: [{type, key, value,           │
│  │                   │             confidence, evidence}]       │
│  └────────┬─────────┘                                          │
│           │                                                     │
│           ▼                                                     │
│  ┌──────────────────┐                                          │
│  │  Dedup Check     │  向量相似度 > 0.9 视为同一记忆             │
│  │  (ChromaDB)      │  ┌──────────┐  ┌──────────┐             │
│  │                   │  │ 相似度高  │  │ 全新记忆  │             │
│  └────────┬──────────┘  └─────┬────┘  └─────┬────┘             │
│           │                   │              │                  │
│           │                   ▼              ▼                  │
│           │           ┌──────────────┐ ┌──────────────┐        │
│           │           │ Merge/Update │ │ Insert New   │        │
│           │           │              │ │              │        │
│           │           │ - 技能年限   │ │ 新增记忆      │        │
│           │           │   冲突检测   │ │ 写入 ChromaDB │        │
│           │           │ - 偏好增强   │ │ + SQLite      │        │
│           │           └──────┬───────┘ └──────┬───────┘        │
│           │                  │                │                 │
│           │                  └────────┬───────┘                 │
│           │                           │                         │
│           ▼                           ▼                         │
│  ┌──────────────────────────────────────────┐                  │
│  │  Memory Consolidator (定期/事件触发)      │                  │
│  │                                          │                  │
│  │  - 合并同类型的高相似度记忆               │                  │
│  │  - 标记长期未访问的记忆为"低活跃度"      │                  │
│  │  - 冲突解决: 新旧事实矛盾时标记待确认     │                  │
│  │  - 淘汰: 低活跃度 + 低重要性 → 自动归档   │                  │
│  └──────────────────────────────────────────┘                  │
│                                                                 │
│  ┌──────────────────────────────────────────┐                  │
│  │  Memory Retriever (每次 Agent 推理前)     │                  │
│  │                                          │                  │
│  │  query = 当前对话意图 + Working State     │                  │
│  │  → ChromaDB 语义检索 Top-K               │                  │
│  │  → 按 type 分类注入 Context              │                  │
│  └──────────────────────────────────────────┘                  │
└────────────────────────────────────────────────────────────────┘
```

### 4.4 存储方案

| 数据 | 存储引擎 | Schema |
|------|---------|--------|
| 记忆的结构化元数据 (type, key, timestamps, metadata) | SQLite | `memories` 表 |
| 记忆的向量嵌入 | ChromaDB | `resume_agent_memories` collection |
| 记忆的演化历史 (merge/update 日志) | SQLite | `memory_changelog` 表 |
| 用户 Profile 结构化数据 | SQLite | `user_profiles` 表 + JSON 字段 |

### 4.5 与 mem0 API 的对应

| mem0 API | 本项目实现 | 说明 |
|----------|----------|------|
| `mem0.add(messages, user_id)` | `MemoryExtractor.extract(turn)` + `MemoryStore.add()` | 从对话中自动提取事实写入 |
| `mem0.search(query, user_id)` | `MemoryRetriever.search(embedding, filters)` | 语义检索 + 元数据过滤 |
| `mem0.update(memory_id, data)` | `MemoryStore.merge_or_update()` | 冲突检测后合并更新 |
| `mem0.delete(memory_id)` | `MemoryStore.soft_delete()` | 标记删除（软删除，可恢复） |
| `mem0.get_all(user_id)` | `MemoryStore.get_all_for_user(user_id)` | 导出全部记忆（用于数据迁移/擦除） |
| `mem0.delete_all(user_id)` | `MemoryStore.purge_user(user_id)` | 用户数据完全擦除 |
| Memory Types | `metadata.type` 字段 | user_profile / preference / session / feedback |

---

## 5. 长时序规划与容错

### 5.1 分层规划系统

单 Agent 处理复杂任务时，采用**战略-战术双层规划**：

#### 战略层（对用户可见）

```
Strategic Plan = [Milestone_1, Milestone_2, ..., Milestone_N]

每个 Milestone:
  - id: str
  - description: "了解用户教育背景"
  - depends_on: [前置 Milestone ID]
  - status: PENDING | IN_PROGRESS | COMPLETED | SKIPPED | BLOCKED
  - estimated_turns: 预估需要几轮对话
  - user_visible: 是否在 UI 展示进度条

示例 —— "从零创建一份后端开发简历":

  M1: 了解教育背景          [COMPLETED]
  M2: 了解求职方向          [COMPLETED]
  M3: 挖掘工作/项目经历    [IN_PROGRESS]  ← 当前
  M4: 组装简历草稿          [PENDING]
  M5: 逐段审查优化          [PENDING]
  M6: 导出                  [PENDING]
```

用户可以说"跳过 M3，先写教育那部分"——Agent 更新 StrategicPlan 中的依赖关系和执行顺序。

#### 战术层（Agent 内部）

每个 Milestone 展开为一组具体的 **Plan-Act-Observe 循环**：

```
M3: 挖掘工作/项目经历 的战术展开:

  3.1 search_memory("项目经历") → 获取已有记忆
  3.2 如果记忆中有未详细挖掘的项目 → 选择一个追问
  3.3 STAR 追问 (可能 2-3 轮对话)
  3.4 evaluate_star_completeness → 达标 → 进入下一个项目
  3.5 所有项目挖掘完毕 → 标记 M3 COMPLETED
```

### 5.2 Checkpoint 机制

```
Checkpoint 数据结构:

{
  "checkpoint_id": "uuid",
  "session_id": "uuid",
  "user_id": "uuid",
  "strategic_plan": {...},          # 当前战略计划快照
  "current_milestone": "M3",
  "tactical_progress": {            # 当前 Milestone 内的战术进度
    "milestone_id": "M3",
    "completed_sub_steps": [3.1, 3.2],
    "current_sub_step": 3.3,
    "pending_questions": [...]       # 还未问用户的追问
  },
  "working_state_hash": "sha256...", # 简历数据的 hash
  "tool_call_history": [...],        # 本轮已执行的工具调用
  "memory_snapshot_ids": [...],      # 本轮的 Memory ID 列表（用于回滚）
  "created_at": "ISO8601",
  "updated_at": "ISO8601"
}
```

**恢复流程**：

```
用户重新打开对话
      │
      ▼
Agent 加载最近的 Checkpoint
      │
      ├─ 验证 Working State hash 是否匹配
      │   - 匹配 → 从 Checkpoint 恢复，告知用户"我们上次进行到..."
      │   - 不匹配 → 数据已在别处被修改，提示用户选择保留哪个版本
      │
      ├─ 重放未完成的工具调用（幂等安全）
      │
      └─ 恢复对话，继续下一轮 Plan
```

### 5.3 容错策略分层

```
┌─────────────────────────────────────────────────────────────┐
│                    Fault Tolerance Layers                    │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  L1 — 工具级重试 (Retry with Backoff)                  │  │
│  │                                                       │  │
│  │  触发条件: 网络超时、API限流、临时服务不可用            │  │
│  │  策略: 指数退避 (1s → 2s → 4s)，最多 3 次              │  │
│  │  幂等保证: 每个写操作携带 idempotency_key              │  │
│  │  示例: GitHub API 429 → 等 60s 后重试                   │  │
│  └───────────────────────────────────────────────────────┘  │
│                          ↓ 仍失败                            │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  L2 — 策略降级 (Graceful Degradation)                  │  │
│  │                                                       │  │
│  │  触发条件: L1 重试全部失败、工具返回不可重试错误         │  │
│  │  策略: 使用降级路径                                    │  │
│  │  示例:                                                │  │
│  │    - GitHub API 限流 → 使用本地缓存的仓库数据           │  │
│  │    - Repo 过大克隆失败 → 仅分析 README + 依赖文件       │  │
│  │    - LLM 超时 → 切换更快的模型 (Opus → Haiku)          │  │
│  │    - PDF 解析失败 → 请用户粘贴纯文本                    │  │
│  └───────────────────────────────────────────────────────┘  │
│                          ↓ 仍失败                            │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  L3 — Checkpoint 恢复 (State Recovery)                │  │
│  │                                                       │  │
│  │  触发条件: Agent 进程崩溃、LLM 返回不可解析的输出       │  │
│  │  策略: 回退到最近的 Checkpoint，丢弃失败步骤的副作用     │  │
│  │  底层依赖: SQLite WAL + 事务保证数据一致性              │  │
│  └───────────────────────────────────────────────────────┘  │
│                          ↓ 仍失败                            │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  L4 — 优雅降级到人工 (Human Handoff)                   │  │
│  │                                                       │  │
│  │  触发条件: 连续 3 个 Checkpoint 在该步骤失败            │  │
│  │  策略:                                                │  │
│  │    - 标记当前 Milestone 为 BLOCKED                     │  │
│  │    - 向用户解释失败原因                                │  │
│  │    - 提供手动操作入口 (直接编辑字段 / 跳过此步骤)       │  │
│  │  示例: "我无法自动分析这个 GitHub 仓库的架构，           │  │
│  │          你可以手动描述项目结构，我帮你整理成经历"      │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## 6. 技术栈选型

### 6.1 选型原则

面向用户较少（个人使用/小团队），优先考虑：
- **零外部依赖部署**：不需要 Docker、不需要外部数据库服务
- **代码清晰度优先于分布式能力**
- **按量选型**：不为了简历而堆砌重型基础设施

### 6.2 技术栈

| 层 | 选型 | 版本 | 选型理由 |
|---|------|------|---------|
| **Agent 编排** | LangGraph | ≥0.2 | 状态图天然适配 Plan-Act-Observe 循环；内置 Checkpoint；支持 Streaming |
| **LLM Provider** | Anthropic (Claude API) | - | 以 Claude 为主模型；预留 OpenAI 兼容接口 |
| **后端框架** | FastAPI | ≥0.110 | 异步原生；SSE 流式输出开箱即用；Pydantic v2 类型系统 |
| **主数据库** | SQLite (WAL 模式) | ≥3.40 | 零部署、单文件；WAL 模式支持读写并发；数据量可控（个人使用 ≤100MB） |
| **向量数据库** | ChromaDB (嵌入式) | ≥0.5 | mem0 推荐后端之一；嵌入式模式零部署；支持元数据过滤 + 向量检索 |
| **磁盘缓存** | diskcache | ≥5.6 | 基于 SQLite 的持久化缓存；替代 Redis，无需额外进程 |
| **前端框架** | Next.js 14 (App Router) | ≥14 | 展示全栈能力；SSE 消费端；Tailwind CSS 快速 UI |
| **PDF 生成** | WeasyPrint / Typst | - | 服务端 PDF 渲染；Typst 作为 LaTeX 的现代替代品（简历模板） |
| **PDF 解析** | pymupdf (fitz) | ≥1.23 | 文本提取 + 布局分析（双栏检测）；marker 作为补充 |
| **代码分析** | 自研 + tree-sitter | - | GitHub 仓库分析：tree-sitter 做 AST 级语言识别；不执行用户代码 |
| **Prompt 管理** | YAML 文件 | - | `prompts/` 目录下按模块组织，版本号在文件名中 |
| **可观测性** | 自研 JSON 日志 | - | 记录推理链、工具调用、耗时、用户反馈；可选对接 LangFuse |

### 6.3 不选用的技术及理由

| 不选用 | 理由 |
|--------|------|
| PostgreSQL / pgvector | 用户量少不需要；SQLite + ChromaDB 满足需求，且零部署 |
| Redis | diskcache 满足缓存需求，减少外部依赖 |
| Docker / K8s | 单人使用不需要；`pip install` + `npm install` 即可启动 |
| CrewAI / AutoGen | 多 Agent 框架，与本项目的单 Agent 深度定位不符 |
| Pinecone / Weaviate | 外部向量数据库服务，需要网络连接和额外费用；ChromaDB 嵌入式足够 |
| S3 / MinIO | 用户少，本地文件系统存储简历文件即可 |

### 6.4 Python 依赖

```
# 核心
langgraph>=0.2.0
anthropic>=0.30.0
fastapi>=0.110.0
pydantic>=2.0
uvicorn

# 数据
chromadb>=0.5.0        # 向量数据库
diskcache>=5.6         # 持久化缓存
aiosqlite               # 异步 SQLite

# 文档处理
pymupdf>=1.23.0        # PDF 解析
python-docx>=1.1.0     # DOCX 解析
marker-pdf              # 高质量 PDF→Markdown (备用)

# 代码分析
tree-sitter             # AST 级语言识别

# 工具
pyyaml                  # Prompt 管理
httpx                   # 异步 HTTP (GitHub API)
```

---

## 7. 关键模块设计

### 7.1 大纲

本章覆盖四个最具架构深度的模块的详细设计：
- 简历解析 Agent（多策略管道）
- JD-简历匹配（两阶段检索+精排）
- GitHub 分析 Agent（沙箱化多阶段分析 + 缓存策略）
- 质量评估框架（规则层 + LLM 层双层架构）

### 7.2 简历解析策略管道

```
上传文件 → 文件类型检测
               │
        ┌──────┼──────┐
        ▼      ▼      ▼
      PDF    DOCX   Markdown
        │      │      │
        ▼      ▼      ▼
   ╔═══════════════════════╗
   ║  多策略解析管道        ║  ← Chain of Responsibility 模式
   ║                       ║
   ║  策略1: 文本提取       ║  ← pymupdf / python-docx
   ║     ↓ 失败            ║
   ║  策略2: OCR 提取       ║  ← 扫描件 fallback (pytesseract)
   ║     ↓ 文本质量差       ║
   ║  策略3: 直接 LLM 理解  ║  ← 将原文件截图传给多模态模型
   ╚═══════════════════════╝
               │
               ▼
         LLM 结构化提纯
        (Entity Extraction)
        输出: Pydantic Resume Schema
               │
               ▼
         Schema 校验 + 修复
        (自动纠正日期格式、字段类型)
               │
               ▼
         可视化预览 → 用户确认/校正
```

**设计要点**：
- 不是把全文丢给 LLM，而是先用规则提取候选字段（日期、公司名、学校名），再让 LLM 做语义消歧。这样可以**控制成本**。
- LLM 输出强类型约束（Pydantic），不是自由 JSON。Schema 校验层把不合法字段自动修复（如日期格式），修复不了的才上报。
- 双栏排版检测：pymupdf 可以读取每个文本块的坐标，通过 X 坐标聚类判断是否双栏，自动线性化读取顺序。

### 7.3 JD-简历匹配引擎

```
Step 1 — JD 结构化解析 (规则 + LLM)
─────────────────────────────────────
JD 文本 → 正则提取显式条件 (年限/学历) → LLM 提取隐式要求 → Pydantic 输出

输出:
{
  "hard_requirements": [
    {"criterion": "3年+ Python开发", "type": "must_have"},
    {"criterion": "本科及以上学历", "type": "must_have"}
  ],
  "nice_to_have": [
    {"criterion": "熟悉分布式系统", "type": "plus"},
    {"criterion": "有开源贡献经验", "type": "plus"}
  ],
  "soft_signals": [
    {"signal": "快速迭代", "interpretation": "可能需要应对频繁的需求变更"}
  ]
}

Step 2 — 语义匹配 (向量召回 + LLM 精排)
────────────────────────────────────────
对每个 JD 要求:
  → 用向量相似度从简历中召回 Top-3 相关段落
  → LLM 逐段打分: {match_level: "✅"|"⚠️"|"❌", evidence: "...", suggestion: "..."}

Step 3 — 生成匹配报告
─────────────────────
汇总 → 结构化报告 (含匹配度百分比 + 逐条建议 + 隐线信号解读)
```

**设计要点**：
- **不是全文拼接**：如果用全文 `JD(1000字) + 简历(2000字) → LLM`，Token 费用高（约 5K input/token），而且长文本容易丢失对应关系。
- **先召回再精排**：每个 JD 要求只和简历中最相关的 3 个段落做匹配，每次 LLM 调用约 500 tokens，全量匹配约 15-20 次调用，总消耗约 10K tokens，降低约 60%。
- 召回用 ChromaDB（简历已分段存入），精排用 LLM。

### 7.4 GitHub 分析 Agent

这是整个项目中最能体现 **单 Agent 推理深度** 的模块。

```
用户提供 GitHub URL + 求职方向
              │
              ▼
    ╔══════════════════════════════════╗
    ║        阶段 1: 快速概览           ║  (~5s, Agent 首先调用)
    ║                                 ║
    ║  fetch_repo_metadata(url)       ║  ← GitHub API: Stars, 语言, 描述
    ║  返回: {语言, Stars, 最近活动...} ║
    ║                                 ║
    ║  Agent 推理:                     ║
    ║  "这个项目是 TypeScript + React, ║
    ║   Stars 78k, 最近活跃。"         ║
    ║  "符合用户的前端方向。继续深度分析" ║
    ╚══════════════┬═══════════════════╝
                   │
                   ▼
    ╔══════════════════════════════════╗
    ║        阶段 2: 结构分析           ║  (~10s)
    ║                                 ║
    ║  analyze_repo_structure(url)    ║  ← 浅克隆 + 目录分析
    ║  返回: {目录树, 模块关系图}      ║
    ║                                 ║
    ║  Agent 推理:                     ║
    ║  "核心模块是 src/element/ 和     ║
    ║   src/renderer/, 耦合度较高"     ║
    ╚══════════════┬═══════════════════╝
                   │
                   ▼
    ╔══════════════════════════════════╗
    ║        阶段 3: 深度分析           ║  (~30s, 可并行)
    ║                                 ║
    ║  analyze_dependencies()  ──┐    ║
    ║  scan_issues()           ──┼──  ║  三个分析可并行执行
    ║  identify_code_hotspots() ──┘    ║
    ║                                 ║
    ║  Agent 综合推理:                  ║
    ║  "依赖存在 3 个过时包,           ║
    ║   Issue #2341 提到了多人协作需求, ║
    ║   renderer 模块最近提交最密集..." ║
    ╚══════════════┬═══════════════════╝
                   │
                   ▼
    ╔══════════════════════════════════╗
    ║        阶段 4: 方向生成           ║  (~20s)
    ║                                 ║
    ║  generate_dev_suggestions(      ║
    ║    analysis_results,            ║
    ║    user_career_direction,       ║  ← 从 Memory 检索
    ║    user_skill_level             ║
    ║  )                              ║
    ║  返回: [{方向, 难度, 工时,       ║
    ║          技术价值, 求职价值}]     ║
    ║                                 ║
    ║  Agent 推理:                     ║
    ║  "生成了 5 个方向。方向 1 (CRDT  ║
    ║   集成) 与用户的文档协作方向高度  ║
    ║   匹配，推荐作为首选。"           ║
    ╚══════════════┬═══════════════════╝
                   │
                   ▼
    ╔══════════════════════════════════╗
    ║        阶段 5: 简历条目生成       ║  (~10s)
    ║                                 ║
    ║  compose_resume_entry(          ║
    ║    selected_direction,          ║
    ║    repo_context                 ║
    ║  )                              ║
    ║  返回: STAR 格式的简历条目       ║
    ╚══════════════════════════════════╝
```

**设计要点**：

1. **Progressive Disclosure**：不是一次性跑完全部分析再给反馈，而是逐步深入。用户在第 1 阶段就能看到初步结果，降低感知延迟。
2. **阶段内并行**：阶段 3 的三个分析（依赖/Issue/代码热点）可以并行执行，因为互相独立。
3. **缓存策略**：每个阶段的结果按 `(repo_url, commit_sha)` 做键缓存到 diskcache。用户重复分析同一仓库时秒级返回。
4. **沙箱隔离**：Clone 的代码放在临时目录，分析完成后自动清理。分析过程限制文件读取范围（只读源码目录，不读 `.env` / 密钥文件）。不执行任何 downloaded code。
5. **Agent 自主决策**：Agent 在每阶段结束后自己评估"分析是否足够"——不够就继续下一阶段，够了就跳到阶段 4。不是写死的 5 步全跑。

### 7.5 质量评估框架

双层架构设计：**规则层（毫秒级，本地） + LLM 层（秒级，远程）**。

```
                   ┌──────────────────────────────┐
                   │      Quality Evaluation       │
                   └──────────────┬───────────────┘
                                  │
          ┌───────────────────────┼───────────────────────┐
          ▼                       ▼                       ▼
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│  Rule-based       │  │  LLM-as-Judge    │  │  ATS Simulator   │
│  (本地, ms级)     │  │  (远程, s级)      │  │  (本地, ms级)     │
│                   │  │                  │  │                  │
│  □ 弱动词检测     │  │  □ STAR 完整性   │  │  □ 关键词提取    │
│  □ 敏感信息扫描   │  │  □ 量化数据密度  │  │  □ 字段检测      │
│  □ 页码检查       │  │  □ 行业术语准确  │  │  □ 表格/图片     │
│  □ 中英文格式     │  │  □ 表达简洁度    │  │    干扰评估      │
│  □ 日期一致性     │  │  □ 叙事逻辑性   │  │                  │
│  □ 技术栈大小写   │  │                  │  │  □ 关键词覆盖率  │
│                   │  │  输出:           │  │                  │
│  输出:            │  │  {              │  │  输出:           │
│  {                │  │    score: 8.2,  │  │  {               │
│    violations: [  │  │    dimensions:{ │  │    parsable: ✅  │
│      {type,       │  │      star: 7,   │  │    fields: [     │
│       location,   │  │      quant: 9,  │  │      name: ✅,   │
│       suggestion} │  │      ...        │  │      phone: ✅,  │
│    ]              │  │    },           │  │      email: ✅,  │
│  }                │  │    suggestions  │  │      education:✅ │
│                   │  │  }              │  │    ]             │
└──────────────────┘  └──────────────────┘  │  }             │
                                             └──────────────────┘
          │                       │                       │
          └───────────────────────┼───────────────────────┘
                                  │
                                  ▼
                   ┌──────────────────────────────┐
                   │       Quality Report          │
                   │                              │
                   │  综合评分: 规则结果 × 0.4     │
                   │          + LLM评估 × 0.5     │
                   │          + ATS检测 × 0.1     │
                   │                              │
                   │  优先级排序的改进清单          │
                   │  (致命 > 严重 > 建议)         │
                   └──────────────────────────────┘
```

**设计要点**：

- **成本控制**：规则层筛选掉 80% 的低级问题后，LLM 只投入剩余 20% 需要语义理解的高价值评估任务。
- **评估结果可复现**：同样的简历 + 同样的评估配置 → 相同的分数（LLM-as-Judge 需设置 temperature=0）。
- **可作为回归测试**：将一批简历 + JD 作为测试用例，每次修改 Prompt 或 Agent 逻辑后跑一次评估，看质量分数是否有退化。

---

## 8. 项目目录结构

```
resume-agent/
│
├── agent/                              # Agent 核心
│   ├── __init__.py
│   ├── loop.py                         # 主循环: Plan → Act → Observe → Replan
│   ├── planner.py                      # 分层规划: Strategic + Tactical
│   ├── context.py                      # Context Assembler
│   ├── checkpoint.py                   # Checkpoint 管理
│   │
│   ├── tools/                          # 工具系统
│   │   ├── __init__.py
│   │   ├── base.py                     # BaseTool + ToolMetadata + ToolResult
│   │   ├── registry.py                 # ToolRegistry (注册、动态发现、权限控制)
│   │   ├── resume_tools.py             # 简历工具集
│   │   ├── jd_tools.py                 # JD 工具集
│   │   ├── github_tools.py             # GitHub 分析工具集
│   │   ├── quality_tools.py            # 质量评估工具集
│   │   └── memory_tools.py             # 记忆工具集 (search/store/forget)
│   │
│   └── memory/                         # mem0 风格记忆系统
│       ├── __init__.py
│       ├── store.py                    # MemoryStore (ChromaDB + SQLite)
│       ├── extractor.py                # MemoryExtractor (LLM-based 事实提取)
│       ├── retriever.py                # MemoryRetriever (语义检索 + 过滤)
│       ├── consolidator.py             # MemoryConsolidator (合并/更新/遗忘)
│       └── models.py                   # Memory 数据模型
│
├── core/                               # 核心业务逻辑 (agent-agnostic)
│   ├── resume/                         # 简历模型与操作
│   │   ├── __init__.py
│   │   ├── schema.py                   # Pydantic 结构化简历模型
│   │   ├── parser.py                   # 多策略简历解析管道
│   │   ├── sanitizer.py                # 敏感信息脱敏
│   │   └── exporter.py                 # PDF/Markdown 导出
│   │
│   ├── jd/                             # JD 处理
│   │   ├── __init__.py
│   │   ├── parser.py                   # JD 结构化解析
│   │   ├── matcher.py                  # 两阶段匹配引擎
│   │   └── signal_detector.py          # JD 隐性信号识别
│   │
│   ├── github/                         # GitHub 分析 (沙箱化)
│   │   ├── __init__.py
│   │   ├── analyzer.py                 # 多阶段分析编排
│   │   ├── cloner.py                   # 浅克隆 + 沙箱管理
│   │   ├── structure.py                # 目录结构/模块分析
│   │   ├── dependencies.py             # 依赖分析
│   │   ├── issues.py                   # Issue 筛选与分级
│   │   └── suggestion.py               # 二开方向生成
│   │
│   └── evaluation/                     # 质量评估框架
│       ├── __init__.py
│       ├── rules.py                    # 规则层检查 (本地)
│       ├── llm_judge.py                # LLM-as-Judge (远程)
│       ├── ats_simulator.py            # ATS 模拟解析
│       └── scorer.py                   # 加权综合评分
│
├── prompts/                            # Prompt 版本管理
│   ├── agent/
│   │   ├── system_v1.yaml
│   │   ├── planner_v1.yaml
│   │   └── memory_extractor_v1.yaml
│   ├── evaluation/
│   │   └── llm_judge_v1.yaml
│   └── github/
│       ├── suggestion_v1.yaml
│       └── resume_entry_v1.yaml
│
├── api/                                # FastAPI 路由
│   ├── __init__.py
│   ├── main.py                         # App 入口
│   ├── deps.py                         # 依赖注入 (Agent, Memory, Tools)
│   ├── routes/
│   │   ├── chat.py                     # SSE 流式对话接口
│   │   ├── resume.py                   # 简历 CRUD
│   │   ├── jd.py                       # JD 匹配
│   │   ├── github.py                   # GitHub 分析
│   │   └── export.py                   # 导出接口
│   └── middleware/
│       ├── sanitizer.py                # 请求脱敏中间件
│       └── logging.py                  # JSON 结构化日志
│
├── frontend/                           # Next.js 14 前端
│   ├── app/
│   │   ├── layout.tsx
│   │   ├── page.tsx                    # 主页 (对话界面)
│   │   ├── resume/
│   │   │   └── [id]/page.tsx           # 简历编辑页
│   │   └── match/
│   │       └── page.tsx                # JD 匹配页
│   ├── components/
│   │   ├── chat/                       # 对话组件
│   │   │   ├── ChatPanel.tsx           # 对话面板
│   │   │   ├── MessageBubble.tsx       # 消息气泡 (含推理过程展开)
│   │   │   └── ReasoningChain.tsx      # Agent 推理链可视化
│   │   ├── resume/                     # 简历组件
│   │   │   ├── ResumeEditor.tsx        # 所见即所得编辑器
│   │   │   ├── SectionCard.tsx         # 简历区块卡片
│   │   │   └── DiffViewer.tsx          # 版本差异对比
│   │   └── match/                      # 匹配报告组件
│   │       └── MatchReport.tsx         # 匹配报告可视化
│   ├── hooks/
│   │   ├── useSSE.ts                   # SSE 流式消费 Hook
│   │   └── useResume.ts                # 简历状态管理
│   └── lib/
│       └── api.ts                      # 后端 API 封装
│
├── data/                               # 运行时数据 (gitignored)
│   ├── sqlite.db                       # SQLite 主库
│   ├── chroma/                         # ChromaDB 持久化目录
│   ├── cache/                          # diskcache 缓存目录
│   └── uploads/                        # 用户上传的简历文件
│
├── tests/                              # 测试
│   ├── unit/
│   │   ├── test_tools.py
│   │   ├── test_memory.py
│   │   └── test_evaluation.py
│   ├── integration/
│   │   ├── test_agent_loop.py
│   │   └── test_github_analysis.py
│   └── fixtures/
│       ├── sample_resume.pdf
│       └── sample_jd.txt
│
├── pyproject.toml                      # Python 项目配置
├── package.json                        # 前端项目配置
└── README.md
```

---

## 9. 部署方案

### 9.1 开发环境

```bash
# 后端
git clone <repo>
cd resume-agent
pip install -e ".[dev]"

# 设置 API Key
export ANTHROPIC_API_KEY=sk-ant-...

# 启动后端 (单命令, 零外部依赖)
python -m api.main
# → FastAPI 启动在 http://localhost:8000
# → SQLite 自动创建在 data/sqlite.db
# → ChromaDB 自动初始化在 data/chroma/

# 前端
cd frontend
npm install
npm run dev
# → Next.js 启动在 http://localhost:3000
```

### 9.2 生产部署（可选）

选一个最简单的方案即可（用户少 + 个人项目）：

```
方案 A — 单容器部署:
  Dockerfile:
    Stage 1: 构建前端 (npm build → static files)
    Stage 2: Python + FastAPI + 静态文件服务
  → docker run -p 8000:8000 resume-agent
  → 浏览器访问 localhost:8000

方案 B — 分离部署:
  前端 → Vercel (免费)
  后端 → Fly.io / Railway (免费额度)
```

两种方案都只需要设置环境变量 `ANTHROPIC_API_KEY`，无需配置数据库连接串。

---

## 10. 附录：面试叙事参考

### 10.1 一句话总结

> "我设计的是一个单 Agent 深度推理系统，核心挑战是长时序复杂任务的规划、工具编排和单点容错，而不是简单的 LLM 对话封装。"

### 10.2 五个关键技术话题

**话题 1：Agent 核心循环**

> "我实现的是 Plan-Act-Observe-Replan 循环，不是简单的用户输入→LLM 返回。Agent 在每一步都自主推理下一步做什么、调用什么工具、结果是否达标。不达标就自动修正，相当于在推理时做自我纠错。"

**话题 2：mem0 风格记忆系统**

> "记忆系统参考了 mem0 的设计——记忆不是存对话日志，而是从对话中自动提取结构化事实。有去重、合并、演化和遗忘机制。比如用户说'我之前做过 2 年后端'和'我在 XX 公司写了 2 年 Go'，系统会自动合并为一条技能事实而不是两条独立记录。底层用 ChromaDB 做语义检索，SQLite 存元数据。"

**话题 3：双层质量评估**

> "我设计了两层评估架构。规则层在本地毫秒级处理 80% 的低级问题——弱动词、敏感信息、格式错误；LLM 层投入剩余的 20%，做语义层面的 STAR 完整度、量化密度评估。这样既保证了质量，又控制了 API 成本。评估框架还可以做回归测试——每次改 prompt 后跑一组用例看分数有没有退化。"

**话题 4：分层容错**

> "单 Agent 没有其他 Agent 做冗余，所以容错更关键。我做了四层——工具重试（指数退避）、策略降级（GitHub API 挂了用缓存）、Checkpoint 恢复（崩溃后从断点继续）、最后是优雅降级到人工（告诉用户哪里做不了，给手动操作入口）。"

**话题 5：按量选型**

> "我在技术选型上做了有意识的抉择——不用 PostgreSQL 用 SQLite WAL，不用 Redis 用 diskcache，不用 Pinecone 用 ChromaDB 嵌入式模式。整个系统 `pip install` + `npm install` 就能跑，零外部依赖。但如果未来用户量增长，数据访问层已经做了抽象，迁移路径是清晰的。"

### 10.3 面试官可能的追问及准备

| 问题 | 准备 |
|------|------|
| "LangGraph 的状态图和普通状态机有什么区别？" | LangGraph 的状态图是 LLM 驱动的——状态转换决策由 LLM 推理决定，不是硬编码的转换条件。而且 graph 可以在运行时动态修改（比如用户说跳过某一步） |
| "ChromaDB 的向量检索精度怎么样？" | 对于个人使用场景（几千条记忆），ChromaDB 的 HNSW 索引精度足够。但如果扩展到团队使用，可以迁移到 pgvector 或 Qdrant，数据访问层已做抽象 |
| "Plan-Observe 循环会不会死循环？" | 有最大循环次数限制 + 连续失败检测。连续 3 步失败会自动请求人工介入，不会无限制重试 |
| "为什么不直接用 mem0 库？" | mem0 是通用记忆方案，但我需要简历领域的特化——记忆类型（Profile/Preference/Session/Feedback）是领域特定的，Consolidator 的合并规则也与通用方案不同。理念上参考了 mem0 的设计哲学，但实现上做了领域适配 |

---

> 配套文档: [ResumeAgent-PRD.md](./ResumeAgent-PRD.md)
