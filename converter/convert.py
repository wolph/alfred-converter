#!/usr/bin/python
'''
Note that we are _explicityly_ using the system python so we don't rely on
custom libraries and/or versions
'''
from __future__ import print_function
import os
import collections
import decimal
import functools
import fractions
import constants
import safe_math


infinity = decimal.Decimal('inf')


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
        try:
            return decimal.Decimal(safe_math.safe_eval(quantity))
        except decimal.InvalidOperation:  # pragma: no cover
            pass


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


class Units(object):
    def __init__(self):
        self.annotations = {}
        self.lower_annotations = {}
        self.units = {}
        self.ids = {}
        self.base_units = {}
        self.quantity_types = collections.defaultdict(set)

    def get_converter(self, elem):
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
            base = elem.get('id')

        return base, (a, b, c, d)

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
            quantity_types=get_texts(elem, 'QuantityType'),
            base_unit=get_text(elem, 'BaseUnit'),
            conversion_params=conversion_params,
        )

        unit.register(self)

    def load(self, xml_file):
        import extra_units

        extra_units.register_pre(self)

        from xml.etree import cElementTree as ET

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

        except:  # NOQA
            partial_query = ' '.join(query.split()[:-1])
            if partial_query:
                for from_, quantity, to in self.convert(partial_query):
                    yield from_, quantity, to
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
        unit = self.units.get(name)
        if not unit:
            unit = self.annotations.get(name)

        if not unit:
            unit = self.annotations.get(name.lower())

        if not unit:
            unit = self.lower_annotations.get(name.lower())

        if not unit:
            raise UnknownUnit(name)

        return unit


class Unit(object):
    def __init__(
        self,
        units,
        id,
        name,
        annotations,
        quantity_types,
        base_unit,
        conversion_params,
        fractional=False,
        split=None,
    ):
        self.units = units
        self.id = id
        self.name = name
        self.fractional = fractional
        self.split = split

        for k, vs in constants.ANNOTATION_REPLACEMENTS.items():
            if k in name:
                for v in vs:
                    annotations.append(name.replace(k, v))
            elif k in id:
                for v in vs:
                    annotations.append(id.replace(k, v))

        self.annotations = set(annotations)
        self.quantity_types = set(quantity_types)
        self.base_unit = base_unit
        self.conversion_params = conversion_params

    def is_blacklisted(self):
        blacklisted = os.environ.get('UNITS_BLACKLISTED', '').lower().strip()
        return set(self.name.lower().split()) & set(blacklisted.split())

    def copy(self, id, conversion_params, **kwargs):  # pragma: no cover
        annotations = []
        data = dict(
            units=self.units,
            annotations=annotations,
            quantity_types=self.quantity_types,
            base_unit=self.base_unit,
            fractional=self.fractional,
            split=self.split,
        )
        data.update(kwargs)
        data['id'] = id
        data['name'] = kwargs.get('name', id)
        data['conversion_params'] = map(str, conversion_params)
        return Unit(**data)

    def get_icon(self):
        for quantity_type in self.quantity_types:  # pragma: no cover
            if quantity_type in constants.ICONS:
                return get_color_prefix() + constants.ICONS[quantity_type]

    def to_base(self, value):
        a, b, c, d = map(decimal.Decimal, self.conversion_params)
        if self.fractional:
            assert not a and not d, 'Fractional units cannot use A and D'
            fraction = fractions.Fraction(b) / fractions.Fraction(c)
            return fraction * fractions.Fraction(value)
        else:
            value = fraction_to_decimal(value)
            return (a + b * value) / (c + d * value)

    def from_base(self, value):
        a, b, c, d = map(decimal.Decimal, self.conversion_params)
        if self.fractional:
            assert not a and not d, 'Fractional units cannot use A and D'
            fraction = fractions.Fraction(c) / fractions.Fraction(b)
            return fraction * fractions.Fraction(value)
        else:
            value = fraction_to_decimal(value)
            return (a - c * value) / (d * value - b)

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
            new_tos = []
            for to in tos:
                if keyword in to.name or keyword in to.id:
                    new_tos.append(to)

            if new_tos:
                return new_tos

            for to in tos:
                for annotation in to.annotations:  # pragma: no branch
                    if to.id in annotation:
                        new_tos.append(to)
                        break

            return new_tos
        else:
            return tos

    def __repr__(self):
        return '<%s %r>' % (self.__class__.__name__, self.__dict__,)
        return '<%s[%s] %s>' % (self.__class__.__name__, self.id, self.name,)

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


def decimal_to_string(value):
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

        value = str(value)
        value = value.rstrip('0').rstrip('.')
        return value


def fraction_to_string(value, proper=False):
    '''Converts a decimal to a string fraction


    '''
    fraction = fractions.Fraction(value)
    if proper:
        if fraction.numerator > fraction.denominator:
            major = int(fraction.numerator / fraction.denominator)
            fraction %= major
            if major and fraction:
                return '%s %s' % (major, fraction)
    else:
        return str(fraction)


def get_units_left():
    '''Whether the place the units on the right or the left of the value'''
    return os.environ.get('UNITS_SIDE') == 'left'


def get_max_magnitude():
    '''Return the maximum order of magnitude difference between units'''
    return int(os.environ.get('MAX_MAGNITUDE', 3))


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


def main(units, query, create_item):
    create_item = change_decimal(create_item)
    query = clean_query(query)
    left = get_units_left()
    max_magnitude = get_max_magnitude()

    for from_, quantity, to in units.convert(query):
        if to and to.is_blacklisted():  # pragma: no cover
            continue

        if from_:
            base_quantity = from_.to_base(quantity)
            new_quantity = to.from_base(base_quantity)

            magnitude = quantity.copy_abs().log10()
            quantity = decimal_to_string(quantity)
            if to.fractional:
                new_magnitude = fraction_to_decimal(new_quantity).copy_abs() \
                    .log10()
                new_quantity = fraction_to_string(new_quantity)
                new_quantity_proper = fraction_to_string(new_quantity, True)
            else:
                new_magnitude = new_quantity.copy_abs().log10()
                new_quantity = decimal_to_string(new_quantity)
                new_quantity_proper = None

            if from_.fractional:
                base_quantity = fraction_to_string(base_quantity)
            else:
                base_quantity = decimal_to_string(base_quantity)

            if magnitude not in {infinity, -infinity} \
                    and abs(magnitude - new_magnitude) > max_magnitude:
                continue

            titles = []

            titles.append('%s %s = %s %s' % (
                swap_unit(left, from_, quantity)
                + swap_unit(left, to, new_quantity)
            ))
            if new_quantity_proper:
                titles.append('%s %s = %s %s' % (
                    swap_unit(left, from_, quantity)
                    + swap_unit(left, to, new_quantity_proper)
                ))

            if to.split:
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

                titles.append('%s %s = %s %s %s %s' % (
                    swap_unit(left, from_, quantity)
                    + swap_unit(left, to, major)
                    + swap_unit(left, split, minor)
                ))
                if minor_proper:
                    titles.append('%s %s = %s %s %s %s' % (
                        swap_unit(left, from_, quantity)
                        + swap_unit(left, to, major)
                        + swap_unit(left, split, minor_proper)
                    ))

            for title in titles:
                yield create_item(
                    title=title,
                    subtitle=(
                        'Action this item to copy the converted value '
                        'to the clipboard'
                    ),
                    icon='icons/'
                    + (
                        to.get_icon()
                        or from_.get_icon()
                        or get_color_prefix() + constants.DEFAULT_ICON
                    ),
                    attrib=dict(
                        uid='%s to %s' % (from_.id, to.id),
                        arg=new_quantity,
                        valid='yes',
                        autocomplete='%s %s' % (new_quantity, to),
                    ),
                )
        else:
            q_str = decimal_to_string(quantity)

            yield create_item(
                title='%s' % q_str,
                subtitle=(
                    'Action this item to copy the converted value to '
                    'the clipboard'
                ),
                icon='icons/%scalculator63.png' % get_color_prefix(),
                attrib=dict(uid=q_str, arg=q_str, valid='yes',),
            )

            if q_str.isdigit() or (q_str[0] == '-' and q_str[1:].isdigit()):
                quantity = int(quantity)

                bases = {
                    k: os.environ.get('BASE_%d' % k, 'true').lower() == 'true'
                    for k in (2, 8, 16)
                }

                if bases[16]:  # pragma: no branch
                    q_hex = hex(quantity)
                    yield create_item(
                        title='%s' % q_hex,
                        subtitle=(
                            'Action this item to copy the HEX '
                            'value to the clipboard'
                        ),
                        icon='icons/%scalculator63.png' % get_color_prefix(),
                        attrib=dict(uid=q_hex, arg=q_hex, valid='yes',),
                    )

                if bases[8]:  # pragma: no branch
                    q_oct = oct(quantity)
                    yield create_item(
                        title='%s' % q_oct,
                        subtitle=(
                            'Action this item to copy the OCT '
                            'value to the clipboard'
                        ),
                        icon='icons/%scalculator63.png' % get_color_prefix(),
                        attrib=dict(uid=q_oct, arg=q_oct, valid='yes',),
                    )

                if bases[2]:  # pragma: no branch
                    q_bin = bin(quantity)
                    yield create_item(
                        title='%s' % q_bin,
                        subtitle=(
                            'Action this item to copy the BIN '
                            'value to the clipboard'
                        ),
                        icon='icons/%scalculator63.png' % get_color_prefix(),
                        attrib=dict(uid=q_bin, arg=q_bin, valid='yes',),
                    )
