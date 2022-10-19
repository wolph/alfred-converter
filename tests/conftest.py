import pytest
from converter import convert, constants


@pytest.fixture(scope='session')
def units():
    units = convert.Units()
    units.load(constants.UNITS_XML_FILE)
    return units

