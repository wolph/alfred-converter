# The poscUnits22.xml file is missing a few units which would be quite useful
# This allows you to add additional units to the list.
from __future__ import print_function, annotations

import decimal

from . import convert


def register_pre(units):
    pass


def register_post(units):
    exponents = {
        1024: (
            (0, '', ''),
            (1, 'ki', 'kibi'),
            (2, 'Mi', 'mebi'),
            (3, 'Gi', 'gibi'),
            (4, 'Ti', 'tebi'),
            (5, 'Pi', 'pebi'),
        ),
        1000: (
            (0, '', ''),
            (1, 'k', 'kilo'),
            (2, 'M', 'mega'),
            (3, 'G', 'giga'),
            (4, 'T', 'tera'),
            (5, 'P', 'peta'),
        ),
    }

    for base, exponents in exponents.items():
        for exponent, prefix, full_prefix in exponents:
            multiplier = base**exponent

            params = dict(
                units=units,
                quantity_types=['digital storage'],
            )

            id_ = f'{prefix}bit'
            name = f'{full_prefix}bit'
            convert.Unit(
                base_unit='bit' if exponent else None,
                id=id_,
                name=name,
                annotations=[f'{prefix.lower()}b', f'{prefix}b', id_, name],
                conversion_params=('0', str(multiplier), '8', '0'),
                **params,
            ).register(units)

            id_ = f'{prefix}byte'
            name = f'{full_prefix}byte'
            convert.Unit(
                id=id_,
                name=name,
                base_unit='byte' if exponent else None,
                annotations=[f'{prefix.lower()}B', f'{prefix}B', id_, name],
                conversion_params=('0', str(multiplier), '1', '0'),
                **params,
            ).register(units)

    liter = units.get('L')
    liter.copy(
        units=units,
        id='teaspoon',
        name='teaspoon',
        annotations=['t', 'tsp'],
        conversion_params=('0', '0.000005', '1', '0'),
        fractional=True,
    ).register(units)
    liter.copy(
        units=units,
        id='tablespoon',
        name='tablespoon',
        annotations=['tbl', 'tbs', 'tbsp'],
        conversion_params=('0', '0.000015', '1', '0'),
        fractional=True,
    ).register(units)
    liter.copy(
        units=units,
        id='cup',
        name='cup',
        annotations=['cup'],
        conversion_params=('0', '0.000240', '1', '0'),
        fractional=True,
    ).register(units)

    units.get('in').fractional = True
    foot = units.get('ft')
    foot.split = 'in'
    foot.fractional = True

    prefixes = {
        ('milli', 'm'): decimal.Decimal('1e-3'),
        ('nano', 'n'): decimal.Decimal('1e-9'),
    }
    farad = units.get('farad')
    for prefixes, multiplier in prefixes.items():
        id_ = prefixes[1] + farad.id
        name = prefixes[0] + farad.name

        farad.copy(
            units=units,
            id=id_,
            name=name,
            annotations=[f'{prefix}f' for prefix in prefixes] + [id_, name],
            conversion_params=tuple(map(str, (0, multiplier, 1, 0))),
        ).register(units)

    hz = units.get('Hz')
    hz.conversion_params = tuple(units.get('cycles/second').conversion_params)
    hz.base_unit = 'radians/second'
    hz.register(units)
