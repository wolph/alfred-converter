import json

from converter import main


def test_scriptfilter_emits_json(capsys, monkeypatch, tmp_path):
    monkeypatch.setenv("alfred_workflow_cache", str(tmp_path))
    main.scriptfilter("1 + 1")

    stdout = capsys.readouterr().out
    data = json.loads(stdout)

    assert data["skipknowledge"] is True
    assert data["items"][0]["title"] == "2"
    assert data["items"][0]["arg"] == "2"


def test_scriptfilter_errors_are_valid_json(capsys, monkeypatch):
    def explode(query):
        raise RuntimeError("boom")

    monkeypatch.setattr(main, "run", explode)
    main.scriptfilter("1 m in cm")

    data = json.loads(capsys.readouterr().out)

    assert data["items"][0]["valid"] is False
    assert data["items"][0]["title"] == "RuntimeError: boom"


def test_scriptfilter_empty_results_are_valid_json_error(capsys, monkeypatch):
    def no_results(units, query, create_item):
        return iter(())

    monkeypatch.setattr(main, "load_units", object)
    monkeypatch.setattr(main.convert, "main", no_results)

    main.scriptfilter("1 m in cm")

    data = json.loads(capsys.readouterr().out)

    assert len(data["items"]) == 1
    assert data["items"][0]["valid"] is False
    assert data["items"][0]["title"] == "RuntimeError: No results for '1 m in cm'"
