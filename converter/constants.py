import re

UNITS_XML_FILE = 'poscUnits22.xml'
UNITS_PICKLE_FILE = 'units.pickle'


SOURCE_PATTERN = r'^(?P<quantity>.*[\d.]+)\s*(?P<from>[^\d\s][^\s]*)'
SOURCE_RE = re.compile(SOURCE_PATTERN + '$', re.IGNORECASE | re.VERBOSE)

FULL_PATTERN = r'(\s+as|\s+to|\s+in|\s*>|\s*=)\s(?P<to>[^\d\s][^\s]*)$'
FULL_RE = re.compile(SOURCE_PATTERN + FULL_PATTERN + '$',
                     re.IGNORECASE | re.VERBOSE)

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
]

