import pytest
from converter import convert, constants


TESTS = '''
1m in cm # Just a simple conversion
2^30 byte # Using powers before conversion
5' # Converting units with special characters
20" # Like above
5 * cos(pi + 2) # Executing mathematical functions
5 * pi + 2 mm in m # Mathematical constants with unit conversion
1 * cos(pi/2) - sin(pi^2) # More advanced mathematical expressions
ln(e^10) # Testing the ln(x) alias of log _e(x)
log(e^10) # The normal log method
5+3^2" in mm # Testing math with unit conversion
1 + 2 / 3 * 4) mm^2 in cm^2 # Unbalanced paranthesis with unit conversion
((1 + 2 / 3 * 4) mm^2 in cm^2 # Unbalanced paranthesis the other way
2^3 cm^2 in mm^2 # Test units with powers
10 m/s in mm/s # Test units with multiple sub-units
0b1010 + 0xA - 050 # Test calculations with hex, oct and binary numbers
'''.split('\n')


@pytest.mark.parametrize('test', TESTS)
def test_working(test):
    # Remove comments if needed
    test = test.split('#')[0]

    units = convert.Units()
    units.load(constants.UNITS_XML_FILE)

    # Execute the test
    for result in convert.main(units, test, dict):
        print result


