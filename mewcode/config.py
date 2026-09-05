"""配置层：YAML 加载、校验、环境变量解析。"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

VALID_PROTOCOLS = ("anthropic", "openai")
REQUIRED_FIELDS = ("name", "protocol", "model", "base_url", "api_key")
ENV_VAR_PATTERN = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$")


class ConfigError(Exception):
    """配置错误，message 指明具体配置项。"""


@dataclass(frozen=True)
class ProviderConfig:
    name: str                 # 供应商标识名
    protocol: str             # "anthropic" | "openai"
    model: str
    base_url: str             # 服务根地址（无末尾斜杠）
    api_key: str = field(repr=False)  # 已解析的密钥；repr 不显示，绝不打印/写盘
    thinking: bool = False


def load_config(path: str | Path) -> list[ProviderConfig]:
    """加载并校验配置文件，返回 provider 配置列表。"""
    cfg_path = Path(path)
    try:
        text = cfg_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"无法读取配置文件 {cfg_path}: {exc}") from exc

    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"配置文件 YAML 格式错误: {exc}") from exc

    if not isinstance(data, dict) or "providers" not in data:
        raise ConfigError("配置文件缺少顶层 providers 列表")
    entries = data["providers"]
    if not isinstance(entries, list) or not entries:
        raise ConfigError("providers 必须是非空列表")

    return [_parse_provider(entry, i) for i, entry in enumerate(entries)]


def _parse_provider(entry: object, index: int) -> ProviderConfig:
    where = f"providers[{index}]"
    if not isinstance(entry, dict):
        raise ConfigError(f"{where} 必须是映射（含六个字段）")

    for key in REQUIRED_FIELDS:
        if key not in entry or entry[key] in (None, ""):
            raise ConfigError(f"{where} 缺少必填字段 {key}")

    for key in ("name", "model", "base_url", "api_key"):
        if not isinstance(entry[key], str):
            raise ConfigError(f"{where}.{key} 必须是字符串")

    protocol = entry["protocol"]
    if protocol not in VALID_PROTOCOLS:
        raise ConfigError(f"{where}.protocol 取值非法: {protocol}（仅支持 anthropic/openai）")

    thinking = entry.get("thinking", False)
    if not isinstance(thinking, bool):
        raise ConfigError(f"{where}.thinking 必须是布尔值")

    api_key = _resolve_api_key(entry["api_key"], where)

    if protocol == "openai" and thinking:
        print(f"警告: {where} protocol 为 openai 时 thinking 被忽略", file=sys.stderr)
        thinking = False

    return ProviderConfig(
        name=entry["name"],
        protocol=protocol,
        model=entry["model"],
        base_url=entry["base_url"].rstrip("/"),
        api_key=api_key,
        thinking=thinking,
    )


def _resolve_api_key(raw: str, where: str) -> str:
    match = ENV_VAR_PATTERN.match(raw)
    if not match:
        return raw
    var_name = match.group(1)
    value = os.environ.get(var_name)
    if value is None or value == "":
        raise ConfigError(f"{where}.api_key 引用的环境变量 {var_name} 未设置")
    return value
