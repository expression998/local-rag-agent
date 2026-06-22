import argparse
import time

import config
from rag_engine import RAGEngine


def main() -> None:
    parser = argparse.ArgumentParser(description="完整重建 RAG 知识库索引")
    parser.add_argument(
        "--knowledge-dir",
        default=str(config.KNOWLEDGE_DIR),
        help="知识文档目录，默认使用项目内 knowledge 目录",
    )
    parser.add_argument(
        "--test-query",
        default=None,
        help="重建后执行一次测试检索",
    )
    args = parser.parse_args()

    started_at = time.time()
    print(f"知识目录：{args.knowledge_dir}")
    print("正在加载 RAG 引擎...")
    engine = RAGEngine()

    print("正在完整重建索引...")
    total = engine.index_directory(args.knowledge_dir, force=True)

    elapsed = time.time() - started_at
    print(f"\n完成：共 {total} 个片段，用时 {elapsed:.0f}s")
    print(f"ChromaDB 当前片段数：{engine.collection.count()}")

    if args.test_query:
        print(f"\n测试查询：{args.test_query}")
        chunks = engine.retrieve(args.test_query)
        best_chunks = engine.rerank(args.test_query, chunks)
        print(f"检索到 {len(chunks)} 个候选片段，重排序后 top-{len(best_chunks)}：")
        for index, chunk in enumerate(best_chunks, start=1):
            preview = chunk[:200].replace("\n", " ")
            print(f"\n[{index}] ({len(chunk)} chars) {preview}...")


if __name__ == "__main__":
    main()
