"""切块逻辑：段落保留、句子打包、重叠窗口。"""
import config
import rag_engine


def make_engine() -> rag_engine.RAGEngine:
    # 不触发 __init__（不加载模型/DB），只使用纯文本方法
    return rag_engine.RAGEngine.__new__(rag_engine.RAGEngine)


def test_short_paragraphs_kept_as_is():
    eng = make_engine()
    chunks = eng._split_into_chunks("短段落。\n\n另一段。")
    assert chunks == ["短段落。", "另一段。"]


def test_empty_text_yields_no_chunks():
    eng = make_engine()
    assert eng._split_into_chunks("") == []
    assert eng._split_into_chunks("\n\n  \n") == []


def test_long_paragraph_split_with_overlap():
    eng = make_engine()
    para = "".join(f"这是第{i}个用于测试重叠的完整句子。" for i in range(40))
    chunks = eng._split_into_chunks(para, max_len=200)

    assert len(chunks) >= 2
    assert all(len(c) <= 200 for c in chunks)
    # 相邻块之间应有重叠：后一块开头的内容出现在前一块结尾附近
    for i in range(len(chunks) - 1):
        tail = eng._tail_overlap(chunks[i], config.CHUNK_OVERLAP)
        assert tail and chunks[i + 1].startswith(tail)


def test_tail_overlap_sentence_aligned():
    eng = make_engine()
    tail = eng._tail_overlap("一二三。四五六。七八九。", 10)
    assert tail.endswith("。")
    assert "一二三" not in tail  # 不会把整段都当重叠


def test_tail_overlap_disabled_with_zero():
    eng = make_engine()
    assert eng._tail_overlap("任意文本。", 0) == ""


def test_page_marker_lines_filtered():
    eng = make_engine()
    chunks = eng._split_into_chunks("正文第一段。\n\n12\n\n第34页\n\n正文第二段。")
    assert chunks == ["正文第一段。", "正文第二段。"]
