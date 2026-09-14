import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import chromadb
import jieba
from rank_bm25 import BM25Okapi
from sentence_transformers import CrossEncoder, SentenceTransformer

import config


@dataclass
class Chunk:
    """一个检索到的文档片段，携带来源信息。"""
    text: str
    source: str
    chunk_index: int

MANIFEST_PATH = config.BASE_DIR / ".index_manifest.json"
SUPPORTED_EXTS = ("*.md", "*.txt", "*.pdf", "*.docx")
CHROMA_BATCH_SIZE = 4000


class RAGEngine:
    def __init__(self) -> None:
        self.embedder = SentenceTransformer(config.EMBEDDING_MODEL, local_files_only=True)
        self.reranker: CrossEncoder | None = self._load_reranker()

        self.chroma_client = chromadb.PersistentClient(str(config.CHROMA_DIR))
        self.collection = self.chroma_client.get_or_create_collection(
            name=config.CHROMA_COLLECTION,
            metadata={"hnsw:space": config.CHROMA_SPACE},
        )

        self.bm25: BM25Okapi | None = None
        self.bm25_docs: list[str] = []

    def _load_reranker(self) -> CrossEncoder | None:
        try:
            return CrossEncoder(config.CROSS_ENCODER_MODEL, local_files_only=True)
        except OSError as exc:
            print(
                "[WARN] Reranker model is unavailable or incomplete. "
                "Falling back to hybrid retrieval without reranking."
            )
            print(f"[WARN] Model: {config.CROSS_ENCODER_MODEL}")
            print(f"[WARN] Reason: {exc}")
            print(
                "[HINT] Download it with: uv run python -c "
                "\"from sentence_transformers import CrossEncoder; "
                f"CrossEncoder('{config.CROSS_ENCODER_MODEL}')\""
            )
            return None

    def _read_md_txt(self, path: Path) -> str:
        return path.read_text(encoding="utf-8")

    def _read_pdf(self, path: Path) -> str:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        return "\n\n".join(page.extract_text() or "" for page in reader.pages)

    def _read_docx(self, path: Path) -> str:
        from docx import Document

        doc = Document(str(path))
        return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())

    def _read_document(self, path: Path) -> str:
        ext = path.suffix.lower()
        if ext == ".pdf":
            return self._read_pdf(path)
        if ext == ".docx":
            return self._read_docx(path)
        return self._read_md_txt(path)

    def _split_into_chunks(self, text: str, max_len: int = 500) -> list[str]:
        paragraphs = self._normalize_paragraphs(text)
        chunks: list[str] = []

        for paragraph in paragraphs:
            if len(paragraph) <= max_len:
                chunks.append(paragraph)
                continue

            current = ""
            for sentence in self._split_sentences(paragraph):
                if not current:
                    current = sentence
                elif len(current) + len(sentence) <= max_len:
                    current += sentence
                else:
                    chunks.append(current)
                    current = sentence

            if current:
                chunks.append(current)

        return [chunk for chunk in chunks if chunk.strip()]

    def _normalize_paragraphs(self, text: str) -> list[str]:
        lines = [line.strip() for line in text.splitlines()]
        merged: list[str] = []

        for line in lines:
            if not line:
                merged.append("")
                continue
            if self._is_page_marker(line):
                continue
            if merged and merged[-1] and not merged[-1].endswith(("。", "！", "？", "；", ":", "：", ")", "）")):
                merged[-1] += line
            else:
                merged.append(line)

        normalized = "".join(f"{line}\n" if line else "\n" for line in merged)
        return [p.strip() for p in normalized.split("\n\n") if p.strip()]

    def _split_sentences(self, paragraph: str) -> list[str]:
        sentences: list[str] = []
        current = ""

        for char in paragraph:
            current += char
            if char in "。！？；.!?;":
                sentences.append(current)
                current = ""

        if current:
            sentences.append(current)

        return sentences

    def _is_page_marker(self, line: str) -> bool:
        return line.isdigit() or (line.startswith("第") and line.endswith("页"))

    def _embed(self, texts: list[str]) -> list[list[float]]:
        return self.embedder.encode(texts, normalize_embeddings=False).tolist()

    def _build_bm25_index(self) -> None:
        all_docs = self.collection.get()["documents"]
        if all_docs:
            tokenized = [list(jieba.cut(d)) for d in all_docs]
            self.bm25 = BM25Okapi(tokenized)
            self.bm25_docs = list(all_docs)
        else:
            self.bm25 = None
            self.bm25_docs = []

    def _load_manifest(self) -> dict[str, float]:
        if MANIFEST_PATH.exists():
            return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        return {}

    def _save_manifest(self, manifest: dict[str, float]) -> None:
        MANIFEST_PATH.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _file_mtime(self, path: Path) -> float:
        return path.stat().st_mtime

    def _needs_index(self, path: Path, manifest: dict[str, float]) -> bool:
        name = path.name
        mtime = self._file_mtime(path)
        return name not in manifest or manifest[name] != mtime

    def index_file(self, file_path: str, manifest: dict[str, float] | None = None) -> int:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        text = self._read_document(path)
        chunks = self._split_into_chunks(text)
        if not chunks:
            return 0

        embeddings = self._embed(chunks)
        source = path.name
        ids = [f"{source}_{i}" for i in range(len(chunks))]
        metadatas = [{"source": source, "chunk": i} for i in range(len(chunks))]

        for i in range(0, len(chunks), CHROMA_BATCH_SIZE):
            self.collection.add(
                documents=chunks[i : i + CHROMA_BATCH_SIZE],
                embeddings=embeddings[i : i + CHROMA_BATCH_SIZE],
                ids=ids[i : i + CHROMA_BATCH_SIZE],
                metadatas=metadatas[i : i + CHROMA_BATCH_SIZE],
            )

        if manifest is not None:
            manifest[source] = self._file_mtime(path)

        return len(chunks)

    def index_directory(self, dir_path: str | None = None, force: bool = False) -> int:
        target = Path(dir_path) if dir_path else config.KNOWLEDGE_DIR
        manifest = {} if force else self._load_manifest()

        if force:
            self.clear_index()

        total = 0
        for pattern in SUPPORTED_EXTS:
            for fp in sorted(target.glob(pattern)):
                if not force and not self._needs_index(fp, manifest):
                    continue

                self._delete_file_chunks(fp.name)
                count = self.index_file(str(fp), manifest)
                status = "indexed" if count else "empty"
                print(f"  {status}: {fp.name} -> {count} chunks")
                total += count

        self._save_manifest(manifest)
        self._build_bm25_index()

        if not force and total == 0:
            count = self.collection.count()
            if count:
                print(f"  no updates needed, {count} chunks available")
                return count

        return total

    def _delete_file_chunks(self, source: str) -> None:
        existing = self.collection.get(where={"source": source})
        if existing["ids"]:
            self.collection.delete(ids=existing["ids"])

    def clear_index(self) -> None:
        all_ids = self.collection.get()["ids"]
        if all_ids:
            self.collection.delete(ids=all_ids)
        self.bm25 = None
        self.bm25_docs = []

    def retrieve(self, query: str, top_k: int = config.RAG_TOP_K_RETRIEVE) -> list[Chunk]:
        collection_count = self.collection.count()
        if collection_count == 0:
            return []

        n_results = min(top_k, collection_count)
        query_emb = self.embedder.encode([query], normalize_embeddings=False).tolist()
        vec_results = self.collection.query(
            query_embeddings=query_emb,
            n_results=n_results,
            include=["documents", "metadatas"],
        )
        vec_chunks = self._results_to_chunks(
            vec_results["documents"][0] if vec_results["documents"] else [],
            vec_results["metadatas"][0] if vec_results["metadatas"] else [],
        )

        if self.bm25 is None:
            self._build_bm25_index()

        bm25_chunks: list[Chunk] = []
        if self.bm25:
            tokenized_query = list(jieba.cut(query))
            bm25_scores = self.bm25.get_scores(tokenized_query)
            bm25_indices = sorted(
                range(len(bm25_scores)),
                key=lambda i: bm25_scores[i],
                reverse=True,
            )[:top_k]

            all_data = self.collection.get()
            all_docs = all_data["documents"]
            all_metadatas = all_data["metadatas"]
            if all_docs:
                bm25_chunks = [
                    Chunk(
                        text=all_docs[i],
                        source=all_metadatas[i]["source"] if all_metadatas and all_metadatas[i] else "unknown",
                        chunk_index=all_metadatas[i]["chunk"] if all_metadatas and all_metadatas[i] else 0,
                    )
                    for i in bm25_indices
                    if i < len(all_docs)
                ]

        return self._rrf_fuse(vec_chunks, bm25_chunks, top_k)

    @staticmethod
    def _results_to_chunks(docs: list[str], metadatas: list[dict]) -> list[Chunk]:
        return [
            Chunk(
                text=docs[i],
                source=metadatas[i]["source"] if metadatas and i < len(metadatas) else "unknown",
                chunk_index=metadatas[i]["chunk"] if metadatas and i < len(metadatas) else 0,
            )
            for i in range(len(docs))
        ]

    def _rrf_fuse(self, vec_chunks: list[Chunk], bm25_chunks: list[Chunk], top_k: int) -> list[Chunk]:
        k = 60
        scores: dict[str, float] = {}
        chunk_map: dict[str, Chunk] = {}

        for rank, chunk in enumerate(vec_chunks):
            scores[chunk.text] = scores.get(chunk.text, 0) + 1.0 / (k + rank)
            chunk_map[chunk.text] = chunk
        for rank, chunk in enumerate(bm25_chunks):
            scores[chunk.text] = scores.get(chunk.text, 0) + 1.0 / (k + rank)
            chunk_map[chunk.text] = chunk

        seen = list(dict.fromkeys(c.text for c in vec_chunks + bm25_chunks))
        seen.sort(key=lambda t: scores.get(t, 0), reverse=True)
        return [chunk_map[t] for t in seen[:top_k]]

    def rerank(self, query: str, chunks: list[Chunk], top_k: int = config.RAG_TOP_K_RERANK) -> list[Chunk]:
        if len(chunks) <= top_k:
            return chunks
        if self.reranker is None:
            return chunks[:top_k]

        scores = self.reranker.predict([(query, chunk.text) for chunk in chunks])
        scored = list(zip(chunks, scores))
        scored.sort(key=lambda item: item[1], reverse=True)
        return [chunk for chunk, _ in scored[:top_k]]

    def query(self, question: str, search_query: str | None = None) -> dict[str, Any]:
        retrieval_query = (search_query or question).strip()
        original_query = question.strip()

        chunks = self.retrieve(original_query)
        if retrieval_query and retrieval_query != original_query:
            rewritten_chunks = self.retrieve(retrieval_query)
            chunks = self._rrf_fuse(chunks, rewritten_chunks, config.RAG_TOP_K_RETRIEVE)

        rerank_query = retrieval_query if retrieval_query else original_query
        if retrieval_query and retrieval_query != original_query:
            rerank_query = f"{original_query}\n{retrieval_query}"

        best_chunks = self.rerank(rerank_query, chunks)
        return {
            "question": question,
            "search_query": retrieval_query or original_query,
            "context": best_chunks,
        }
