"""Web 端 Prompt 拼接与会话存储（不启动服务器、不加载模型）。"""
import time

from sessions import SessionStore
from web import build_prompt, chunk_to_dict
from rag_engine import Chunk


class FakeChunk:
    """与 Chunk 同形的轻量对象，避免测试导入触法真实引擎。"""

    def __init__(self, text: str, source: str, chunk_index: int) -> None:
        self.text = text
        self.source = source
        self.chunk_index = chunk_index


def test_build_prompt_contains_all_sections():
    chunks = [FakeChunk("片段内容A", "a.md", 0), FakeChunk("片段内容B", "b.md", 3)]
    history = [{"role": "user", "content": "上一问"}, {"role": "assistant", "content": "上一答"}]
    prompt = build_prompt("当前问题", chunks, history)

    assert "当前问题" in prompt
    assert "片段内容A" in prompt and "片段内容B" in prompt
    assert "a.md" in prompt and "b.md" in prompt
    assert "上一问" in prompt and "上一答" in prompt
    assert "对话历史" in prompt


def test_build_prompt_without_history():
    prompt = build_prompt("问题", [FakeChunk("内容", "a.md", 0)], [])
    assert "问题" in prompt
    # 模板说明文字含"对话历史"，但无历史时不应出现历史区块
    assert "对话历史：\n" not in prompt
    assert "上一问" not in prompt


def test_chunk_to_dict_shape():
    data = chunk_to_dict(Chunk(text="文本", source="s.md", chunk_index=2))
    assert data == {"source": "s.md", "chunk_index": 2, "text": "文本"}


def test_session_store_roundtrip(tmp_path):
    store = SessionStore(tmp_path / "sessions.db")
    store.append("s1", "第一个问题", "第一个回答")
    store.append("s1", "第二个问题", "第二个回答")
    store.append("s2", "另一个会话问题", "另一个会话回答")

    messages = store.messages("s1")
    assert [m["role"] for m in messages] == ["user", "assistant", "user", "assistant"]
    assert messages[2]["content"] == "第二个问题"

    sessions = store.list_sessions()
    assert len(sessions) == 2
    # s2 后写入，updated_at 更新，应排在前
    assert sessions[0]["session_id"] == "s2"
    assert sessions[1]["preview"] == "第一个问题"


def test_session_store_delete(tmp_path):
    store = SessionStore(tmp_path / "sessions.db")
    store.append("s1", "问题", "回答")
    store.delete("s1")
    assert store.messages("s1") == []
    assert store.list_sessions() == []


def test_session_store_survives_reopen(tmp_path):
    db = tmp_path / "sessions.db"
    store = SessionStore(db)
    store.append("s1", "持久化问题", "持久化回答")
    store.close()

    reopened = SessionStore(db)
    messages = reopened.messages("s1")
    assert messages[0]["content"] == "持久化问题"


def test_session_preview_truncates(tmp_path):
    store = SessionStore(tmp_path / "s.db")
    store.append("s1", "长" * 200, "答")
    preview = store.list_sessions()[0]["preview"]
    assert len(preview) <= 63
    assert preview.endswith("...")
