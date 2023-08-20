from __future__ import print_function, annotations

import contextlib
import decimal
import fractions
import os

from converter import safe_math, constants


def parse_quantity(quantity):
    '''
    Parse a quantity, supports pretty much everything with high precision

    >>> parse_quantity('inf')
    Decimal('Infinity')
    >>> parse_quantity('inf - inf')
    '''
    try:
        return decimal.Decimal(quantity)
    except decimal.InvalidOperation:
        with contextlib.suppress(decimal.InvalidOperation):
            return decimal.Decimal(safe_math.safe_eval(quantity))


def fraction_to_decimal(value):
    '''Convert a fraction to a decimal

    >>> fraction_to_decimal(fractions.Fraction('1/2'))
    Decimal('0.5')
    '''
    if isinstance(value, fractions.Fraction):
        numerator = decimal.Decimal(value.numerator)
        denominator = decimal.Decimal(value.denominator)
        value = numerator / denominator

    return value


def get_env_flag(name, default=True):
    if name not in os.environ:
        return default

    value = os.environ[name]
    return value.lower() in {'true', '1', 'yes', 't', 'y'}


def decimal_to_string(value: decimal.Decimal) -> str:
    '''This strips trailing zeros without converting to 0e0 for 0

    >>> decimal_to_string(decimal.Decimal('1.2345'))
    '1.2345'
    >>> decimal_to_string(decimal.Decimal('1.2000000000000000000000000000001'))
    '1.2'
    >>> decimal_to_string(decimal.Decimal('1.01'))
    '1.01'
    >>> decimal_to_string(decimal.Decimal('1.10'))
    '1.1'
    >>> decimal_to_string(decimal.Decimal('1.00'))
    '1'
    >>> decimal_to_string(decimal.Decimal('1'))
    '1'
    '''
    with decimal.localcontext() as context:
        context.prec = 50
        value = value.quantize(
            decimal.Decimal(10) ** -constants.OUTPUT_DECIMALS, context=context
        )

        return str(value).rstrip('0').rstrip('.')


def fraction_to_string(
    value, proper=False, limit=constants.FRACTIONAL_PRECISION.denominator
):
    # sourcery skip: remove-unnecessary-else, swap-if-else-branches
    '''Converts a decimal to a string fraction


    >>> fraction_to_string(fractions.Fraction('1/2'))
    '1/2'
    >>> fraction_to_string(fractions.Fraction('3/2'))
    '3/2'
    >>> fraction_to_string(fractions.Fraction('1/3'))
    '1/3'

    >>> fraction_to_string(fractions.Fraction('1/3'), limit=3)
    '1/3'
    >>> fraction_to_string(fractions.Fraction('1/3'), limit=2)
    >>> fraction_to_string(fractions.Fraction('15/64'), limit=4)
    '~1/4'

    >>> fraction_to_string(fractions.Fraction('1/3'), proper=True)
    >>> fraction_to_string(fractions.Fraction('3/2'), proper=True)
    '1 1/2'
    >>> fraction_to_string(fractions.Fraction('5/4'), proper=True)
    '1 1/4'
    >>> fraction_to_string(fractions.Fraction('7/4'), proper=True)
    '1 3/4'
    '''
    fraction = fractions.Fraction(value)
    prefix = ''
    if limit and fraction.denominator > limit:
        # Convert the fraction to the closest available fraction with the
        # highest allowed denominator
        approximate = fractions.Fraction(round(fraction * limit), limit)
        deviation = abs((100 * approximate / fraction) - 100)
        prefix = '~'

        fraction = approximate

        if deviation > constants.FRACTIONAL_MAX_DEVIATION:
            return

    if proper:
        if fraction.numerator > fraction.denominator:
            major = int(fraction.numerator / fraction.denominator)
            fraction %= major
            if major and fraction:
                return f'{prefix}{major} {fraction}'
    else:
        return prefix + str(fraction)
