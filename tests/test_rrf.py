"""RRF 融合排序。"""
import rag_engine


def make_engine() -> rag_engine.RAGEngine:
    return rag_engine.RAGEngine.__new__(rag_engine.RAGEngine)


def make_chunk(text: str, source: str = "doc.md", idx: int = 0) -> rag_engine.Chunk:
    return rag_engine.Chunk(text=text, source=source, chunk_index=idx)


def test_rrf_prefers_chunks_in_both_lists():
    eng = make_engine()
    a = make_chunk("共同命中")
    b = make_chunk("只在向量")
    c = make_chunk("只在BM25")
    fused = eng._rrf_fuse([b, a], [c, a], top_k=3)
    # 同时出现在两个列表里的块融合分最高
    assert fused[0].text == "共同命中"


def test_rrf_dedupes_by_text():
    eng = make_engine()
    a1 = make_chunk("相同内容", "a.md", 1)
    a2 = make_chunk("相同内容", "a.md", 2)
    fused = eng._rrf_fuse([a1], [a2], top_k=10)
    assert len(fused) == 1


def test_rrf_respects_top_k():
    eng = make_engine()
    chunks = [make_chunk(f"文本{i}") for i in range(20)]
    fused = eng._rrf_fuse(chunks, [], top_k=5)
    assert len(fused) == 5


def test_rrf_empty_inputs():
    eng = make_engine()
    assert eng._rrf_fuse([], [], top_k=5) == []
