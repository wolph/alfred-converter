#!/usr/bin/env python3
import os
import pickle
import sys
import traceback

from . import constants, convert, output

DEBUG = os.environ.get('DEBUG_CONVERTER')


def error_response(error):
    tb = traceback.format_exc().splitlines()
    subtitle = tb[-2].strip() if len(tb) >= 2 else str(error)
    return output.Response(
        items=[
            output.Item(
                title=f"{error.__class__.__name__}: {error}",
                subtitle=subtitle,
                valid=False,
                icon="icons/inv-calculator63.png",
            )
        ],
        skipknowledge=True,
    )


def load_units():
    try:  # pragma: no cover
        assert not DEBUG
        with open(constants.UNITS_PICKLE_FILE, 'rb') as fh:
            units = pickle.load(fh)
            assert units.get('in').fractional
            if (
                getattr(units, 'cache_version', None)
                != constants.UNITS_CACHE_VERSION
            ):
                raise RuntimeError('Stale units cache')
            return units
    except BaseException:  # pragma: no cover
        units = convert.Units()
        units.load(constants.UNITS_XML_FILE)

        with open(constants.UNITS_PICKLE_FILE, 'wb') as fh:
            pickle.dump(units, fh, -1)

        with open(constants.UNITS_PICKLE_FILE, 'rb') as fh:
            return pickle.load(fh)


def run(query):
    units = load_units()
    items = list(convert.main(units, query, output.item_creator()))
    if not items:
        raise RuntimeError(f'No results for {query!r}')
    return output.Response(items=items, skipknowledge=True)


def scriptfilter(query):
    try:
        response = run(' '.join(str(query).split()))
    except Exception as error:  # pragma: no cover
        response = error_response(error)

    if DEBUG:
        import pprint

        pprint.pprint(response.to_alfred())
    else:
        output.write_json(response)


if __name__ == '__main__':
    scriptfilter(' '.join(sys.argv[1:]))
# else:
#     sys.stdout = open(os.devnull, 'w')
#     sys.stderr = open(os.devnull, 'w')
