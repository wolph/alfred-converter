import json
from decimal import Decimal

from converter import output


def test_item_to_alfred_json_contains_copy_fields():
    item = output.Item(
        title="10 meter = 1000 centimeter",
        subtitle="Action this item to copy the converted value to the clipboard",
        arg="1000",
        uid="m to cm",
        icon="icons/scale6.png",
        autocomplete="1000 centimeter",
    )

    data = item.to_alfred()

    assert data == {
        "uid": "m to cm",
        "title": "10 meter = 1000 centimeter",
        "subtitle": "Action this item to copy the converted value to the clipboard",
        "arg": "1000",
        "valid": True,
        "autocomplete": "1000 centimeter",
        "icon": {"path": "icons/scale6.png"},
        "text": {
            "copy": "1000",
            "largetype": "1000",
        },
    }


def test_response_renders_items_and_skipknowledge():
    response = output.Response(
        items=[output.Item(title="2", arg="2", uid="calc:2")],
        skipknowledge=True,
    )

    data = json.loads(output.render_json(response))

    assert data == {
        "skipknowledge": True,
        "items": [
            {
                "uid": "calc:2",
                "title": "2",
                "arg": "2",
                "valid": True,
                "text": {
                    "copy": "2",
                    "largetype": "2",
                },
            }
        ],
    }


def test_legacy_create_item_factory_maps_attrib_to_item():
    create_item = output.item_creator()

    item = create_item(
        title="0xa",
        subtitle="Action this item to copy the HEX value to the clipboard",
        icon="icons/calculator63.png",
        attrib={
            "uid": "0xa",
            "arg": "0xa",
            "valid": "yes",
            "autocomplete": "0xa",
        },
    )

    assert item == output.Item(
        title="0xa",
        subtitle="Action this item to copy the HEX value to the clipboard",
        arg="0xa",
        uid="0xa",
        valid=True,
        icon="icons/calculator63.png",
        autocomplete="0xa",
    )


def test_item_without_optional_fields_renders_minimal_json():
    assert output.Item(title="No results", valid=False).to_alfred() == {
        "title": "No results",
        "valid": False,
    }


def test_item_uses_custom_copy_text_when_provided():
    item = output.Item(
        title="display",
        arg="argument",
        text_copy="",
        text_largetype="",
    )

    assert item.to_alfred()["text"] == {
        "copy": "",
        "largetype": "",
    }


def test_item_preserves_empty_optional_fields():
    item = output.Item(
        title="empty fields",
        subtitle="",
        icon="",
        autocomplete="",
    )

    assert item.to_alfred() == {
        "title": "empty fields",
        "valid": True,
        "subtitle": "",
        "autocomplete": "",
        "icon": {"path": ""},
    }


def test_response_renders_rerun_without_skipknowledge():
    assert output.Response(rerun=0.5).to_alfred() == {
        "items": [],
        "rerun": 0.5,
    }


def test_legacy_create_item_factory_defaults_to_valid_item():
    create_item = output.item_creator()

    assert create_item(title=2) == output.Item(title="2", valid=True)


def test_legacy_create_item_factory_accepts_boolean_valid():
    create_item = output.item_creator()

    assert create_item(title="invalid", attrib={"valid": False}) == output.Item(
        title="invalid",
        valid=False,
    )


def test_legacy_create_item_factory_stringifies_non_none_attrib_values():
    create_item = output.item_creator()

    item = create_item(
        title="decimal result",
        attrib={
            "arg": Decimal("1.5"),
            "uid": 123,
            "autocomplete": Decimal("1.5"),
            "valid": "yes",
        },
    )

    assert item.arg == "1.5"
    assert item.uid == "123"
    assert item.autocomplete == "1.5"

    data = json.loads(output.render_json(output.Response(items=[item])))

    assert data["items"][0]["arg"] == "1.5"
    assert data["items"][0]["uid"] == "123"
    assert data["items"][0]["autocomplete"] == "1.5"


def test_write_json_writes_response_to_stdout(capsys):
    output.write_json(output.Response(items=[output.Item(title="pi", arg="3.14")]))

    assert json.loads(capsys.readouterr().out) == {
        "items": [
            {
                "title": "pi",
                "arg": "3.14",
                "valid": True,
                "text": {
                    "copy": "3.14",
                    "largetype": "3.14",
                },
            }
        ]
    }
