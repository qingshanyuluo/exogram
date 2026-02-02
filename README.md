## exogram（ETL for Experience）
 
 目标：把一次人类操作的“过程日志”蒸馏成可复用的 SOP / Heuristics（长期记忆），并在下次执行同类任务时注入到 `browser-use` Agent，让它带着“锦囊妙计”现场发挥，而不是跑死脚本。
 
 ### 目录结构
- `src/exogram/recording/`：录制导入（把 workflow-use 导出的 `.workflow.json` 归一化为 RawSteps）
- `src/exogram/distillation/`：认知蒸馏（LLM 复盘总结，只输出自然语言规则）
- `src/exogram/memory/`：长期记忆（JSONL 文件存储 + 简单检索）
- `src/exogram/execution/`：带知识执行（检索记忆并注入 `browser-use.Agent`）
 - `data/recordings/`：RawSteps 输出目录
 - `data/memory/memory.jsonl`：长期记忆（逐行 JSON）
 
 ### 安装（Python 3.11）
 在项目根目录：
 
 ```bash
uv venv --seed -p 3.11 .venv
 source .venv/bin/activate
 pip install -e .
 ```
 
说明：`browser-use` 当前版本不一定依赖 Playwright；如果你使用本机浏览器模式，请确保系统已安装可用的 Chrome/Chromium。
 
 配置环境变量：
 
 ```bash
 cp .env.example .env
 # 编辑 .env，填入 OPENAI_API_KEY
 ```
 
 ### 端到端 MVP（record → distill → run）
 1) **导入录制**（输入：workflow-use 导出的 `.workflow.json`）
 
 ```bash
exogram record --topic ERP_Export --workflow-json /path/to/example.workflow.json
 ```
 
### 交互式录制（打开浏览器让你操作）
如果你希望“开始录制 → 打开浏览器 → 手动操作 → 点击悬浮按钮结束 → 生成录制事件”，用：

```bash
# 安装录制依赖（二选一）
pip install -e ".[recorder]"
# 或：pip install playwright

# 安装浏览器驱动（只需一次）
playwright install chromium

# 开始录制
exogram record-live --topic ERP_Export --start-url "https://example.com"
```

 2) **蒸馏认知**（输出：写入 `data/memory/memory.jsonl`）
 
 ```bash
exogram distill --topic ERP_Export --recording data/recordings/ERP_Export.raw_steps.json
 ```
 
 3) **带知识执行**（先检索 topic 相关记忆，再注入 agent 任务）
 
 ```bash
exogram run --topic ERP_Export --task "帮我下载昨天的报表，优先 CSV 格式"
 ```
 
### 快速自检（不需要任何 API Key）
你可以先用示例 workflow JSON 验证 `record` 命令可用：

```bash
exogram record --topic Demo --workflow-json examples/example.workflow.json
```

 ### 说明：workflow-use 与本项目关系
- workflow-use 更像“眼睛/采集层”（Chrome 扩展 + 结构化 workflow JSON）。本项目不会把它生成的脚本当成执行来源。
- 你可以继续用 workflow-use 的扩展录制；只要把导出的 `.workflow.json` 路径喂给 `exogram record` 即可。
