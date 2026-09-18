from dataclasses import replace
from collections.abc import Generator

from openai import OpenAI

import provider_settings
from config import LLMProvider, PROVIDERS

REQUEST_TIMEOUT_SECONDS = 120.0
MODELS_TIMEOUT_SECONDS = 20.0

_PROVIDER_CACHE: dict[str, OpenAI] = {}


def _get_client(provider: LLMProvider) -> OpenAI:
    if provider.name not in _PROVIDER_CACHE:
        _PROVIDER_CACHE[provider.name] = OpenAI(
            api_key=provider.api_key,
            base_url=provider.base_url,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    return _PROVIDER_CACHE[provider.name]


def _invalidate_client(provider_name: str) -> None:
    """供应商配置变更后丢弃旧 client，避免复用过期的 Key/地址。"""
    _PROVIDER_CACHE.pop(provider_name, None)


def get_effective_provider(name: str) -> LLMProvider | None:
    """合并 .env 静态配置与本机运行时覆盖（provider_settings.json）。"""
    base = PROVIDERS.get(name)
    if base is None:
        return None
    overrides = provider_settings.get(name)
    if not overrides:
        return base

    models = overrides.get("models") or base.models
    return replace(
        base,
        api_key=overrides.get("api_key") or base.api_key,
        base_url=overrides.get("base_url") or base.base_url,
        models=models,
        default_model=models[0] if overrides.get("models") else base.default_model,
    )


def set_provider_config(
    name: str,
    api_key: str | None = None,
    base_url: str | None = None,
    clear: bool = False,
) -> LLMProvider:
    """保存供应商运行时配置并使其立即生效。返回更新后的有效配置。"""
    if name not in PROVIDERS:
        available = ", ".join(PROVIDERS.keys())
        raise ValueError(f"未知供应商 '{name}'，可选：{available}")
    if clear:
        provider_settings.clear(name)
    else:
        provider_settings.update(name, api_key=api_key, base_url=base_url)
    _invalidate_client(name)
    return get_effective_provider(name)


def fetch_models(provider_name: str) -> list[str]:
    """从供应商的 OpenAI 兼容 /models 接口拉取可用模型列表。"""
    provider = get_effective_provider(provider_name)
    if provider is None:
        available = ", ".join(PROVIDERS.keys())
        raise ValueError(f"未知供应商 '{provider_name}'，可选：{available}")
    if not _is_configured_api_key(provider.api_key):
        raise ValueError(f"供应商 '{provider_name}' 未配置 API Key")

    client = _get_client(provider)
    response = client.models.list(timeout=MODELS_TIMEOUT_SECONDS)
    models = sorted({m.id for m in response.data if getattr(m, "id", None)})
    if not models:
        raise ValueError("供应商未返回任何模型")
    return models


def save_fetched_models(provider_name: str, models: list[str]) -> None:
    """把从供应商拉取到的模型列表持久化，作为该供应商的有效模型清单。"""
    provider_settings.update(provider_name, models=models)
    _invalidate_client(provider_name)


def mask_key(api_key: str) -> str:
    """掩码展示已配置的 Key，只露末 4 位。"""
    if not _is_configured_api_key(api_key):
        return ""
    return f"****{api_key[-4:]}"


def _is_configured_api_key(api_key: str) -> bool:
    return bool(api_key and not api_key.startswith("your-"))


def _resolve_provider(provider_name: str) -> LLMProvider:
    provider = get_effective_provider(provider_name)
    if not provider:
        available = ", ".join(PROVIDERS.keys())
        raise ValueError(f"未知供应商 '{provider_name}'，可选：{available}")
    if not _is_configured_api_key(provider.api_key):
        raise ValueError(f"供应商 '{provider_name}' 未配置 API Key，请检查 .env 或在界面左上角配置。")
    return provider


def list_providers() -> dict[str, LLMProvider]:
    return dict(PROVIDERS)


def get_provider(name: str) -> LLMProvider | None:
    # 返回合并运行时配置后的有效供应商，Web 界面配置的 Key 对 CLI 同样生效
    return get_effective_provider(name)


def chat(
    provider_name: str,
    model: str | None = None,
    messages: list[dict] | None = None,
    temperature: float = 0.3,
    **kwargs,
) -> str:
    provider = _resolve_provider(provider_name)
    client = _get_client(provider)
    model_name = model or provider.default_model

    response = client.chat.completions.create(
        model=model_name,
        messages=messages or [],
        temperature=temperature,
        **kwargs,
    )

    return response.choices[0].message.content or ""


def chat_stream(
    provider_name: str,
    model: str | None = None,
    messages: list[dict] | None = None,
    temperature: float = 0.3,
    **kwargs,
) -> Generator[str, None, None]:
    provider = _resolve_provider(provider_name)
    client = _get_client(provider)
    model_name = model or provider.default_model

    stream = client.chat.completions.create(
        model=model_name,
        messages=messages or [],
        temperature=temperature,
        stream=True,
        **kwargs,
    )

    for chunk in stream:
        delta = chunk.choices[0].delta
        if delta.content:
            yield delta.content
