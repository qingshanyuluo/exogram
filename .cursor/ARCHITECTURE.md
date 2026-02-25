# 核心架构与约定

## 1. 项目定位

**Exogram** 是浏览器 Agent 的「程序性记忆」中间件：一次示教，永久复用，跨 UI 泛化。

- **browser-use**：Agent 的「手」（执行层）
- **workflow-use**：Agent 的「眼」（感知层）
- **Exogram**：Agent 的「海马体」（记忆层）

闭环：**录制 → 认知蒸馏 → 记忆存储 → 规则注入执行**。

---

## 2. 技术栈

| 层级 | 技术 |
|------|------|
| 语言/运行时 | Python 3.11+ |
| CLI | Typer + Rich Markdown |
| 执行层 | browser-use（Agent + Browser） |
| LLM | LangChain + OpenAI 兼容 API（蒸馏与执行可配置不同模型） |
| 数据模型 | Pydantic v2 |
| 录制（可选） | Playwright（`pip install -e ".[recorder]"`） |
| 配置 | python-dotenv + `.env`，入口 `exogram.config.load_settings()` |

---

## 3. 目录与模块职责

```
src/exogram/
├── cli.py                 # 命令行入口：record / record-live / setup-auth / distill / memorize / run
├── config.py              # 配置：data_dir、模型、OpenAI 超时等
├── models.py              # 基础模型：RawStep、RawStepsDocument、CognitionRecord、SemanticRecord 等
├── models_rich.py         # 富认知模型：RichCognitionRecord、WebsiteInfo、KeyElement、OperationKnowledge 等
├── utils.py               # 通用工具：ensure_dir、read_json、write_json、normalize_text、get_logger
├── recording/             # 录制
│   ├── live_recorder.py       # 交互式浏览器录制（Playwright），支持 SSO 登录态保存/复用
│   └── workflow_use_adapter.py # 将 workflow-use 的 JSON 转为 RawStepsDocument
├── distillation/          # 认知蒸馏
│   ├── semantic_distiller.py  # 主蒸馏器：RawStepsDocument → RichCognitionRecord（LLM 一次调用）
│   └── distiller.py           # 旧版蒸馏器（已不用）
├── memory/                # 长期记忆
│   └── jsonl_store.py     # JSONL 存储：append、list_all、retrieve（简单文本/标签匹配）
└── execution/             # 带知识执行
    ├── executor.py        # 封装 browser-use Agent：注入 wisdom，run_sync/run
    ├── context.py         # CognitiveContextManager：RichCognitionRecord → 系统指令（Prompt）
    └── auth.py           # 登录态：get_cdp_compatible_auth_file（兼容 browser-use）
```

- **`/recording`**：产出 `RawStepsDocument`（.raw_steps.json），不依赖 selector，偏语义化。
- **`/distillation`**：仅用 `SemanticDistiller`，输入 RawSteps，输出 `RichCognitionRecord`（.cognition.json）。
- **`/memory`**：`JsonlMemoryStore` 存 `CognitionRecord`，支持按 topic/query 检索，供后续扩展「按任务检索记忆」。
- **`/execution`**：加载 cognition → `CognitiveContextManager.build_system_instruction()` 得到 wisdom → `Executor.run_sync(task, wisdom)`。

---

## 4. 核心数据流

1. **录制**：人类操作 → LiveRecorder 或 WorkflowUseJsonAdapter → `RawStepsDocument` → 写入 `data/recordings/{topic}.raw_steps.json`。
2. **蒸馏**：`SemanticDistiller.distill(raw_doc)` → `RichCognitionRecord` → 写入 `{topic}.cognition.json`。
3. **记忆（可选）**：`memorize` 将 cognition 转为 `CognitionRecord` 追加到 `data/memory/memory.jsonl`，便于多 topic 检索。
4. **执行**：`run --topic T / --cognition path` 加载 cognition → 构建 wisdom → `Executor` 将 wisdom 注入任务描述 → browser-use Agent 执行。

---

## 5. 核心业务闭环

- **录**：`exogram record-live --topic X --start-url U` 或 `exogram record --topic X --workflow-json W`。
- **炼**：`exogram distill --recording data/recordings/X.raw_steps.json`。
- **存**：`exogram memorize --cognition data/recordings/X.cognition.json`（可选）。
- **跑**：`exogram run --topic X --task "用户自然语言任务"`（或 `--cognition path`）。

约束：UI 描述与操作知识均语义化，不依赖 XPath/CSS selector；敏感数据本地优先，仅 DOM/步骤文本参与蒸馏。

---

## 6. 配置与环境变量（要点）

- `EXOGRAM_DATA_DIR`：数据根目录（默认 `./data`）。
- `OPENAI_API_KEY` / `OPENAI_BASE_URL`：通用；蒸馏可用 `DISTILLATION_OPENAI_*`，执行可用 `EXECUTION_OPENAI_*`。
- `DISTILLATION_MODEL` / `EXECUTION_MODEL`（或 `EXOGRAM_AGENT_MODEL`）：蒸馏与执行模型分离。
- `EXOGRAM_FLASH_MODE=1`：执行时跳过评估，仅用记忆。
- 登录态：默认 `~/.exogram/auth/{domain}.json`，可由 `exogram setup-auth` 初始化。
