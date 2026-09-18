# RAG Agent

[![CI](https://github.com/expression998/local-rag-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/expression998/local-rag-agent/actions/workflows/ci.yml)

一个本地运行的检索增强生成（RAG）知识问答系统。你可以把文档放进 `knowledge/` 目录，通过命令行提问，系统会从文档中找到相关内容并生成回答。

## 快速开始

### 前置条件

- Python 3.10+
- [uv](https://docs.astral.sh/uv/)（推荐）或 pip

### 安装

```bash
# 进入项目目录
cd RAG-agent

# 安装依赖
uv sync
```

### 配置

从示例文件创建配置：

```bash
copy .env.example .env
```

编辑 `.env`，填入至少一个 API Key：

```env
# 默认供应商
LLM_PROVIDER=deepseek

# DeepSeek
DEEPSEEK_API_KEY=sk-your-deepseek-api-key

# 或使用本地中转服务（见下方说明）
# LLM_PROVIDER=cli-proxy
# LLM_API_KEY=sk-your-proxy-api-key
# LLM_BASE_URL=http://localhost:8317/v1
```

### 启动问答

命令行模式：

```bash
uv run agent.py
```

或启动 Web 界面（推荐）：

```bash
uv run web.py
```

启动后打开 <http://127.0.0.1:8000>，在浏览器中选择供应商与模型、查看知识库状态、流式提问。回答支持 Markdown 渲染，`[来源: ...]` 引用可点击，点击后会高亮右侧对应的文档片段。

Web 界面还支持：

- **上传文档**：点"上传文档"按钮，或直接把文件拖进页面任意位置（.md/.txt/.pdf/.docx，≤20MB），入库后自动索引
- **删除文档**：知识库文件列表中的删除按钮，同步清理索引片段
- **多会话**：对话自动落盘（`sessions.db`），顶栏下拉切换历史会话或开新对话，重启不丢
- **深色模式**：顶栏一键切换，跟随系统偏好
- **引用展开**：点击右侧来源卡片查看片段全文

首次启动会自动下载嵌入模型并索引 `knowledge/` 目录中的文档。命令行模式下直接输入问题即可：

```
请输入问题 > RAG Agent 支持哪些文件格式？
```

### 指定供应商和模型

```bash
uv run agent.py --provider deepseek --model deepseek-v4-flash
uv run agent.py -p cli-proxy -m gemini-2.5-flash
```

## 项目结构

```text
RAG agent/
├── agent.py              # CLI 入口：交互式问答、Prompt 拼接
├── web.py                # Web 服务：静态页面 + API，NDJSON 流式输出
├── static/               # Web 前端（原生 HTML/CSS/JS）
├── query_rewrite.py      # 多轮对话查询改写（LLM 生成独立检索词）
├── sessions.py           # 会话持久化（SQLite，标准库）
├── config.py             # 配置：模型、路径、检索参数、供应商
├── llm.py                # LLM 调用封装（OpenAI SDK）
├── rag_engine.py         # RAG 核心：解析→切块→索引→检索→重排序
├── rebuild_full.py       # 完整重建索引脚本
├── tests/                # pytest 套件 + Node 渲染器测试
├── .github/workflows/    # GitHub Actions CI
├── pyproject.toml        # 项目依赖声明
├── .env                  # API Key 与默认供应商（已 gitignore）
├── .env.example          # 环境变量模板
├── .gitignore
├── README.md
├── CHANGELOG.md          # 更新日志
├── knowledge/            # 知识文档目录，放入你的 .md/.txt/.pdf/.docx
├── chroma_db/            # ChromaDB 向量数据库（自动生成）
└── .index_manifest.json  # 索引清单（自动生成）
```

### 运行测试

```bash
uv run pytest tests/ -v      # Python 单元测试
node tests/static/test_markdown.mjs   # 前端 Markdown 渲染器测试
```

## 使用说明

### 将你的文档放入知识库

系统支持四种文件格式：

| 格式 | 说明 |
| --- | --- |
| `.md` | Markdown 文档 |
| `.txt` | 纯文本文件 |
| `.pdf` | PDF 文档 |
| `.docx` | Word 文档 |

直接将文件复制到 `knowledge/` 目录，重启或在问答界面输入新问题时，系统会自动检测增量并索引。

### 重建索引

如果修改了知识库中的文件，系统会自动检测变更（基于文件修改时间）并做增量索引。

强制重建（清空旧索引后重新索引所有文件）：

```bash
uv run agent.py --reindex
```

完整重建（独立脚本，适合脚本化调用）：

```bash
uv run rebuild_full.py
```

重建后直接测试查询：

```bash
uv run rebuild_full.py --test-query "你的问题"
```

### 交互命令

| 输入 | 功能 |
| --- | --- |
| `quit` / `exit` / `q` | 退出 |
| `provider` | 查看可用供应商与模型列表 |
| `/clear` / `/reset` | 清除对话历史 |
| `/memory` | 查看当前对话记忆 |

### 引用来源

每次回答后，系统会展示引用了哪些文档片段：

```
回答：RAG Agent 支持 Markdown、纯文本、PDF 和 Word 文档格式。

--- 引用来源 ---
  [example.md - 第0段] RAG Agent 是一个基于检索增强生成的知识问答系统，支持 .md、.txt、.pdf ...
  [doc.md - 第3段] 用户可将文档放入 knowledge/ 目录，系统自动索引...
```

LLM 在回答时也会标注具体引用：

```
根据文档，RAG Agent 支持四种文件格式[来源: example.md - 第0段]。
```

## 架构流程

```text
用户提问
   ↓
query_rewrite.py      多轮查询改写
   └── 结合对话历史，把问题改写成独立检索词（可关闭）
   ↓
RAGEngine.retrieve()  混合检索
   ├── 向量检索：text2vec-base-chinese 嵌入 → ChromaDB，内积检索，取 top-10
   ├── BM25 检索：jieba 分词 → rank_bm25，取 top-10
   └── RRF 融合排序 → top-10（原始问题与改写问题两路结果再融合一次）
   ↓
RAGEngine.rerank()    重排序
   └── BAAI/bge-reranker-base CrossEncoder 打分 → top-3
   ↓
agent.py / web.py     拼接 Prompt
   └── 对话历史 + 用户问题 + 标注来源的相关片段
   ↓
llm.py                调用 LLM
   └── OpenAI 兼容接口，流式输出回答
```

## 配置说明

### 核心依赖

| 组件 | 用途 |
| --- | --- |
| chromadb | 本地向量数据库 |
| sentence-transformers | 文本嵌入（shibing624/text2vec-base-chinese） |
| CrossEncoder | 重排序（BAAI/bge-reranker-base） |
| rank-bm25 + jieba | BM25 关键词检索 |
| openai | LLM 调用（OpenAI 兼容接口） |
| pypdf | PDF 解析 |
| python-docx | Word 解析 |
| python-dotenv | 环境变量加载 |

### LLM 供应商

| 标识符 | 供应商 | 默认模型 |
| --- | --- | --- |
| `cli-proxy` | CLIProxyAPI 本地中转 | `gemini-2.5-flash` |
| `deepseek` | DeepSeek | `deepseek-v4-flash` |
| `minimax` | MiniMax | `minimax-text-01` |
| `moonshot` | Moonshot / Kimi | `moonshot-v1-8k` |
| `openrouter` | OpenRouter | `openai/gpt-4o` |
| `qwen` | 通义千问 | `qwen-plus` |

在 `.env` 中设置 `LLM_PROVIDER` 切换默认供应商，或在启动时用 `-p` 参数临时切换。

### 检索参数

在 `config.py` 中可调整：

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `RAG_TOP_K_RETRIEVE` | 10 | 混合检索取回数量 |
| `RAG_TOP_K_RERANK` | 3 | 重排序后保留数量 |
| `CHUNK_OVERLAP` | 80 | 相邻切块重叠字符数（按整句对齐），可用环境变量覆盖 |

### 索引版本与自动迁移

`.index_manifest.json` 带版本字段。当升级引入改变向量语义的改动（如 0.3.0 的嵌入归一化）时，版本号递增，下次启动自动全量重建一次——大知识库下首次启动会明显变慢，属预期行为。

### 查询改写（环境变量）

多轮对话中，用户的追问往往缺少上下文（如"那第二种呢？"）。查询改写会用 LLM 结合对话历史，把追问补全成独立检索词，再与原始问题各自检索并融合，提升多轮检索的召回。可在 `.env` 中配置：

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `ENABLE_QUERY_REWRITE` | `true` | 设为 `false` 关闭查询改写 |
| `QUERY_REWRITE_HISTORY_MESSAGES` | `6` | 改写时参考的最近消息条数 |
| `QUERY_REWRITE_MAX_TOKENS` | `128` | 改写输出的最大 token 数 |

### 模型下载

嵌入模型是启动必需的，重排序模型缺失时会自动降级。如需预先下载：

```bash
uv run python -c "from sentence_transformers import SentenceTransformer, CrossEncoder; SentenceTransformer('shibing624/text2vec-base-chinese'); CrossEncoder('BAAI/bge-reranker-base')"
```

国内网络环境下可能需要代理：

```powershell
$env:HTTPS_PROXY="http://127.0.0.1:7897"
$env:HTTP_PROXY="http://127.0.0.1:7897"
```

模型默认缓存在用户目录下的 Hugging Face cache，例如 `C:\Users\<用户名>\.cache\huggingface\hub\`。

## 在项目代码中调用

```python
from rag_engine import RAGEngine, Chunk

engine = RAGEngine()
engine.index_directory()

result = engine.query("你的问题")
# result["context"] 是 list[Chunk]
# Chunk 包含: text, source, chunk_index

for chunk in result["context"]:
    print(f"[{chunk.source} - 第{chunk.chunk_index}段] {chunk.text[:80]}")
```

## 常见问题

### 启动报错 "no model found"

嵌入模型未下载。运行模型下载命令（见上方），或检查网络代理。

### 回答质量不好

- 检查 `knowledge/` 中是否有足够的相关文档
- 在 `config.py` 中调大 `RAG_TOP_K_RERANK` 让更多片段进入上下文
- 切换更好的 LLM 模型

### 修改文档后索引没有更新

系统通过文件修改时间检测变更。如果修改时间未更新（如 git clone 后），可以加上 `--reindex` 强制重建。

### 知识库文件删除后旧索引还在

0.3.0 起已自动处理：知识目录中删除的文件会在下次索引时清理对应片段。也可用 `uv run agent.py --reindex` 强制全量重建。

### GBK/GB2312 编码的 txt 打不开

`.md`/`.txt` 按 `utf-8-sig → gb18030` 顺序自动尝试解码；两种都失败的文件会被跳过并在日志中告警，请转存为 UTF-8。

## License

MIT
