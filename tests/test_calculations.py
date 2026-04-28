import pytest

from converter import constants, convert, safe_math

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
    '16"': 'inch 16 = foot 1 inch 4',
    'log(10, 10)': '1',
    'log(100) / log(10)': '2',
    'log10(100)': '2',
    'log2(16)': '4',
    '0f': 'degree Fahrenheit 0 = degree Fahrenheit -0',
    '113 in to ft': 'inch 113 = foot 9 inch 5',
    '100 pounds to ounces': 'pounds mass 100 = ounce mass 1600',
    '113.125 in to ft': '113.125 inch = 9 foot 5 1/8 inch',
    '10 ft to mm': '10 foot = 3048 millimeters',
    '1/4"': '0.25 inch = 1/4 inch',
    '1/200"': '0.005 inch = 5 mil, a thousandth of an inch',
    '0f in c': '0 degree Fahrenheit = -17.777778 degrees Celsius',
    '10f in c': '10 degree Fahrenheit = -12.222222 degrees Celsius',
    '0x1f': '31',
    '(10 * 20) mm in cm': '200 millimeters = 20 centimeter',
}
SINGULAR_EXPRESSIONS = {
    '100 pounds to ounces': 'pounds mass 100 = ounce mass 1600',
}

DECIMAL_EXPRESSIONS = {
    '1.23': '1,23',
    '1.23 * 2': '2,46',
    '2 * 1.23': '2,46',
}


def auto_side(monkeypatch, expected):
    if expected[0].isdigit():
        monkeypatch.setenv('UNITS_SIDE', 'right')
    else:
        monkeypatch.setenv('UNITS_SIDE', 'left')


def get_results(units, expression, expected):
    results = list(convert.main(units, expression, dict))

    print('Results:')
    for result in results:
        print(result['title'])

    print('Expected: %r' % expected)

    return results


@pytest.mark.parametrize('expression, expected', EXPRESSIONS.items())
def test_working(expression, expected, monkeypatch, units):
    auto_side(monkeypatch, expected)

    # Execute the expression
    result = None
    # sourcery skip: no-loop-in-tests
    for result in get_results(units, expression, expected):
        # sourcery skip: no-conditionals-in-tests
        if result['title'] == expected:
            return True
        else:
            print('%r != %r' % (expected, result['title']))

    if result:
        raise RuntimeError(
            '%r returned %r, expected: %r'
            % (expression, result['title'], expected)
        )
    else:
        raise RuntimeError(
            '%r didnt return, expected: %r' % (expression, expected)
        )


@pytest.mark.parametrize('expression, expected', SINGULAR_EXPRESSIONS.items())
def test_expected_singular(expression, expected, monkeypatch, units):
    auto_side(monkeypatch, expected)
    print('Expected: %r' % expected)

    # Execute the expression
    results = get_results(units, expression, expected)
    assert len(results) == 1, 'Expected a single result, got: %r' % results
    result, = results
    assert result['title'] == expected, \
        ('%r returned %r, expected: %r') \
        % (expression, result['title'], expected)


@pytest.mark.parametrize('expression, expected', DECIMAL_EXPRESSIONS.items())
def test_decimal_separator(expression, expected, monkeypatch, units):
    auto_side(monkeypatch, expected)
    monkeypatch.setattr(constants, 'DECIMAL_SEPARATOR', ',')

    print('sep', constants.DECIMAL_SEPARATOR, expression)

    # Execute the expression
    result = None
    for result in get_results(units, expression, expected):
        if result['title'] == expected:
            return True
        else:
            print('%r != %r' % (expected, result['title']))

    if result:
        raise RuntimeError(
            '%r returned %r, expected: %r'
            % (expression, result['title'], expected)
        )
    else:
        raise RuntimeError(
            '%r didnt return, expected: %r' % (expression, expected)
        )


def test_seconds_prioritize_minute_conversion(monkeypatch, units):
    monkeypatch.setenv("UNITS_SIDE", "right")
    titles = [
        item["title"]
        for item in convert.main(units, "100 s", dict)
    ]

    assert titles[0] == "100 second = 1.666667 minutes"
    assert "100 second = 1 hundred seconds" not in titles[:5]
    assert "100 second = 10000 ten milli second" not in titles[:5]


def test_rare_time_units_are_filtered(monkeypatch, units):
    monkeypatch.setenv("UNITS_SIDE", "right")
    titles = [
        item["title"]
        for item in convert.main(units, "0.02 s", dict)
    ]

    assert all("ten milli second" not in title for title in titles)
    assert all("hundred seconds" not in title for title in titles)


def test_explicit_blacklisted_target_returns_no_results(units):
    assert list(convert.main(units, "1 s to cs", dict)) == []


def test_explicit_digit_prefixed_blacklisted_target_returns_no_results(units):
    assert list(convert.main(units, "1 s to 100ka", dict)) == []


def test_explicit_unknown_target_returns_no_results(units):
    assert list(convert.main(units, "1 s to xyz", dict)) == []


def test_explicit_metric_identity_target_is_first(monkeypatch, units):
    monkeypatch.setenv("UNITS_SIDE", "right")
    titles = [
        item["title"]
        for item in convert.main(units, "10 m in m", dict)
    ]

    assert titles[0] == "10 meter = 10 meter"


def test_explicit_time_identity_target_is_first(monkeypatch, units):
    monkeypatch.setenv("UNITS_SIDE", "right")
    titles = [
        item["title"]
        for item in convert.main(units, "100 s to s", dict)
    ]

    assert titles[0] == "100 second = 100 second"


def test_explicit_target_match_beats_identity(monkeypatch, units):
    monkeypatch.setenv("UNITS_SIDE", "right")
    titles = [
        item["title"]
        for item in convert.main(units, "1 kg to g", dict)
    ]

    assert titles[0] == "1 kilogram = 1000 gram"


def test_log_functions_keep_scientific_meaning():
    assert str(safe_math.safe_eval("log(e^10)")) == "10"
    assert str(safe_math.safe_eval(convert.clean_query("ln(e^10)"))) == "10"
    assert str(safe_math.safe_eval("log10(e^10)")) == (
        "4.342944819032518045543160246"
    )
