"""YAML configuration with environment-backed secrets and safe diagnostics."""

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

import yaml


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    protocol: Literal["anthropic", "openai"]
    api_key: str = field(repr=False)
    model: str
    base_url: str | None = None
    thinking: bool = False


@dataclass
class Config:
    providers: list[ProviderConfig] = field(default_factory=list)


def load(path: str | Path = ".mewcode/config.yaml") -> Config:
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        raise ConfigError(
            "无法读取 .mewcode/config.yaml，请复制配置模板并填写。"
        ) from None
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        location = f"（第 {mark.line + 1} 行）" if mark else ""
        raise ConfigError(f"配置文件 YAML 格式错误{location}") from None
    if not isinstance(data, dict):
        raise ConfigError("配置必须包含 providers 列表")
    entries = data.get("providers")
    if not isinstance(entries, list) or not entries:
        raise ConfigError("providers 必须是非空列表")
    providers = []
    for index, entry in enumerate(entries):
        where = f"providers[{index}]"
        if not isinstance(entry, dict):
            raise ConfigError(f"{where} 必须是映射")
        for key in ("name", "protocol", "api_key", "model"):
            if not isinstance(entry.get(key), str) or not entry[key].strip():
                raise ConfigError(f"{where}.{key} 必须是非空字符串")
        if entry["protocol"] not in ("anthropic", "openai"):
            raise ConfigError(f"{where}.protocol 仅支持 anthropic/openai")
        if not isinstance(entry.get("thinking", False), bool):
            raise ConfigError(f"{where}.thinking 必须是布尔值")
        url = entry.get("base_url")
        if url is not None:
            try:
                parsed = urlsplit(url) if isinstance(url, str) else None
                valid = (
                    parsed
                    and parsed.scheme in ("http", "https")
                    and parsed.hostname
                    and not parsed.username
                    and not parsed.password
                    and not parsed.query
                    and not parsed.fragment
                )
                if not valid:
                    raise ValueError
                _ = parsed.port
            except ValueError:
                raise ConfigError(
                    f"{where}.base_url 必须是无凭据的 HTTP(S) 地址"
                ) from None
        api_key = entry["api_key"]
        reference = re.fullmatch(
            r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)", api_key
        )
        if reference:
            variable = reference.group(1) or reference.group(2)
            api_key = os.environ.get(variable, "")
            if not api_key.strip():
                raise ConfigError(
                    f"{where}.api_key 引用的环境变量 {variable} 未设置或为空"
                )
        elif api_key.startswith("$"):
            raise ConfigError(f"{where}.api_key 环境变量引用格式应为 ${{VARIABLE}}")
        providers.append(
            ProviderConfig(
                **{key: entry[key] for key in ("name", "protocol", "model")},
                api_key=api_key,
                base_url=url,
                thinking=entry.get("thinking", False),
            )
        )
    return Config(providers)
