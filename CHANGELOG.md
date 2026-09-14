# 更新日志

本文件记录每个发布版本的显著变更。

## 0.2.0 - 2026-09-14

### 新增

- **Web 界面**：`uv run web.py` 启动，浏览器访问 <http://127.0.0.1:8000>
  - 三栏工作台：模型连接与知识库面板、对话区、引用来源面板
  - NDJSON 流式输出，等待时有打字动画，生成中有光标跟随
  - 回答支持安全 Markdown 渲染（标题/列表/代码块/粗斜体等；全量 HTML 转义，链接仅放行 http/https/mailto）
  - 回答中的 `[来源: 文件 - 片段 N]` 引用可点击，联动高亮右侧对应的来源卡片
  - 欢迎页提供可点击的快捷问题卡片
  - 知识库面板展示文件列表（按类型着色徽标）、文件/片段统计，支持一键重建索引
- **多轮对话查询改写**（`query_rewrite.py`）：LLM 结合对话历史把追问（如"那第二种呢？"）补全为独立检索词，与原始问题各自检索后 RRF 融合，提升多轮场景召回。可通过 `ENABLE_QUERY_REWRITE=false` 关闭，详见 README

### 修复

- `rebuild_full.py --test-query` 对 Chunk 对象做切片导致的 TypeError
- Web 端长对话把页面整体撑高、无法滚动的问题（grid 子项缺 `min-height: 0`）
- 超长文件名的引用标签溢出对话气泡（中间截断显示，悬停可见全名）

### 其他

- 静态资源响应增加 `Cache-Control: no-cache`，避免浏览器使用过期前端文件
- `.gitignore` 补充 `.uv-cache/`、`.agents/`
- README 补充 Web 启动方式、查询改写说明与项目结构
- 移除内部交接文档与私有知识文档的版本跟踪（本地文件保留）

## 0.1.0 - 2026-06-22

- 首个版本：CLI 交互问答、混合检索（向量 + BM25 + RRF 融合）、CrossEncoder 重排序（缺失时自动降级）、基于 mtime 的增量索引、多供应商 LLM 支持（DeepSeek / Moonshot / Qwen / MiniMax / OpenRouter / 本地代理）
