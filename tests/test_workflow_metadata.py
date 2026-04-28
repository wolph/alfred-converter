import plistlib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CURRENCY_UPDATE_SCRIPT = (
    "from converter import main\n"
    "main.scriptfilter('''currency-update {query}''')"
)
CLIPBOARD_UID = "06C9C4A9-38CE-441A-8D06-E2F2D8B39B60"


def load_info():
    with (REPO_ROOT / "info.plist").open("rb") as fh:
        return plistlib.load(fh)


def script_filters(info):
    return [
        obj
        for obj in info["objects"]
        if obj["type"] == "alfred.workflow.input.scriptfilter"
    ]


def test_script_filters_call_json_scriptfilter():
    info = load_info()

    for obj in script_filters(info):
        script = obj["config"]["script"]
        assert "from converter import main" in script
        assert "main.scriptfilter(" in script


def test_currency_update_command_exists_with_workflow_wiring():
    info = load_info()
    currency_update_filters = [
        obj
        for obj in script_filters(info)
        if obj["config"]["keyword"] == "currency-update"
    ]

    assert len(currency_update_filters) == 1

    currency_update_filter = currency_update_filters[0]
    uid = currency_update_filter["uid"]

    assert currency_update_filter["config"]["script"] == CURRENCY_UPDATE_SCRIPT
    assert info["connections"][uid] == [
        {
            "destinationuid": CLIPBOARD_UID,
            "modifiers": 0,
            "modifiersubtext": "",
            "vitoclose": False,
        }
    ]
    assert "xpos" in info["uidata"][uid]
    assert "ypos" in info["uidata"][uid]


def test_default_currency_targets_are_configurable():
    info = load_info()
    config = [
        item
        for item in info["userconfigurationconfig"]
        if item["variable"] == "CURRENCY_DEFAULT_TARGETS"
    ]

    assert len(config) == 1
    assert config[0]["config"]["default"] == "usd,eur,gbp,jpy,cny,cad,aud"
