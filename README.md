# RAG Agent

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

```bash
uv run agent.py
```

首次启动会自动下载嵌入模型并索引 `knowledge/` 目录中的文档。启动后直接输入问题即可：

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
├── config.py             # 配置：模型、路径、检索参数、供应商
├── llm.py                # LLM 调用封装（OpenAI SDK）
├── rag_engine.py         # RAG 核心：解析→切块→索引→检索→重排序
├── rebuild_full.py       # 完整重建索引脚本
├── pyproject.toml        # 项目依赖声明
├── .env                  # API Key 与默认供应商（已 gitignore）
├── .env.example          # 环境变量模板
├── .gitignore
├── README.md
├── HANDOFF.md            # 内部交接文档
├── knowledge/            # 知识文档目录，放入你的 .md/.txt/.pdf/.docx
├── chroma_db/            # ChromaDB 向量数据库（自动生成）
└── .index_manifest.json  # 索引清单（自动生成）
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
RAGEngine.retrieve()  混合检索
   ├── 向量检索：text2vec-base-chinese 嵌入 → ChromaDB，内积检索，取 top-10
   ├── BM25 检索：jieba 分词 → rank_bm25，取 top-10
   └── RRF 融合排序 → top-10
   ↓
RAGEngine.rerank()    重排序
   └── BAAI/bge-reranker-base CrossEncoder 打分 → top-3
   ↓
agent.py              拼接 Prompt
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

当前删除文件后，旧索引需要手动重建。使用 `uv run agent.py --reindex` 可清理全部旧索引并重建。

## License

MIT
