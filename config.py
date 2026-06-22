import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent
KNOWLEDGE_DIR = BASE_DIR / "knowledge"
CHROMA_DIR = BASE_DIR / "chroma_db"

EMBEDDING_MODEL = "shibing624/text2vec-base-chinese"
CROSS_ENCODER_MODEL = "BAAI/bge-reranker-base"

CHROMA_COLLECTION = "knowledge_base"
CHROMA_SPACE = "ip"

RAG_TOP_K_RETRIEVE = 10
RAG_TOP_K_RERANK = 3


@dataclass
class LLMProvider:
    name: str
    display_name: str
    base_url: str
    api_key: str
    models: list[str]
    default_model: str


def _resolve_api_key(env_var: str, default: str = "") -> str:
    return os.getenv(env_var, default) or ""


PROVIDERS: dict[str, LLMProvider] = {
    "cli-proxy": LLMProvider(
        name="cli-proxy",
        display_name="CLIProxyAPI (本地代理)",
        base_url=os.getenv("LLM_BASE_URL", "http://localhost:8317/v1"),
        api_key=os.getenv("LLM_API_KEY", "your-proxy-api-key"),
        models=[
            "gemini-2.5-flash",
            "gemini-2.5-pro",
            "gemini-3-pro-preview",
            "gemini-3.1-pro-preview",
        ],
        default_model="gemini-2.5-flash",
    ),
    "deepseek": LLMProvider(
        name="deepseek",
        display_name="DeepSeek",
        base_url="https://api.deepseek.com/v1",
        api_key=_resolve_api_key("DEEPSEEK_API_KEY"),
        models=["deepseek-chat", "deepseek-reasoner", "deepseek-v4-flash"],
        default_model="deepseek-v4-flash",
    ),
    "minimax": LLMProvider(
        name="minimax",
        display_name="MiniMax",
        base_url="https://api.minimax.chat/v1",
        api_key=_resolve_api_key("MINIMAX_API_KEY"),
        models=["minimax-text-01", "minimax-abab6.5s-chat"],
        default_model="minimax-text-01",
    ),
    "moonshot": LLMProvider(
        name="moonshot",
        display_name="Moonshot (Kimi)",
        base_url="https://api.moonshot.cn/v1",
        api_key=_resolve_api_key("MOONSHOT_API_KEY"),
        models=["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"],
        default_model="moonshot-v1-8k",
    ),
    "openrouter": LLMProvider(
        name="openrouter",
        display_name="OpenRouter",
        base_url="https://openrouter.ai/api/v1",
        api_key=_resolve_api_key("OPENROUTER_API_KEY"),
        models=["openai/gpt-4o", "anthropic/claude-sonnet-4", "google/gemini-2.5-flash"],
        default_model="openai/gpt-4o",
    ),
    "qwen": LLMProvider(
        name="qwen",
        display_name="通义千问 (Qwen)",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key=_resolve_api_key("QWEN_API_KEY"),
        models=["qwen-turbo", "qwen-plus", "qwen-max"],
        default_model="qwen-plus",
    ),
}


DEFAULT_PROVIDER = os.getenv("LLM_PROVIDER", "cli-proxy")
