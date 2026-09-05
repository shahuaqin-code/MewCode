import pytest
import yaml

from mewcode.config import ConfigError, load


@pytest.fixture
def entry():
    return dict(name="test", protocol="openai", api_key="secret", model="model")


def write(tmp_path, data):
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(data))
    return path


def test_defaults_and_multiple(tmp_path, entry):
    cfg = load(write(tmp_path, {"providers": [entry, {**entry, "thinking": True}]}))
    assert len(cfg.providers) == 2
    assert cfg.providers[0].base_url is None
    assert cfg.providers[1].thinking is True
    assert "secret" not in repr(cfg)


@pytest.mark.parametrize(
    "field,value",
    [
        ("name", " "),
        ("api_key", None),
        ("model", 2),
        ("protocol", "invalid"),
        ("thinking", "true"),
        ("base_url", "ftp://host"),
        ("base_url", []),
        ("base_url", "https://user:secret@host"),
    ],
)
def test_invalid_fields(tmp_path, entry, field, value):
    entry[field] = value
    with pytest.raises(ConfigError, match=field):
        load(write(tmp_path, {"providers": [entry]}))


@pytest.mark.parametrize(
    "data", [None, [], {}, {"providers": []}, {"providers": [None]}]
)
def test_invalid_structure(tmp_path, data):
    with pytest.raises(ConfigError):
        load(write(tmp_path, data))


def test_missing_and_malformed_secret_safe(tmp_path):
    with pytest.raises(ConfigError):
        load(tmp_path / "missing")
    path = tmp_path / "bad"
    path.write_text("providers: [api_key: secret\n")
    with pytest.raises(ConfigError) as error:
        load(path)
    assert "secret" not in str(error.value)


@pytest.mark.parametrize("reference", ["${DEEPSEEK_API_KEY}", "$DEEPSEEK_API_KEY"])
def test_environment_key(tmp_path, entry, monkeypatch, reference):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "resolved-test-secret")
    entry["api_key"] = reference
    cfg = load(write(tmp_path, {"providers": [entry]}))
    assert cfg.providers[0].api_key == "resolved-test-secret"
    assert "resolved-test-secret" not in repr(cfg)


@pytest.mark.parametrize("value", [None, "", "   "])
def test_missing_environment_key(tmp_path, entry, monkeypatch, value):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    if value is not None:
        monkeypatch.setenv("DEEPSEEK_API_KEY", value)
    entry["api_key"] = "${DEEPSEEK_API_KEY}"
    with pytest.raises(ConfigError, match="DEEPSEEK_API_KEY"):
        load(write(tmp_path, {"providers": [entry]}))


def test_invalid_environment_reference(tmp_path, entry):
    entry["api_key"] = "${BROKEN"
    with pytest.raises(ConfigError, match="引用格式"):
        load(write(tmp_path, {"providers": [entry]}))
