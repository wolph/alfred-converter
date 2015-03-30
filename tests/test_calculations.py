import pytest
from converter import convert, constants

EXPRESSIONS = {
    '.1 * 0.01': '0.001',
    'sqrt(4)*2': '4',
    'sqrt(4) * 2': '4',
    'sqrt(4)*2*sqrt(2^2^2)+2^3-2^5+2^3': '0',
    '(sqrt(sqrt(5)^2)^2^2)^(1/2)': '5',
    '(sqrt(sqrt(5)^2)^2^2)^1/2': '12.5',
    '10 meter in cm': 'meter 10 = centimeter 1000',
    '10 metre in cm': 'meter 10 = centimeter 1000',
}


@pytest.mark.parametrize('test', EXPRESSIONS.iteritems())
def test_working(test):
    # Remove comments if needed
    expression, expected_result = test
    expression = expression.split('#')[0]

    units = convert.Units()
    units.load(constants.UNITS_XML_FILE)

    # Execute the expression
    result = None
    for result in convert.main(units, expression, dict):
        if result['title'] == expected_result:
            return True

    if result:
        raise RuntimeError('%r returned %r, expected: %r' % (
            expression, result['title'], expected_result))
    else:
        raise RuntimeError('%r didnt return, expected: %r' % (
            expression, expected_result))


