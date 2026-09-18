from dataclasses import dataclass

import config
from llm import chat


QUERY_REWRITE_PROMPT = """You rewrite user questions into standalone retrieval queries for a RAG knowledge base.

Rules:
- Use the conversation history only to resolve references and omitted context.
- Preserve key entities, filenames, numbers, time ranges, constraints, and technical terms.
- Do not answer the question.
- Do not add facts that are not implied by the user question or history.
- If the original question is already clear for retrieval, return it unchanged.
- Output only one retrieval query. No markdown, quotes, explanation, or prefix.

Conversation history:
{history}

User question:
{question}

Retrieval query:"""


@dataclass(frozen=True)
class QueryRewriteResult:
    original_query: str
    search_query: str
    rewritten: bool
    error: str | None = None


def rewrite_query(
    provider_name: str,
    model: str | None,
    question: str,
    history: list[dict],
) -> QueryRewriteResult:
    original = question.strip()
    if not config.ENABLE_QUERY_REWRITE or not original or not history:
        # 无历史时改写没有可补全的指代，跳过这次 LLM 调用
        return QueryRewriteResult(original_query=original, search_query=original, rewritten=False)

    prompt = QUERY_REWRITE_PROMPT.format(
        history=_format_history(history),
        question=original,
    )

    try:
        rewritten = chat(
            provider_name=provider_name,
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=config.QUERY_REWRITE_MAX_TOKENS,
        )
    except Exception as exc:
        return QueryRewriteResult(
            original_query=original,
            search_query=original,
            rewritten=False,
            error=str(exc),
        )

    search_query = _clean_rewritten_query(rewritten) or original
    return QueryRewriteResult(
        original_query=original,
        search_query=search_query,
        rewritten=search_query != original,
    )


def _format_history(history: list[dict]) -> str:
    recent = history[-config.QUERY_REWRITE_HISTORY_MESSAGES :]
    if not recent:
        return "(none)"

    lines = []
    for message in recent:
        role = "User" if message.get("role") == "user" else "Assistant"
        content = " ".join(str(message.get("content", "")).split())
        if len(content) > 500:
            content = content[:500] + "..."
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


def _clean_rewritten_query(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`").strip()

    lines = [line.strip().strip("\"'`") for line in cleaned.splitlines() if line.strip()]
    if not lines:
        return ""

    query = " ".join(lines).strip().strip("\"'`")
    for prefix in ("retrieval query:", "rewritten query:", "search query:", "query:"):
        if query.lower().startswith(prefix):
            query = query[len(prefix) :].strip()
            break
    return query
