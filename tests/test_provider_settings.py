"""供应商运行时配置与有效配置合并逻辑（无网络请求）。"""
import pytest

import config
import llm
import provider_settings


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    path = tmp_path / "provider_settings.json"
    monkeypatch.setattr(provider_settings, "SETTINGS_PATH", path)
    yield path


def test_roundtrip_update_and_get():
    provider_settings.update("deepseek", api_key="sk-test-1234")
    assert provider_settings.get("deepseek")["api_key"] == "sk-test-1234"

    provider_settings.update("deepseek", base_url="https://example.com/v1")
    entry = provider_settings.get("deepseek")
    assert entry["base_url"] == "https://example.com/v1"
    assert entry["api_key"] == "sk-test-1234"


def test_get_unknown_or_empty():
    assert provider_settings.get("deepseek") == {}
    provider_settings.update("minimax", models=[])
    assert provider_settings.get("minimax") == {}  # 空列表视为无覆盖


def test_clear_removes_entry():
    provider_settings.update("qwen", api_key="sk-q")
    provider_settings.clear("qwen")
    assert provider_settings.get("qwen") == {}


def test_corrupt_file_returns_empty(isolated_settings):
    isolated_settings.write_text("{broken", encoding="utf-8")
    assert provider_settings.load() == {}


def test_effective_provider_merges_overrides(monkeypatch):
    monkeypatch.setattr(provider_settings, "SETTINGS_PATH", isolated_settings_default())
    provider_settings.update("deepseek", api_key="sk-runtime", models=["m-a", "m-b"])

    eff = llm.get_effective_provider("deepseek")
    assert eff.api_key == "sk-runtime"
    assert eff.models == ["m-a", "m-b"]
    assert eff.default_model == "m-a"
    # base_url 未覆盖时沿用静态配置
    assert eff.base_url == "https://api.deepseek.com/v1"


def test_effective_provider_without_overrides(monkeypatch):
    monkeypatch.setattr(provider_settings, "SETTINGS_PATH", isolated_settings_default())
    eff = llm.get_effective_provider("deepseek")
    assert eff.api_key == config.PROVIDERS["deepseek"].api_key
    assert eff.models == config.PROVIDERS["deepseek"].models


def test_set_provider_config_clear(monkeypatch):
    monkeypatch.setattr(provider_settings, "SETTINGS_PATH", isolated_settings_default())
    llm.set_provider_config("deepseek", api_key="sk-temp")
    assert llm.get_effective_provider("deepseek").api_key == "sk-temp"

    llm.set_provider_config("deepseek", clear=True)
    assert llm.get_effective_provider("deepseek").api_key != "sk-temp"


def test_set_provider_config_unknown_provider():
    with pytest.raises(ValueError, match="未知供应商"):
        llm.set_provider_config("nonexistent", api_key="sk-x")


def test_mask_key():
    assert llm.mask_key("") == ""
    assert llm.mask_key("your-proxy-api-key") == ""
    assert llm.mask_key("sk-abcdefg1234") == "****1234"


def isolated_settings_default():
    """test_effective_* 用：由 autouse fixture 已隔离，直接返回当前路径。"""
    return provider_settings.SETTINGS_PATH
