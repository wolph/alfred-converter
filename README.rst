Alfred Unit Converter
--------------------------------

Alfred unit converter is a smart calculator for Alfred with support for unit
conversions to make it a bit comparable to the Google Calculator and Wolfram
Alpha.

Issues
================

If new units and/or other names for units should be added please let me know by
creating an issue at: https://github.com/WoLpH/alfred-converter/issues

Installation
=============

To install use the following link:

https://github.com/WoLpH/alfred-converter/blob/master/unit_converter.alfredworkflow

Requirements
==================

This workflow supports Python 3.8+.

Configuration
==================

The extension can be configured through the environment variables setting in Alfred.

::

    BASE_2: Enable base 2 (binary ) output
    BASE_8: Enable base 8 (octal) output
    BASE_16: Enable base 16 (hexadecimal) output
    DECIMAL_SEPARATOR: Comma or dot separator for decimals
    FRACTIONAL_UNITS: "both", "decimal" or "fractional" only
    OUTPUT_DECIMALS: Number of decimals to show for decimal output
    FRACTION_PRECISION: Maximum denominator for fractional output
    FRACTIONAL_MAX_DEVIATION: Maximum allowed deviation for fractional output
    CURRENCY_DEFAULT_TARGETS: Currency targets to show for short queries such as "5 usd". Defaults to usd,eur,gbp,jpy,cny,cad,aud
    MAX_MAGNITUDE: Maximum orders of magnitude to show. For 1 megabyte in bytes we need 9 orders of magnitude because it's 1 million bytes.
    UNITS_BLACKLIST: Units you wish to hide
    UNITS_SIDE: Showing the units at the right or the left side

Currency conversion
==================

Currency conversions use daily cached rates from the free fawazahmed0
exchange-api. Normal unit and calculator queries never block on currency
network access.

Currency examples:

::

    2000 isk eur
    2000 isk to eur
    2000 isk in eur
    5 usd

Rates refresh automatically on the first currency use of a new day. If cached
rates are stale, Alfred shows the stale result immediately while a background
refresh runs. If no rates exist yet, Alfred shows a rates-updating item; retry
the query shortly after.

Short currency queries such as ``5 usd`` show the configured default target
currencies. The default list is ``usd,eur,gbp,jpy,cny,cad,aud`` and can be changed
with ``CURRENCY_DEFAULT_TARGETS`` in the Alfred workflow configuration.
Currency results include symbols and target-currency icons. Currencies with
a clear country or region use flag badges; ambiguous regional and special
currencies keep neutral currency badges.

To update a base currency manually:

::

    currency-update isk

Math notes
==================

log() is the natural logarithm. ln() is an alias for log(). Use log10() for
base-10 logarithms.

Example queries
==================

::

    1m in cm # Just a simple conversion
    2^30 byte # Using powers before conversion
    5' # Converting units with special characters
    20" # Like above
    5 * cos(pi + 2) # Executing mathematical functions
    5 * pi + 2 mm in m # Mathematical constants with unit conversion
    1 * cos(pi/2) - sin(pi^2) # More advanced mathematical expressions
    ln(e^10) # Testing the ln(x) alias of log _e(x)
    log(e^10) # The normal log method
    log10(e^10) # Base-10 logarithm
    5+3^2" in mm # Testing math with unit conversion
    1 + 2 / 3 * 4) mm^2 in cm^2 # Unbalanced paranthesis with unit conversion
    ((1 + 2 / 3 * 4) mm^2 in cm^2 # Unbalanced paranthesis the other way
    inf - inf # Not actually possible, but we backtrack to "inf"
    0b1010 + 0xA - 050 # Test calculations with hex, oct and binary numbers

.. image:: https://raw.githubusercontent.com/WoLpH/alfred-converter/master/examples/bytes.png

.. image:: https://raw.githubusercontent.com/WoLpH/alfred-converter/master/examples/exponent_rounding.png

.. image:: https://raw.githubusercontent.com/WoLpH/alfred-converter/master/examples/mathematical_functions.png

.. image:: https://raw.githubusercontent.com/WoLpH/alfred-converter/master/examples/square_metres.png

.. image:: https://raw.githubusercontent.com/WoLpH/alfred-converter/master/examples/bin_oct_hex.png

The list of units and conversions was downloaded from:
http://w3.energistics.org/uom/poscUnits22.xml
