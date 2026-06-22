from collections.abc import Generator

from openai import OpenAI

from config import LLMProvider, PROVIDERS

_PROVIDER_CACHE: dict[str, OpenAI] = {}


def _get_client(provider: LLMProvider) -> OpenAI:
    if provider.name not in _PROVIDER_CACHE:
        _PROVIDER_CACHE[provider.name] = OpenAI(
            api_key=provider.api_key,
            base_url=provider.base_url,
        )
    return _PROVIDER_CACHE[provider.name]


def _is_configured_api_key(api_key: str) -> bool:
    return bool(api_key and not api_key.startswith("your-"))


def _resolve_provider(provider_name: str) -> LLMProvider:
    provider = PROVIDERS.get(provider_name)
    if not provider:
        available = ", ".join(PROVIDERS.keys())
        raise ValueError(f"未知供应商 '{provider_name}'，可选：{available}")
    if not _is_configured_api_key(provider.api_key):
        raise ValueError(f"供应商 '{provider_name}' 未配置 API Key，请检查 .env。")
    return provider


def list_providers() -> dict[str, LLMProvider]:
    return dict(PROVIDERS)


def get_provider(name: str) -> LLMProvider | None:
    return PROVIDERS.get(name)


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
