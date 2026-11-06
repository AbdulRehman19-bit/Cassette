import os

from cassette.config import load_dotenv


def test_loads_values_without_overriding_and_ignores_junk(tmp_path, monkeypatch):
    monkeypatch.delenv("CASSETTE_T_A", raising=False)
    monkeypatch.setenv("CASSETTE_T_B", "keep")
    f = tmp_path / ".env"
    f.write_text('# c\nCASSETTE_T_A="x y"\nexport CASSETTE_T_B=new\n\nnot a line\n', encoding="utf-8")
    assert load_dotenv(f, tmp_path / "missing.env") == [f]
    assert os.environ["CASSETTE_T_A"] == "x y"
    assert os.environ["CASSETTE_T_B"] == "keep"
    monkeypatch.delenv("CASSETTE_T_A")
