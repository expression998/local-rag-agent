"""查询改写的清洗与历史格式化（不发 LLM 请求）。"""
import config
import query_rewrite
from query_rewrite import QueryRewriteResult, _clean_rewritten_query, _format_history, rewrite_query


def test_clean_strips_code_fence_and_quotes():
    assert _clean_rewritten_query("```检索词```") == "检索词"
    assert _clean_rewritten_query('"检索词"') == "检索词"


def test_clean_strips_known_prefixes():
    assert _clean_rewritten_query("Retrieval Query: 检索词") == "检索词"
    assert _clean_rewritten_query("query: 检索词") == "检索词"


def test_clean_joins_multiline():
    assert _clean_rewritten_query("第一行\n第二行") == "第一行 第二行"


def test_clean_empty_returns_empty():
    assert _clean_rewritten_query("```\n```") == ""
    assert _clean_rewritten_query("   \n ") == ""


def test_format_history_truncates_long_content():
    history = [
        {"role": "user", "content": "很长的内容" * 200},
        {"role": "assistant", "content": "回答"},
    ]
    text = _format_history(history)
    assert "..." in text
    assert text.count("User:") == 1


def test_format_history_limits_message_count(monkeypatch):
    monkeypatch.setattr(config, "QUERY_REWRITE_HISTORY_MESSAGES", 2)
    history = [
        {"role": "user", "content": "问题0"},
        {"role": "assistant", "content": "回答0"},
        {"role": "user", "content": "问题最新"},
    ]
    text = _format_history(history)
    assert "问题0" not in text
    assert "问题最新" in text


def test_format_history_empty():
    assert _format_history([]) == "(none)"


def test_rewrite_skipped_without_history():
    """无历史时应短路返回，不触发 LLM 调用。"""
    result = rewrite_query("deepseek", None, "第一个问题", [])
    assert isinstance(result, QueryRewriteResult)
    assert result.search_query == "第一个问题"
    assert result.rewritten is False
    assert result.error is None


def test_rewrite_disabled_by_config(monkeypatch):
    monkeypatch.setattr(config, "ENABLE_QUERY_REWRITE", False)
    history = [{"role": "user", "content": "之前的问题"}, {"role": "assistant", "content": "回答"}]
    result = rewrite_query("deepseek", None, "追问", history)
    assert result.search_query == "追问"
    assert result.rewritten is False
