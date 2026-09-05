"""Provider 注册表：protocol → Provider 实现类。"""

from mewcode.providers.anthropic import AnthropicProvider
from mewcode.providers.openai import OpenAIProvider

PROTOCOLS = {
    "anthropic": AnthropicProvider,
    "openai": OpenAIProvider,
}

__all__ = ["PROTOCOLS"]
