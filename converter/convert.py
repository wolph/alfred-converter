#!/usr/bin/env python3
'''
Note that we are _explicityly_ using the system python so we don't rely on
custom libraries and/or versions
'''
from __future__ import print_function, annotations

import collections
import decimal
import fractions
import functools
import os
import typing
from xml.etree import cElementTree as ET

from . import constants, safe_math
from .utils import (
    parse_quantity,
    fraction_to_decimal,
    get_env_flag,
    decimal_to_string,
    fraction_to_string,
)

infinity = decimal.Decimal('inf')

_FractionDecimal = typing.Union[decimal.Decimal, fractions.Fraction]
_FractionDecimalStr = typing.Union[_FractionDecimal, str]
_DecimalStr = typing.Union[decimal.Decimal, str]


class ConversionParams(typing.NamedTuple):
    a: decimal.Decimal
    b: decimal.Decimal
    c: decimal.Decimal
    d: decimal.Decimal
    # For decimal conversions we use: (a + b * value) / (c + d * value)
    # For fractional conversions we use: (b / c) * value
    # Look at the `to_base` and `from_base` methods for more information

    @classmethod
    def create(cls, a, b, c, d):
        a = decimal.Decimal(a)
        b = decimal.Decimal(b)
        c = decimal.Decimal(c)
        d = decimal.Decimal(d)
        return ConversionParams(a, b, c, d)


class UnknownUnit(Exception):
    pass


def get_text(parent, name, default=None):
    child = parent.find(name)
    if child is not None:
        return (child.text or '').strip() or default
    else:
        return default


def _get_texts(parent, name):
    for child in parent.findall(name):
        yield child.text


def get_texts(parent, name):
    return list(_get_texts(parent, name))


def get_color_prefix():
    backcolor = os.environ.get('alfred_theme_background', '')
    if backcolor.startswith('rgba'):  # pragma: no cover
        # Format: 'rgba(r,g,b,a)'
        channel = backcolor[5:-1].split(',')
        red, green, blue = channel[:3]
        # Reference: stackoverflow.com/questions/9780632/
        grey = 0.2126 * int(red) + 0.7152 * int(green) + 0.0722 * int(blue)
        if grey < 128:
            return 'inv-'
        else:
            return ''
    else:
        return ''


class Units(object):
    def __init__(self):
        self.annotations = {}
        self.lower_annotations = {}
        self.units = {}
        self.ids = {}
        self.base_units = {}
        self.quantity_types = collections.defaultdict(set)

    def get_converter(self, elem) -> tuple[str | None, ConversionParams]:
        base_unit = elem.find('ConversionToBaseUnit')
        # Convert to decimals later to make it faster :)
        a = '0'
        b = '1'
        c = '1'
        d = '0'

        if base_unit:
            factor = base_unit.find('Factor')
            fraction = base_unit.find('Fraction')
            formula = base_unit.find('Formula')

            if factor is not None:
                b = factor.text
            elif fraction is not None:
                b = fraction.find('Numerator').text
                c = fraction.find('Denominator').text
            elif formula is not None:  # pragma: no branch
                a = formula.find('A').text
                b = formula.find('B').text
                c = formula.find('C').text
                d = formula.find('D').text
            else:  # pragma: no cover
                raise RuntimeError(
                    'Unknown element with id %r' % elem.get('id')
                )

            base = base_unit.get('baseUnit')
        else:
            base = None

        return base, ConversionParams.create(a, b, c, d)

    def register(self, elem):
        base_unit, conversion_params = self.get_converter(elem)
        name = get_text(elem, 'Name') or elem.get('id')
        name = name.replace('picro', 'pico')

        annotations = [
            elem.get('id'),
            elem.get('annotation'),
        ]

        unit = Unit(
            units=self,
            id=elem.get('id'),
            name=name,
            annotations=annotations,
            quantity_types=set(get_texts(elem, 'QuantityType')),
            base_unit=base_unit,
            conversion_params=conversion_params,
        )

        unit.register(self)

    def load(self, xml_file):
        from . import extra_units

        extra_units.register_pre(self)

        tree = ET.parse(xml_file)
        root = tree.getroot()
        for elem in root.find('UnitsDefinition'):
            if elem.find('Deprecated') is None:
                annotation = elem.get('annotation')
                if '(' in annotation:
                    continue

                name_words = set(get_text(elem, 'Name', '').lower().split())
                if name_words & constants.NAME_BLACKLIST:
                    continue

                if annotation in constants.ANNOTATION_BLACKLIST:
                    continue

                if any(x.isdigit() for x in annotation.split('/') if x):
                    continue

                self.register(elem)

        extra_units.register_post(self)

    def convert(self, query):
        '''Convert a query to a list of units with quantities

        :rtype: list of (Unit, decimal.Decimal, Unit)
        '''
        query = safe_math.pre_calculate(query)
        match = constants.FULL_RE.match(query)
        source_match = constants.SOURCE_RE.match(query)

        tos = None
        from_ = None
        quantity = parse_quantity('0')
        try:
            try:
                if match:
                    from_ = self.get(match.group('from'))
                    quantity = parse_quantity(match.group('quantity'))
                    tos = from_.others(match.group('to'))
                elif source_match:
                    from_ = self.get(source_match.group('from'))
                    quantity = parse_quantity(source_match.group('quantity'))
                    tos = from_.others()
                else:
                    raise UnknownUnit()

            except UnknownUnit:
                tos = None
                from_ = None
                quantity = parse_quantity(query)

        except Exception:
            if partial_query := ' '.join(query.split()[:-1]):
                yield from self.convert(partial_query)
                return

        if tos:
            for to in tos:
                yield from_, quantity, to
        else:
            yield None, quantity, None

    def get(self, name):
        '''Get a unit with the given name or annotation

        :param str name: Unit name or annotation

        :return: Returns unit
        :rtype: Unit
        '''
        # sourcery skip: use-or-for-fallback
        unit = self.units.get(name)

        # Coalescing of options for unit names
        if not unit:
            unit = self.annotations.get(name)

        if not unit:
            unit = self.annotations.get(name.lower())

        if not unit:
            unit = self.lower_annotations.get(name.lower())

        if not unit:
            raise UnknownUnit(name)

        return unit


class Unit:
    units: Units
    id: str
    name: str
    fractional: bool
    split: bool | None
    annotations: set[str]
    quantity_types: set[str]
    base_unit: str | None
    conversion_params: ConversionParams

    def __init__(
        self,
        units: Units,
        id: str,
        name: str,
        annotations: list[str],
        quantity_types: set[str],
        base_unit: str | None,
        conversion_params: tuple[
            _DecimalStr, _DecimalStr, _DecimalStr, _DecimalStr
        ],
        fractional: bool = False,
        split: bool | None = None,
    ):
        self.units = units
        self.id = id
        self.name = name
        self.fractional = fractional
        self.split = split

        for k, vs in constants.ANNOTATION_REPLACEMENTS.items():
            for v in vs:
                if k in name:
                    annotations.append(name.replace(k, v))
                elif k in id:
                    annotations.append(id.replace(k, v))

        self.annotations = set(annotations)
        self.quantity_types = set(quantity_types)
        self.base_unit = base_unit

        self.conversion_params = ConversionParams.create(*conversion_params)

    def is_blacklisted(self):
        blacklisted = os.environ.get('UNITS_BLACKLIST', '').lower().strip()
        return set(self.name.lower().split()) & set(blacklisted.split())

    def copy(self, id: str, conversion_params, **kwargs):  # pragma: no cover
        data = (
            dict(
                units=self.units,
                annotations=[],
                quantity_types=self.quantity_types,
                base_unit=self.base_unit,
                fractional=self.fractional,
                split=self.split,
            )
            | kwargs
            | dict(
                id=id,
                name=kwargs.get('name', id),
                conversion_params=conversion_params,
            )
        )
        return Unit(**data)  # type: ignore

    def get_icon(self):
        for quantity_type in self.quantity_types:  # pragma: no cover
            if quantity_type in constants.ICONS:
                return get_color_prefix() + constants.ICONS[quantity_type]

    def to_base(self, value: _FractionDecimalStr) -> _FractionDecimal:
        a, b, c, d = self.conversion_params
        if self.fractional:
            assert not a and not d, 'Fractional units cannot use A and D'
            fraction = fractions.Fraction(b) / fractions.Fraction(c)
            return fraction * fractions.Fraction(value)
        else:
            decimal_value = fraction_to_decimal(value)
            return (a + b * decimal_value) / (c + d * decimal_value)

    def from_base(self, value: _FractionDecimalStr) -> _FractionDecimal:
        a, b, c, d = self.conversion_params
        if self.fractional:
            assert not a and not d, 'Fractional units cannot use A and D'
            fraction = fractions.Fraction(c) / fractions.Fraction(b)
            return fraction * fractions.Fraction(value)
        else:
            decimal_value = fraction_to_decimal(value)
            return (a - c * decimal_value) / (d * decimal_value - b)

    def register(self, units):
        units.ids[self.id] = self
        units.units[self.name] = self

        for annotation in self.annotations:
            units.annotations[annotation] = self
            units.lower_annotations[annotation.lower()] = self

        for quantity_type in list(self.quantity_types):
            units.quantity_types[quantity_type].add(self)

        if not self.base_unit:
            units.base_units[self.name] = self

    def others(self, keyword=None):
        tos = set()
        for quantity_type in self.quantity_types:
            others = self.units.quantity_types[quantity_type]
            for other in others:
                tos.add(other)

        tos = sorted(tos, key=(lambda x: (len(x.id), x.name)))

        if keyword:
            new_tos = [
                to
                for to in tos
                if (
                    keyword in to.name
                    or keyword in to.id
                    or keyword in to.annotations
                )
            ]
            if new_tos:
                return new_tos

            # This might be a scenario that does not occur anymore, but it
            # doesn't hurt to keep it
            for to in tos:  # pragma: no cover
                for annotation in to.annotations:
                    if to.id in annotation:
                        new_tos.append(to)
                        break

            return new_tos  # pragma: no cover
        else:
            return tos

    def __repr__(self):
        data = self.__dict__.copy()
        data['units'] = '...'
        data['annotations'] = '...'
        return f'<{self.__class__.__name__} {data!r}>'

    def __str__(self):
        return constants.localize(self.name)

    def __hash__(self):
        return hash(self.id)


def clean_query(query):
    # query = constants.DECIMAL_SEPARATOR_RE.sub(
    #     constants.DECIMAL_SEPARATOR_REPLACEMENT, query)
    # query = constants.PARTIAL_DECIMAL_SEPARATOR_RE.sub(
    #     constants.PARTIAL_DECIMAL_SEPARATOR_REPLACEMENT, query)
    query = query.replace('$', '')
    query = constants.FUNCTION_ALIASES_RE.sub(
        constants.FUNCTION_ALIASES_REPLACEMENT, query
    )
    query = query.replace('**', '^')
    query = query.rstrip(constants.RIGHT_TRIMABLE_OPERATORS)
    query = query.strip()
    query = constants.POWER_UNIT_RE.sub(
        constants.POWER_UNIT_REPLACEMENT, query
    )
    query = constants.FOOT_INCH_RE.sub(constants.FOOT_INCH_REPLACE, query, 1)
    query = constants.PERCENTAGE_OF_RE.sub(
        constants.PERCENTAGE_OF_REPLACEMENT, query
    )
    query = constants.PERCENT_ADD_RE.sub(
        constants.PERCENT_ADD_REPLACEMENT, query
    )
    query = constants.PERCENT_OFF_RE.sub(
        constants.PERCENT_OFF_REPLACEMENT, query
    )
    query = constants.PERCENT_OF_RE.sub(
        constants.PERCENT_OF_REPLACEMENT, query
    )
    query = constants.DIFFERENCE_RE.sub(
        constants.DIFFERENCE_REPLACEMENT, query
    )
    return query


def get_units_left():
    '''Whether the place the units on the right or the left of the value'''
    return os.environ.get('UNITS_SIDE', '').lower() == 'left'


def get_max_magnitude():
    '''Return the maximum order of magnitude difference between units'''
    return int(os.environ.get('MAX_MAGNITUDE', '3'), 10)


def swap_unit(left, unit, *values):
    if left:
        return (unit,) + values
    else:
        return values + (unit,)


def change_decimal(function):
    @functools.wraps(function)
    def _change_decimal(*args, **kwargs):
        for k, v in list(kwargs.items()):
            if isinstance(v, str):
                kwargs[k] = v.replace('.', constants.DECIMAL_SEPARATOR)

        return function(*args, **kwargs)

    return _change_decimal


def main(units: Units, query: str, create_item):
    create_item = change_decimal(create_item)
    query = clean_query(query)
    left = get_units_left()
    max_magnitude = get_max_magnitude()

    for from_, quantity, to in units.convert(query):
        if to and to.is_blacklisted():  # pragma: no cover
            continue

        if from_:
            yield from format_units(
                create_item, from_, left, max_magnitude, quantity, to, units
            )
        else:
            yield from format_number(create_item, quantity)


def format_number(create_item, quantity):
    q_str = decimal_to_string(quantity)
    yield create_item(
        title=f'{q_str}',
        subtitle=(
            'Action this item to copy the converted value to ' 'the clipboard'
        ),
        icon=f'icons/{get_color_prefix()}calculator63.png',
        attrib=dict(
            uid=q_str,
            arg=q_str,
            valid='yes',
        ),
    )
    if q_str.isdigit() or (q_str[0] == '-' and q_str[1:].isdigit()):
        quantity = int(quantity)

        bases = {k: get_env_flag('BASE_%d' % k) for k in (2, 8, 16)}

        if bases[16]:  # pragma: no branch
            q_hex = hex(quantity)
            yield create_item(
                title=f'{q_hex}',
                subtitle=(
                    'Action this item to copy the HEX '
                    'value to the clipboard'
                ),
                icon=f'icons/{get_color_prefix()}calculator63.png',
                attrib=dict(
                    uid=q_hex,
                    arg=q_hex,
                    valid='yes',
                ),
            )

        if bases[8]:  # pragma: no branch
            q_oct = oct(quantity)
            yield create_item(
                title=f'{q_oct}',
                subtitle=(
                    'Action this item to copy the OCT '
                    'value to the clipboard'
                ),
                icon=f'icons/{get_color_prefix()}calculator63.png',
                attrib=dict(
                    uid=q_oct,
                    arg=q_oct,
                    valid='yes',
                ),
            )

        if bases[2]:  # pragma: no branch
            q_bin = bin(quantity)
            yield create_item(
                title=f'{q_bin}',
                subtitle=(
                    'Action this item to copy the BIN '
                    'value to the clipboard'
                ),
                icon=f'icons/{get_color_prefix()}calculator63.png',
                attrib=dict(
                    uid=q_bin,
                    arg=q_bin,
                    valid='yes',
                ),
            )


def to_title(left, *quantities):
    quantities = zip(quantities[::2], quantities[1::2])
    formatted = ['%s %s' % swap_unit(left, u, q) for u, q in quantities]
    return f'{formatted[0]} = {" ".join(formatted[1:])}'


def format_units(
    create_item,
    from_: Unit,
    left: bool,
    max_magnitude: decimal.Decimal,
    quantity: decimal.Decimal,
    to: Unit,
    units: Units,
    fractional: bool = True,
):
    base_quantity: _FractionDecimalStr = from_.to_base(quantity)
    new_quantity: _FractionDecimalStr = to.from_base(base_quantity)
    magnitude: decimal.Decimal = quantity.copy_abs().log10()
    str_quantity = decimal_to_string(quantity)

    title_parts = []

    if not from_.fractional and isinstance(base_quantity, decimal.Decimal):
        base_quantity = decimal_to_string(base_quantity)

    if to.fractional:
        new_magnitude = fraction_to_decimal(new_quantity).copy_abs().log10()

        if fractional:
            title_parts.append(
                (decimal_to_string(fraction_to_decimal(new_quantity)),)
            )

            if new_quantity_proper := fraction_to_string(new_quantity, True):
                title_parts.append((new_quantity_proper,))

            if fraction := fraction_to_string(new_quantity):
                title_parts.append((fraction,))
                new_quantity = fraction

    elif isinstance(new_quantity, decimal.Decimal):
        new_magnitude = new_quantity.copy_abs().log10()
        new_quantity = decimal_to_string(new_quantity)
        title_parts.append((new_quantity,))
        new_quantity_proper = None
    else:
        raise TypeError('Unknown type %r' % type(new_quantity))

    if (
        magnitude not in {infinity, -infinity}
        and abs(magnitude - new_magnitude) > max_magnitude
    ):
        return

    if to.split:
        title_parts += _get_split_unit_title_parts(units, to, base_quantity)

    titles = [
        to_title(left, from_, str_quantity, to, *title_part)
        for title_part in title_parts
    ]
    yield from create_items(create_item, from_, new_quantity, titles, to)


def _get_split_unit_title_parts(units, to, base_quantity):
    title_parts = []
    split = units.get(to.split)

    major_quantity = to.from_base(base_quantity)
    minor_quantity = split.from_base(base_quantity)

    major = int(major_quantity)
    if major:
        divisor = split.from_base(1) / to.from_base(1)
        minor = minor_quantity % divisor
    else:
        minor = minor_quantity
    minor_proper = fraction_to_string(minor, True)

    if minor.denominator in constants.ALLOWED_DENOMINATORS:
        title_parts.append((major, split, minor))
        if minor_proper:
            title_parts.append((major, split, minor_proper))

    return title_parts


def create_items(create_item, from_, new_quantity, titles, to):
    item = dict(
        subtitle=(
            'Action this item to copy the converted value ' 'to the clipboard'
        ),
        icon='icons/'
        + (
            to.get_icon()
            or from_.get_icon()
            or get_color_prefix() + constants.DEFAULT_ICON
        ),
        attrib=dict(
            uid=f'{from_.id} to {to.id}',
            arg=new_quantity,
            valid='yes',
            autocomplete=f'{new_quantity} {to}',
        ),
    )
    for title in titles:
        yield create_item(title=title, **item)
