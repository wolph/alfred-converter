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

Configuration
==================

The extension can be configured through the environment variables setting in Alfred.

::
    BASE_2: Enable base 2 (binary ) output
    BASE_8: Enable base 8 (octal) output
    BASE_16: Enable base 16 (hexadecimal) output
    DECIMAL_SEPARATOR: Comma or dot separator for decimals
    FRACTIONAL_UNITS: "both", "decimal" or "fractional" only
    MAX_MAGNITUDE: Maximum orders of magnitude to show. For 1 megabyte in bytes we need 9 orders of magnitude because it's 1 million bytes.
    UNITS_BLACKLIST: Units you wish to hide
    UNITS_SIDE: Showing the units at the right or the left side

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
