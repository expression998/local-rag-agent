import argparse
import sys

from config import DEFAULT_PROVIDER, PROVIDERS
from llm import chat_stream, get_provider
from rag_engine import Chunk, RAGEngine

PROMPT_TEMPLATE = """你是一位知识问答助手。请根据对话历史、用户问题和相关文档片段，生成准确、简洁的回答。

{history}
用户问题：{question}

相关片段：
{context}

请只基于上述内容作答；如果片段不足以支持结论，请明确说明不知道，不要编造信息。在回答中，如果需要引用某个片段，请在相关句子末尾用上标标注来源，例如 [来源: example.md - 片段 3]。
"""

SUPPORTED_EXTS = ".md / .txt / .pdf / .docx"


def build_prompt(question: str, chunks: list[Chunk], history: list[dict]) -> str:
    history_str = ""
    if history:
        lines = []
        for msg in history:
            role = "用户" if msg["role"] == "user" else "助手"
            lines.append(f"{role}: {msg['content']}")
        history_str = "对话历史：\n" + "\n".join(lines) + "\n\n"

    context_lines = []
    for i, chunk in enumerate(chunks, 1):
        label = f"[片段{i} 来源: {chunk.source} - 第{chunk.chunk_index}段]"
        context_lines.append(f"{label}\n{chunk.text}")

    return PROMPT_TEMPLATE.format(
        history=history_str,
        question=question,
        context="\n\n".join(context_lines),
    )


def print_header(provider_name: str, model: str) -> None:
    print("=" * 56)
    print("  知识问答 Agent (RAG)")
    print(f"  供应商：{provider_name}")
    print(f"  模型：  {model}")
    print(f"  支持：  {SUPPORTED_EXTS}")
    print("  命令：  quit/exit/q 退出 | provider 查看供应商 | /clear 清除记忆 | /memory 查看记忆")
    print("=" * 56)


def main() -> None:
    parser = argparse.ArgumentParser(description="RAG 知识问答 Agent")
    parser.add_argument(
        "--provider",
        "-p",
        default=DEFAULT_PROVIDER,
        help=f"LLM 供应商（默认：{DEFAULT_PROVIDER}）",
    )
    parser.add_argument(
        "--model",
        "-m",
        default=None,
        help="模型名（默认使用供应商 default_model）",
    )
    parser.add_argument(
        "--reindex",
        action="store_true",
        help="强制重建知识库索引",
    )
    args = parser.parse_args()

    provider = get_provider(args.provider)
    if not provider:
        available = ", ".join(PROVIDERS.keys())
        print(f"错误：未知供应商 '{args.provider}'，可选：{available}")
        sys.exit(1)

    model = args.model or provider.default_model
    print_header(provider.display_name, model)

    print("\n正在加载 RAG 引擎...")
    engine = RAGEngine()

    print("正在索引知识文档...")
    total = engine.index_directory(force=args.reindex)
    if total:
        print(f"索引可用，共 {total} 个片段。\n")
    else:
        print("警告：knowledge 目录为空，或没有可索引的文档。\n")

    conversation_history: list[dict] = []

    while True:
        try:
            raw = input("\n请输入问题 > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not raw:
            continue
        if raw.lower() in ("quit", "exit", "q"):
            break
        if raw.lower() == "provider":
            _show_providers()
            continue
        if raw.lower() in ("/clear", "/reset"):
            conversation_history.clear()
            print("对话记忆已清除。\n")
            continue
        if raw.lower() == "/memory":
            _show_memory(conversation_history)
            continue

        result = engine.query(raw)
        if not result["context"]:
            print("未找到相关文档片段。")
            continue

        print(f"\n找到 {len(result['context'])} 个相关片段。")
        prompt = build_prompt(result["question"], result["context"], conversation_history)

        print("回答：", end="", flush=True)
        answer = ""
        try:
            for token in chat_stream(
                provider_name=provider.name,
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
            ):
                print(token, end="", flush=True)
                answer += token
            print()
        except Exception as exc:
            print(f"\n调用 LLM 失败：{exc}")
            continue

        # 展示引用来源
        print("\n--- 引用来源 ---")
        seen_sources: set[tuple[str, int]] = set()
        for chunk in result["context"]:
            key = (chunk.source, chunk.chunk_index)
            if key not in seen_sources:
                seen_sources.add(key)
                preview = chunk.text[:80].replace("\n", " ") + ("..." if len(chunk.text) > 80 else "")
                print(f"  [{chunk.source} - 第{chunk.chunk_index}段] {preview}")

        conversation_history.append({"role": "user", "content": raw})
        conversation_history.append({"role": "assistant", "content": answer})


def _show_memory(conversation_history: list[dict]) -> None:
    if conversation_history:
        print(f"\n当前记忆（{len(conversation_history)} 条）：")
        for msg in conversation_history:
            role = "用户" if msg["role"] == "user" else "助手"
            preview = msg["content"][:80] + "..." if len(msg["content"]) > 80 else msg["content"]
            print(f"  [{role}] {preview}")
    else:
        print("暂无对话记忆。")
    print()


def _show_providers() -> None:
    print("\n可用供应商：")
    for name, provider in PROVIDERS.items():
        flag = "（未配置 API Key）" if not provider.api_key or provider.api_key.startswith("your-") else ""
        print(f"  [{name}] {provider.display_name}{flag}")
        print(f"         模型：{', '.join(provider.models)}")
    print()


if __name__ == "__main__":
    main()
