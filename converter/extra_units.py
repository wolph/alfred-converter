# The poscUnits22.xml file is missing a few units which would be quite useful
# This allows you to add additional units to the list.

import convert


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

    for base, exponents in exponents.iteritems():
        for exponent, prefix, full_prefix in exponents:
            multiplier = base ** exponent

            params = dict(
                units=units,
                quantity_types=['digital storage'],
            )

            id = prefix + 'bit'
            name = full_prefix + 'bit'
            convert.Unit(
                base_unit='bit' if exponent else None,
                id=id,
                name=name,
                annotations=[prefix.lower() + 'b', prefix + 'b', id, name],
                conversion_params=tuple(map(str, (0, multiplier, 8, 0))),
                **params).register(units)

            id = prefix + 'byte'
            name = full_prefix + 'byte'
            convert.Unit(
                id=id,
                name=name,
                base_unit='byte' if exponent else None,
                annotations=[prefix.lower() + 'B', prefix + 'B', id, name],
                conversion_params=tuple(map(str, (0, multiplier, 1, 0))),
                **params).register(units)




