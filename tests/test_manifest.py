"""清单逻辑：版本迁移、mtime 检测、坏清单容错。"""
import json

import config
import rag_engine


def make_engine() -> rag_engine.RAGEngine:
    return rag_engine.RAGEngine.__new__(rag_engine.RAGEngine)


def test_load_manifest_missing_file(tmp_path):
    rag_engine.MANIFEST_PATH = tmp_path / "manifest.json"
    eng = make_engine()
    manifest = eng._load_manifest()
    assert manifest == {"version": 0, "files": {}}


def test_load_manifest_roundtrip(tmp_path):
    rag_engine.MANIFEST_PATH = tmp_path / "manifest.json"
    eng = make_engine()
    manifest = eng._fresh_manifest()
    manifest["files"]["doc.md"] = 123.5
    eng._save_manifest(manifest)

    loaded = eng._load_manifest()
    assert loaded["version"] == config.INDEX_VERSION
    assert loaded["files"] == {"doc.md": 123.5}


def test_old_flat_manifest_triggers_version_mismatch(tmp_path):
    """旧版扁平结构（无 version/files 字段）应判定为需要重建。"""
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"_version": 2, "doc.md": 1.0}), encoding="utf-8")
    rag_engine.MANIFEST_PATH = path

    eng = make_engine()
    manifest = eng._load_manifest()
    assert manifest["version"] != config.INDEX_VERSION
    assert manifest["files"] == {}


def test_corrupt_manifest_recovers(tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text("{broken json", encoding="utf-8")
    rag_engine.MANIFEST_PATH = path

    eng = make_engine()
    manifest = eng._load_manifest()
    assert manifest == {"version": 0, "files": {}}


def test_needs_index_by_mtime(tmp_path):
    doc = tmp_path / "doc.txt"
    doc.write_text("hello", encoding="utf-8")

    files: dict[str, float] = {}
    assert rag_engine.RAGEngine._needs_index(doc, files) is True

    files[doc.name] = doc.stat().st_mtime
    assert rag_engine.RAGEngine._needs_index(doc, files) is False

    files[doc.name] = files[doc.name] - 10
    assert rag_engine.RAGEngine._needs_index(doc, files) is True


def test_needs_index_missing_file():
    from pathlib import Path

    missing = Path("does_not_exist.txt")
    assert rag_engine.RAGEngine._needs_index(missing, {}) is False
