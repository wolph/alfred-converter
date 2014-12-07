from converter import main


def test_convert():
    main.scriptfilter('5 * sin(pi/2) + 2 mm in m')

