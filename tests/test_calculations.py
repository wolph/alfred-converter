import pytest
from converter import convert, constants

EXPRESSIONS = {
    '1-0.5': '0.5',
    '.1 * 0.01': '0.001',
    'sqrt(4)*2': '4',
    'sqrt(4) * 2': '4',
    'sqrt(4)*2*sqrt(2^2^2)+2^3-2^5+2^3': '0',
    '(sqrt(sqrt(5)^2)^2^2)^(1/2)': '5',
    '(sqrt(sqrt(5)^2)^2^2)^1/2': '12.5',
    '10 meter in cm': 'meter 10 = centimeter 1000',
    '10 metre in cm': 'meter 10 = centimeter 1000',
    '''4'2" in inch''': 'inch 50 = inch 50',
    '''4'2 1/4" in ft''': 'inch 50.25 = foot 4 inch 9/4',
    '''4'2-1/4" in ft''': 'inch 50.25 = foot 4 inch 9/4',
    'cos(pi / 3)': '0.5',
    'cos(pi / 3) * 2': '1',
    '2 * cos(pi / 3)': '1',
    '11"': 'inch 11 = foot 0 inch 11',
    '12"': 'inch 12 = foot 1 inch 0',
    '13"': 'inch 13 = foot 1 inch 1',
    'log(10, 10)': '1',
    'log(100) / log(10)': '2',
}


@pytest.mark.parametrize('test', EXPRESSIONS.iteritems())
def test_working(test, monkeypatch):
    monkeypatch.setenv('UNITS_SIDE', 'left')
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
        else:
            print('%r != %r' % (expected_result, result['title']))

    if result:
        raise RuntimeError(
            '%r returned %r, expected: %r'
            % (expression, result['title'], expected_result)
        )
    else:
        raise RuntimeError(
            '%r didnt return, expected: %r' % (expression, expected_result)
        )
