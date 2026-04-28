import json

from converter import main


def test_convert(capsys):
    main.scriptfilter('5 * sin(pi/2) + 2 mm in m')
    data = json.loads(capsys.readouterr().out)
    assert data["items"]
    assert data["items"][0]["title"]
