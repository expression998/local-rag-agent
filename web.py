from __future__ import annotations

import argparse
import json
import logging
import mimetypes
import uuid
from collections import OrderedDict
from dataclasses import asdict
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from typing import Any
from urllib.parse import unquote

import config
from llm import chat_stream, list_providers
from query_rewrite import rewrite_query
from rag_engine import Chunk, RAGEngine
from sessions import SessionStore


BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"
SUPPORTED_UPLOAD_EXTS = {".md", ".txt", ".pdf", ".docx"}
HISTORY_LIMIT = 12
MAX_SESSIONS = 128
MAX_UPLOAD_BYTES = 20 * 1024 * 1024

PROMPT_TEMPLATE = """你是一位严谨的知识库问答助手。
请根据对话历史、用户问题和相关文档片段，生成准确、简洁、可追溯的中文回答。

{history}
用户问题：
{question}

相关片段：
{context}

回答要求：
1. 只基于相关片段作答，片段不足以支持结论时请明确说明不知道。
2. 不要编造文档中没有的信息。
3. 如果引用了某个片段，请在相关句子末尾标注来源，例如 [来源: example.md - 片段 3]。
"""

DISPLAY_NAMES = {
    "cli-proxy": "CLIProxyAPI 本地代理",
    "deepseek": "DeepSeek",
    "minimax": "MiniMax",
    "moonshot": "Moonshot / Kimi",
    "openrouter": "OpenRouter",
    "qwen": "通义千问 Qwen",
}


class AppState:
    def __init__(self) -> None:
        self._engine: RAGEngine | None = None
        self._engine_lock = Lock()
        self._sessions: OrderedDict[str, list[dict[str, str]]] = OrderedDict()
        self._sessions_lock = Lock()
        self.store = SessionStore()

    def engine(self) -> RAGEngine:
        with self._engine_lock:
            if self._engine is None:
                self._engine = RAGEngine()
                self._engine.index_directory()
            return self._engine

    def reindex(self, force: bool = False) -> int:
        with self._engine_lock:
            if self._engine is None:
                self._engine = RAGEngine()
            return self._engine.index_directory(force=force)

    def engine_loaded(self) -> bool:
        with self._engine_lock:
            return self._engine is not None

    def chunk_count(self) -> int | None:
        with self._engine_lock:
            if self._engine is None:
                return None
            return self._engine.collection.count()

    def history(self, session_id: str) -> list[dict[str, str]]:
        with self._sessions_lock:
            history = self._sessions.get(session_id)
            if history is None:
                return []
            self._sessions.move_to_end(session_id)
            return list(history)

    def append_history(self, session_id: str, question: str, answer: str) -> None:
        with self._sessions_lock:
            history = self._sessions.setdefault(session_id, [])
            self._sessions.move_to_end(session_id)
            history.append({"role": "user", "content": question})
            history.append({"role": "assistant", "content": answer})
            if len(history) > HISTORY_LIMIT:
                del history[: len(history) - HISTORY_LIMIT]
            while len(self._sessions) > MAX_SESSIONS:
                self._sessions.popitem(last=False)
        self.store.append(session_id, question, answer)

    def clear_history(self, session_id: str) -> None:
        with self._sessions_lock:
            self._sessions.pop(session_id, None)
        self.store.delete(session_id)


STATE = AppState()


def build_prompt(question: str, chunks: list[Chunk], history: list[dict[str, str]]) -> str:
    history_text = ""
    if history:
        lines = []
        for message in history:
            role = "用户" if message["role"] == "user" else "助手"
            lines.append(f"{role}: {message['content']}")
        history_text = "对话历史：\n" + "\n".join(lines) + "\n"

    context_lines = []
    for index, chunk in enumerate(chunks, 1):
        context_lines.append(
            f"[片段 {index} 来源: {chunk.source} - 片段 {chunk.chunk_index}]\n{chunk.text}"
        )

    return PROMPT_TEMPLATE.format(
        history=history_text,
        question=question,
        context="\n\n".join(context_lines),
    )


def chunk_to_dict(chunk: Chunk) -> dict[str, Any]:
    return {
        "source": chunk.source,
        "chunk_index": chunk.chunk_index,
        "text": chunk.text,
    }


def configured_api_key(api_key: str) -> bool:
    return bool(api_key and not api_key.startswith("your-"))


def knowledge_files() -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    for path in sorted(config.KNOWLEDGE_DIR.iterdir()):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_UPLOAD_EXTS:
            continue
        stat = path.stat()
        files.append(
            {
                "name": path.name,
                "extension": path.suffix.lower(),
                "size": stat.st_size,
                "modified": stat.st_mtime,
            }
        )
    return files


def remove_knowledge_file(name: str) -> int:
    """删除知识文件并移除其索引片段。返回移除的片段数。"""
    safe = Path(name).name
    if not safe or safe != name or safe.startswith("."):
        raise ValueError("非法文件名")
    target = config.KNOWLEDGE_DIR / safe
    if not target.is_file():
        raise ValueError(f"文件不存在：{safe}")
    target.unlink()
    return STATE.engine().remove_file(safe)


class RAGWebHandler(SimpleHTTPRequestHandler):
    server_version = "RAGWeb/0.1"

    def translate_path(self, path: str) -> str:
        if path == "/":
            return str(STATIC_DIR / "index.html")
        clean_path = path.split("?", 1)[0].split("#", 1)[0].lstrip("/")
        return str(STATIC_DIR / clean_path)

    def do_GET(self) -> None:
        if self.path.startswith("/api/providers"):
            self.send_json({"providers": self._providers_payload(), "default_provider": config.DEFAULT_PROVIDER})
            return
        if self.path.startswith("/api/knowledge"):
            self.send_json({"files": knowledge_files()})
            return
        if self.path.startswith("/api/status"):
            self.send_json(self._status_payload())
            return
        if self.path.startswith("/api/sessions"):
            parts = [p for p in self.path.split("?")[0].split("/") if p]
            if len(parts) == 2:
                self.send_json({"sessions": STATE.store.list_sessions()})
                return
            if len(parts) == 4 and parts[3] == "messages":
                self.send_json({"messages": STATE.store.messages(parts[2])})
                return
            self.send_error(HTTPStatus.NOT_FOUND, "Session endpoint not found")
            return
        return super().do_GET()

    def do_POST(self) -> None:
        if self.path.startswith("/api/chat"):
            payload = self.read_json_body()
            self.stream_chat(payload)
            return
        if self.path.startswith("/api/upload"):
            self.handle_upload()
            return
        if self.path.startswith("/api/knowledge/delete"):
            payload = self.read_json_body()
            name = str(payload.get("name") or "")
            try:
                removed = remove_knowledge_file(name)
                self.send_json({"ok": True, "removed_chunks": removed, "status": self._status_payload()})
            except ValueError as exc:
                self.send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            except Exception as exc:
                self.send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        if self.path.startswith("/api/reindex"):
            payload = self.read_json_body()
            force = bool(payload.get("force", False))
            try:
                count = STATE.reindex(force=force)
                self.send_json({"ok": True, "indexed_chunks": count, "status": self._status_payload()})
            except Exception as exc:
                self.send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        if self.path.startswith("/api/session/clear"):
            payload = self.read_json_body()
            session_id = str(payload.get("session_id") or "")
            if session_id:
                STATE.clear_history(session_id)
            self.send_json({"ok": True})
            return
        self.send_error(HTTPStatus.NOT_FOUND, "API endpoint not found")

    def handle_upload(self) -> None:
        try:
            raw_name = unquote(self.headers.get("X-Filename", "") or "")
            name = Path(raw_name).name
            if not name or name.startswith("."):
                raise ValueError("缺少合法文件名")
            if Path(name).suffix.lower() not in SUPPORTED_UPLOAD_EXTS:
                raise ValueError(f"不支持的文件类型，仅支持 {' '.join(sorted(SUPPORTED_UPLOAD_EXTS))}")

            length = int(self.headers.get("Content-Length", "0") or "0")
            if length <= 0:
                raise ValueError("上传内容为空")
            if length > MAX_UPLOAD_BYTES:
                raise ValueError(f"文件过大（上限 {MAX_UPLOAD_BYTES // 1024 // 1024}MB）")

            data = self.rfile.read(length)
            target = config.KNOWLEDGE_DIR / name
            target.write_bytes(data)
            count = STATE.reindex(force=False)
            self.send_json({"ok": True, "file": name, "indexed_chunks": count, "status": self._status_payload()})
        except ValueError as exc:
            self.send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self.send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def guess_type(self, path: str) -> str:
        if path.endswith(".js"):
            return "text/javascript; charset=utf-8"
        if path.endswith(".css"):
            return "text/css; charset=utf-8"
        if path.endswith(".html"):
            return "text/html; charset=utf-8"
        return mimetypes.guess_type(path)[0] or "application/octet-stream"

    def read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def stream_chat(self, payload: dict[str, Any]) -> None:
        question = str(payload.get("question") or "").strip()
        provider_name = str(payload.get("provider") or config.DEFAULT_PROVIDER)
        model = str(payload.get("model") or "").strip() or None
        session_id = str(payload.get("session_id") or uuid.uuid4())

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.end_headers()

        client_gone = False

        def write_event(event: str, data: dict[str, Any]) -> bool:
            nonlocal client_gone
            if client_gone:
                return False
            try:
                line = json.dumps({"event": event, **data}, ensure_ascii=False) + "\n"
                self.wfile.write(line.encode("utf-8"))
                self.wfile.flush()
                return True
            except (BrokenPipeError, ConnectionResetError, OSError):
                # 客户端已断开：停止写流。半截回答不入会话历史。
                client_gone = True
                return False

        if not question:
            write_event("error", {"message": "请输入问题。"})
            return

        try:
            history = STATE.history(session_id)
            rewrite = rewrite_query(provider_name, model, question, history)

            if not write_event("status", {"message": "正在检索知识库..."}):
                return
            engine = STATE.engine()
            result = engine.query(question, search_query=rewrite.search_query)
            chunks = result["context"]

            if not chunks:
                write_event("sources", {"sources": []})
                write_event("done", {"answer": "没有找到相关文档片段。", "session_id": session_id})
                return

            write_event("sources", {"sources": [chunk_to_dict(chunk) for chunk in chunks]})
            write_event("status", {"message": "正在生成回答..."})

            prompt = build_prompt(question, chunks, history)
            answer = ""
            for token in chat_stream(
                provider_name=provider_name,
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
            ):
                answer += token
                if not write_event("token", {"token": token}):
                    return

            STATE.append_history(session_id, question, answer)
            write_event("done", {"answer": answer, "session_id": session_id})
        except Exception as exc:
            write_event("error", {"message": str(exc)})

    def _providers_payload(self) -> list[dict[str, Any]]:
        providers = []
        for name, provider in list_providers().items():
            data = asdict(provider)
            data.pop("api_key", None)
            data["display_name"] = DISPLAY_NAMES.get(name, provider.display_name)
            data["configured"] = configured_api_key(provider.api_key)
            providers.append(data)
        return providers

    def _status_payload(self) -> dict[str, Any]:
        return {
            "engine_loaded": STATE.engine_loaded(),
            "knowledge_dir": str(config.KNOWLEDGE_DIR),
            "file_count": len(knowledge_files()),
            "chunk_count": STATE.chunk_count(),
        }


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    parser = argparse.ArgumentParser(description="启动 RAG Agent Web 前端")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), RAGWebHandler)
    url = f"http://{args.host}:{args.port}"
    print(f"RAG Agent Web is running at {url}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
