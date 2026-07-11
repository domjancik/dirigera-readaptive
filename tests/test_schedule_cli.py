from dirigera_readaptive.schedule_cli import load_token


def test_load_token_reads_env_first(tmp_path, monkeypatch):
    token_file = tmp_path / "token"
    token_file.write_text("file-token\n", encoding="utf-8")
    monkeypatch.setenv("DIRIGERA_TOKEN", "env-token")

    assert load_token("DIRIGERA_TOKEN", token_file) == "env-token"


def test_load_token_reads_file_when_env_missing(tmp_path, monkeypatch):
    token_file = tmp_path / "token"
    token_file.write_text("file-token\n", encoding="utf-8")
    monkeypatch.delenv("DIRIGERA_TOKEN", raising=False)

    assert load_token("DIRIGERA_TOKEN", token_file) == "file-token"


def test_load_token_rejects_missing_token(monkeypatch):
    monkeypatch.delenv("DIRIGERA_TOKEN", raising=False)

    try:
        load_token("DIRIGERA_TOKEN")
    except ValueError as error:
        assert "DIRIGERA_TOKEN" in str(error)
    else:
        raise AssertionError("expected missing token error")
