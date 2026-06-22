# RAG Agent 项目交接说明

## 1. 项目当前状态

这是一个本地运行的 RAG 知识问答项目，入口是 `agent.py`。系统会读取 `knowledge/` 目录中的知识文档，构建本地 ChromaDB 向量索引，同时构建 BM25 关键词索引；查询时使用“向量检索 + BM25 + RRF 融合”，如果本地重排序模型完整可用，则再用 CrossEncoder 做 top-k 重排序，最后调用 OpenAI 兼容接口生成回答。

当前项目已经做过一轮 GitHub 发布前整理：

- 已初始化 Git 仓库。
- 已补充 `.gitignore`，避免提交 `.env`、`.venv/`、`chroma_db/`、`.uv-cache/`、本地私有知识文档和大型 PDF。
- 已新增 `.env.example`。
- 已新增 `knowledge/example.md` 作为可公开示例知识文档。
- 已修复主要 Python 文件中的中文乱码和破损字符串。
- 已将 `rebuild_full.py` 改成通用完整重建脚本，不再硬编码本机 PDF 路径。
- 已让 reranker 模型缺失时自动降级，不再启动崩溃。

## 2. 重要文件

```text
agent.py             CLI 入口，交互式问答、Prompt 拼接、对话历史
config.py            模型、路径、检索参数、LLM 供应商配置
llm.py               OpenAI SDK 封装，支持流式/非流式调用
rag_engine.py        RAG 核心逻辑：解析、切块、索引、检索、重排序
rebuild_full.py      完整重建索引脚本
README.md            对外项目说明
HANDOFF.md           当前交接文档
.env.example         环境变量示例
.gitignore           GitHub 发布前忽略规则
knowledge/example.md 可公开示例知识文档
```

本地文件中仍然存在但不会提交：

```text
.env
.venv/
.uv-cache/
chroma_db/
knowledge/doc.md
knowledge/*.pdf
```

## 3. 启动方式

进入项目目录：

```bash
cd "C:\Users\LL\Desktop\RAG agent"
```

首次安装依赖：

```bash
uv sync
```

配置环境变量：

```bash
copy .env.example .env
```

然后编辑 `.env`，填入至少一个供应商的 API Key，并设置：

```env
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=your-real-api-key
```

启动问答：

```bash
uv run agent.py
```

指定供应商和模型：

```bash
uv run agent.py --provider deepseek --model deepseek-v4-flash
uv run agent.py -p cli-proxy -m gemini-2.5-flash
```

强制增量重建索引：

```bash
uv run agent.py --reindex
```

完整重建索引：

```bash
uv run rebuild_full.py
```

完整重建后顺便做测试查询：

```bash
uv run rebuild_full.py --test-query "RAG Agent 支持哪些文件格式？"
```

## 4. 当前 RAG 流程

```text
用户问题
  -> SentenceTransformer 生成查询向量
  -> ChromaDB 向量检索 top-10
  -> jieba + rank_bm25 关键词检索 top-10
  -> RRF 融合排序
  -> CrossEncoder 重排序 top-3，如果模型不可用则跳过
  -> agent.py 拼接 Prompt
  -> llm.py 调用 OpenAI 兼容 LLM 流式输出
```

## 5. 模型依赖说明

嵌入模型：

```text
shibing624/text2vec-base-chinese
```

重排序模型：

```text
BAAI/bge-reranker-base
```

`rag_engine.py` 当前使用 `local_files_only=True`，所以模型默认只从本地 Hugging Face 缓存加载。

如果嵌入模型缺失，项目仍会启动失败，因为没有嵌入模型就无法检索。

如果 reranker 模型缺失或下载不完整，项目现在不会崩溃，会提示 warning 并自动降级为混合检索结果直接取 top-3。

下载 reranker：

```bash
uv run python -c "from sentence_transformers import CrossEncoder; CrossEncoder('BAAI/bge-reranker-base')"
```

下载嵌入模型和 reranker：

```bash
uv run python -c "from sentence_transformers import SentenceTransformer, CrossEncoder; SentenceTransformer('shibing624/text2vec-base-chinese'); CrossEncoder('BAAI/bge-reranker-base')"
```

如需代理，可在 PowerShell 中设置：

```powershell
$env:HTTPS_PROXY="http://127.0.0.1:7897"
$env:HTTP_PROXY="http://127.0.0.1:7897"
```

## 6. GitHub 上传注意事项

上传前应确认：

```bash
git status --short --ignored
```

应该被忽略的内容包括：

```text
.env
.venv/
.uv-cache/
chroma_db/
knowledge/doc.md
knowledge/*.pdf
```

不要上传真实 `.env`。

不要上传本地知识库中的私有文件或版权不明确的 PDF。

当前推荐只上传：

```text
knowledge/.gitkeep
knowledge/example.md
```

首次提交可以执行：

```bash
git add .
git commit -m "Initial public RAG agent project"
```

如果要推到 GitHub：

```bash
git branch -M main
git remote add origin https://github.com/<your-name>/<repo-name>.git
git push -u origin main
```

## 7. 已知问题

1. **没有引用来源展示**
   - ChromaDB metadata 中已经保存 `source` 和 `chunk`。
   - 但当前 `retrieve()` / `rerank()` 只返回文本，不返回来源。
   - 建议下一步改成返回结构化结果，例如 `text/source/chunk/score`。

2. **切块策略仍比较基础**
   - 当前按段落和句子切分。
   - 还没有 overlap，也没有语义切块。
   - 长文档跨段答案可能召回不完整。

3. **删除知识文件后旧索引不会自动清理**
   - `.index_manifest.json` 记录文件 mtime。
   - 但文件被删除时，ChromaDB 中对应 chunks 目前不会自动删除。

4. **模型下载依赖网络环境**
   - 国内网络环境下 Hugging Face 模型可能下载失败。
   - 需要代理或提前手动缓存模型。

5. **缺少测试**
   - 当前没有 `pytest` 测试。
   - 至少应补切块、空库检索、manifest 增量索引、provider 配置测试。

## 8. 建议下一步优先级

P1：增加引用来源。

目标：回答后能展示来源文件和 chunk 编号，提升可信度。

P2：优化切块。

目标：增加 overlap，减少长文档跨段信息丢失。

P3：处理删除文件后的索引清理。

目标：知识目录删除文件后，自动删除 ChromaDB 中旧 chunks。

P4：增加测试和 CI。

目标：GitHub 上能自动跑基础语法检查和单元测试。

P5：改进模型加载体验。

目标：嵌入模型缺失时给出更友好的错误提示，或提供明确的下载脚本。

## 9. 当前接手建议

如果只是要先发 GitHub：

1. 确认 `.env` 和知识库 PDF 没有进入 `git status` 的待提交列表。
2. 提交当前代码。
3. 在 GitHub README 中说明模型需要本地缓存。
4. 后续再做引用来源和测试。

如果要继续打磨成更完整的 RAG 项目：

1. 先做“引用来源追踪”。
2. 再做“切块 overlap”。
3. 最后补测试和 GitHub Actions。
