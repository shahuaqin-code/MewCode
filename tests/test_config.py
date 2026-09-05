"""配置层测试。"""

import re

import pytest

from mewcode.config import ConfigError, load_config

VALID_YAML = """\
providers:
  - name: deepseek
    protocol: anthropic
    model: deepseek-v4-pro
    base_url: https://api.deepseek.com/anthropic/
    api_key: ${TEST_MC_KEY}
    thinking: true
"""


@pytest.fixture
def config_file(tmp_path):
    def write(text: str):
        p = tmp_path / "config.yaml"
        p.write_text(text, encoding="utf-8")
        return p

    return write


def test_full_parse(config_file, monkeypatch):
    monkeypatch.setenv("TEST_MC_KEY", "secret-key")
    configs = load_config(config_file(VALID_YAML))
    assert len(configs) == 1
    c = configs[0]
    assert c.name == "deepseek"
    assert c.protocol == "anthropic"
    assert c.model == "deepseek-v4-pro"
    assert c.base_url == "https://api.deepseek.com/anthropic"  # 尾斜杠已去
    assert c.api_key == "secret-key"
    assert c.thinking is True
    assert "secret-key" not in repr(c)  # 密钥不进 repr


def test_thinking_defaults_false(config_file, monkeypatch):
    monkeypatch.setenv("TEST_MC_KEY", "k")
    yaml = VALID_YAML.replace("    thinking: true\n", "")
    configs = load_config(config_file(yaml))
    assert configs[0].thinking is False


def test_plaintext_api_key(config_file):
    yaml = VALID_YAML.replace("${TEST_MC_KEY}", "plain-key")
    configs = load_config(config_file(yaml))
    assert configs[0].api_key == "plain-key"


@pytest.mark.parametrize("field", ["name", "protocol", "model", "base_url", "api_key"])
def test_missing_required_field(config_file, field):
    # 清空字段值（保留 YAML 结构），触发缺字段/非法值报错
    yaml = re.sub(rf"^(\s*(-\s*)?{field}):.*", r'\1: ""', VALID_YAML, flags=re.M)
    with pytest.raises(ConfigError, match=field):
        load_config(config_file(yaml))


def test_invalid_protocol(config_file):
    yaml = VALID_YAML.replace("protocol: anthropic", "protocol: http")
    with pytest.raises(ConfigError, match="protocol"):
        load_config(config_file(yaml))


def test_bad_yaml(config_file):
    with pytest.raises(ConfigError, match="YAML"):
        load_config(config_file("providers: [unclosed"))


def test_missing_providers_key(config_file):
    with pytest.raises(ConfigError, match="providers"):
        load_config(config_file("foo: bar\n"))


def test_unset_env_var_errors(config_file):
    with pytest.raises(ConfigError, match="TEST_MC_KEY"):
        load_config(config_file(VALID_YAML))


def test_openai_thinking_warns(config_file, capsys, monkeypatch):
    monkeypatch.setenv("TEST_MC_KEY", "k")
    yaml = VALID_YAML.replace("protocol: anthropic", "protocol: openai")
    configs = load_config(config_file(yaml))
    assert configs[0].thinking is False
    assert "thinking 被忽略" in capsys.readouterr().err


def test_thinking_must_be_bool(config_file):
    yaml = VALID_YAML.replace("thinking: true", "thinking: 'yes'")
    with pytest.raises(ConfigError, match="thinking"):
        load_config(config_file(yaml))


def test_model_must_be_string(config_file):
    yaml = VALID_YAML.replace("model: deepseek-v4-pro", "model: 123")
    with pytest.raises(ConfigError, match="model"):
        load_config(config_file(yaml))


def test_missing_file(tmp_path):
    with pytest.raises(ConfigError, match="无法读取"):
        load_config(tmp_path / "nope.yaml")
