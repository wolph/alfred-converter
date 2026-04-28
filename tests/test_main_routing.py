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
    assert data["items"][0]["title"] == (
        "RuntimeError: No results for '1 m in cm'"
    )


def test_comma_decimal_query_does_not_emit_error(monkeypatch):
    monkeypatch.setattr(main.constants, "DECIMAL_SEPARATOR", ",")

    response = main.run("5,2")

    assert response.items[0].title == "5,2"


def test_currency_query_routes_to_currency(monkeypatch, tmp_path):
    called = []

    def fake_convert_query(base_dir, query):
        called.append((base_dir, query))
        return main.output.Response(
            items=[
                main.output.Item(
                    title="2000 ISK = 13.908436 EUR",
                    arg="13.908436",
                )
            ]
        )

    monkeypatch.setenv("alfred_workflow_cache", str(tmp_path))
    monkeypatch.setattr(main.currency, "convert_query", fake_convert_query)

    response = main.run("2000 isk eur")

    assert response.items[0].title == "2000 ISK = 13.908436 EUR"
    assert called == [(str(tmp_path), "2000 isk eur")]


def test_default_currency_query_routes_to_currency(monkeypatch, tmp_path):
    called = []

    def fake_convert_query(base_dir, query):
        called.append((base_dir, query))
        return main.output.Response(
            items=[
                main.output.Item(
                    title="5 USD = 4.5 EUR",
                    arg="4.5",
                )
            ]
        )

    monkeypatch.setenv("alfred_workflow_cache", str(tmp_path))
    monkeypatch.setattr(main.currency, "convert_query", fake_convert_query)

    response = main.run("5 usd")

    assert response.items[0].title == "5 USD = 4.5 EUR"
    assert called == [(str(tmp_path), "5 usd")]


def test_default_currency_query_does_not_shadow_unit_source(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("alfred_workflow_cache", str(tmp_path))

    def fail_currency(*args, **kwargs):
        raise AssertionError("currency path touched")

    monkeypatch.setattr(main.currency, "convert_query", fail_currency)

    response = main.run("5 cup")

    assert any("cup" in item.title for item in response.items)


def test_regular_unit_query_does_not_touch_currency(monkeypatch, tmp_path):
    monkeypatch.setenv("alfred_workflow_cache", str(tmp_path))

    def fail_currency(*args, **kwargs):
        raise AssertionError("currency path touched")

    monkeypatch.setattr(main.currency, "convert_query", fail_currency)

    response = main.run("1 m in cm")

    assert any("centimeter" in item.title for item in response.items)


def test_update_command_routes_to_currency_update(monkeypatch, tmp_path):
    monkeypatch.setenv("alfred_workflow_cache", str(tmp_path))
    monkeypatch.setattr(
        main.currency,
        "update_command",
        lambda base_dir, query: main.output.Response(
            items=[
                main.output.Item(
                    title="Updated ISK currency rates",
                    valid=False,
                )
            ]
        ),
    )

    response = main.run("currency-update isk")

    assert response.items[0].title == "Updated ISK currency rates"


def test_malformed_update_command_routes_to_currency_update(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("alfred_workflow_cache", str(tmp_path))

    def fail_refresh(*args, **kwargs):
        raise AssertionError("refresh called")

    monkeypatch.setattr(main.currency, "fetch_rates", fail_refresh)
    monkeypatch.setattr(main.currency, "refresh_rates", fail_refresh)
    monkeypatch.setattr(main.currency, "manual_refresh_rates", fail_refresh)

    response = main.run("currency-update isk now")

    assert response.items[0].valid is False
    assert response.items[0].title == "Invalid currency update command"
