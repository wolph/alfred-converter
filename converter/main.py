#!/usr/bin/env python3
from __future__ import print_function

import functools
import os
import pickle
import sys
from xml.etree import cElementTree as ET

from . import constants, convert

DEBUG = os.environ.get('DEBUG_CONVERTER')
PRETTY_XML = os.environ.get('PRETTY_XML')


def create_item(parent, attrib={}, **kwargs):
    # Make sure all attributes are strings
    for k in list(attrib):
        attrib[k] = str(attrib[k])

    item = ET.SubElement(parent, 'item', attrib)
    for k, v in kwargs.items():
        elem = ET.SubElement(item, k)
        elem.text = str(v)

    return item


def item_creator(parent):
    def _item_creator(*args, **kwargs):
        return create_item(parent, *args, **kwargs)

    return _item_creator


def debug_item_creator(attrib, **kwargs):  # pragma: no cover
    return kwargs


def to_xml(f):
    @functools.wraps(f)
    def _to_xml(*args, **kwargs):
        try:
            # The repetition of the items, tree and write methods are needed
            # since the objects get changed in-place. This catches all errors.
            items = ET.Element('items')
            tree = ET.ElementTree(items)

            f(items, *args, **kwargs)

            if not DEBUG:
                assert items, 'No results for %r' % args

                xml_string = ET.tostring(items)
                if PRETTY_XML:
                    from xml.dom import minidom
                    xml_string = minidom.parseString(
                        xml_string
                    ).toprettyxml(indent='   ')

                sys.__stdout__.write(xml_string.decode('utf-8'))

        except Exception as e:  # pragma: no cover
            raise
            items = ET.Element('items')
            tree = ET.ElementTree(items)
            item = ET.SubElement(items, 'item', valid='no')

            title = ET.SubElement(item, 'title')
            title.text = '%s: %s' % (e.__class__.__name__, str(e))

            import traceback

            subtitle = ET.SubElement(item, 'subtitle')
            subtitle.text = '%s: %s' % (
                traceback.format_exc().split('\n')[-4].strip(),
                traceback.format_exc().split('\n')[-3].strip(),
            )
            tree.write(sys.__stdout__, encoding='unicode')
            traceback.print_exc()

    return _to_xml


@to_xml
def scriptfilter(items, query):
    try:  # pragma: no cover
        assert not DEBUG
        with open(constants.UNITS_PICKLE_FILE, 'rb') as fh:
            units = pickle.load(fh)
            assert units.get('in').fractional
    except BaseException:  # pragma: no cover
        units = convert.Units()
        units.load(constants.UNITS_XML_FILE)

        with open(constants.UNITS_PICKLE_FILE, 'wb') as fh:
            pickle.dump(units, fh, -1)

        with open(constants.UNITS_PICKLE_FILE, 'rb') as fh:
            units = pickle.load(fh)

    if DEBUG:
        import pprint

        items = list(convert.main(units, query, debug_item_creator))
        pprint.pprint(items)
    else:
        list(convert.main(units, query, item_creator(items)))


import os
import pprint
pprint.pprint(os.environ, open('/tmp/env', 'w'))


if __name__ == '__main__':
    scriptfilter(' '.join(sys.argv[1:]))
# else:
#     sys.stdout = open(os.devnull, 'w')
#     sys.stderr = open(os.devnull, 'w')
