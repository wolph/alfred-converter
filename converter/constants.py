import re

UNITS_XML_FILE = 'poscUnits22.xml'
UNITS_PICKLE_FILE = 'units.pickle'

OUTPUT_DECIMALS = 6


SOURCE_PATTERN = r'^(?P<quantity>.*[\d.]+)\s*(?P<from>[^\d\s][^\s]*)'
SOURCE_RE = re.compile(SOURCE_PATTERN + '$', re.IGNORECASE | re.VERBOSE)

FULL_PATTERN = r'(\s+as|\s+to|\s+in|\s*>|\s*=)\s(?P<to>[^\d\s][^\s]*)$'
FULL_RE = re.compile(SOURCE_PATTERN + FULL_PATTERN + '$',
                     re.IGNORECASE | re.VERBOSE)

ICONS = {
    'length': 'scale6.png',
    'height': 'scale6.png',
    'distance': 'scale6.png',
    'area': 'scaling1.png',
    'time': 'round27.png',
    'thermodynamic temperature': 'thermometer19.png',
    'volume': 'measuring3.png',
    'mass': 'weight4.png',
    'velocity': 'timer18.png',
    'level of power intensity': 'treble2.png',
    'digital storage': 'binary9.png',
}
DEFAULT_ICON = 'ruler9.png'

ANNOTATION_REPLACEMENTS = {
    'metre': ('metres', 'meter', 'meters'),
    'inch': ('inches', '"'),
    'm2': ('m^2',),
    'm3': ('m^3',),
    'sq ': ('square ',),
    'foot': ('feet', "'"),
    'degF': ('f', 'fahrenheit', 'farhenheit', 'farenheit'),
    'degC': ('c', 'celsius', 'celcius'),
    'byte': ('B', 'bytes',),
    'bit': ('b', 'bits',),
    'kbyte': ('KB', 'kB', 'kb', 'kilobyte',),
    'Mbyte': ('MB', 'megabyte',),
}

RIGHT_TRIMABLE_OPERATORS = '/+*- (.^'

FUNCTION_ALIASES = {
    'deg': 'degrees',
    'rad': 'radians',
    'ln': 'log',
    'arccos': 'acos',
    'arcsin': 'asin',
    'arctan': 'atan',
}
FUNCTION_ALIASES_RE = re.compile(r'\b(%s)\(' % '|'.join(FUNCTION_ALIASES))


def FUNCTION_ALIASES_REPLACEMENT(match):
    return FUNCTION_ALIASES[match.group(1)] + '('


POWER_UNIT_RE = re.compile(r'([a-z])\^([23])\b')
POWER_UNIT_REPLACEMENT = r'\g<1>\g<2>'

PRE_EVAL_REPLACEMENTS = {
    '^': '**',
}

# Known safe math functions
MATH_FUNCTIONS = [
    # Number theoretic and representation functions
    'ceil',
    'copysign',
    'fabs',
    'factorial',
    'floor',
    'fmod',
    'frexp',
    'isinf',
    'isnan',
    'ldexp',
    'modf',
    'trunc',

    # Power and logarithmic functions
    'exp',
    'expm1',
    'log',
    'log1p',
    'log10',
    'pow',
    'sqrt',

    # Trigonometric functions
    'acos',
    'asin',
    'atan',
    'atan2',
    'cos',
    'hypot',
    'sin',
    'tan',

    # Angular conversion functions
    'degrees',
    'radians',

    # Hyperbolic functions
    'acosh',
    'asinh',
    'atanh',
    'cosh',
    'sinh',
    'tanh',

    # Special functions
    'erf',
    'erfc',
    'gamma',
    'lgamma',

    # Missing functions won't break anything but won't do anything either
    'this_function_definitely_does_not_exist',
]

