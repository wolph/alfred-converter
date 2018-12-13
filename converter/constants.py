import re

UNITS_XML_FILE = 'poscUnits22.xml'
UNITS_PICKLE_FILE = 'units.pickle'

OUTPUT_DECIMALS = 6


SOURCE_PATTERN = r'^(?P<quantity>.*[\d.]+)\s*(?P<from>[^\d\s]([^\s]*|.+?))'
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
    'litre': ('liter', 'liters', 'l'),
    'metre': ('meter', 'm'),
    'm2': ('meter^3',),
    'dm': ('decimeter',),
    'dm2': ('dm^2', 'decimeter^2',),
    'dm3': ('dm^3', 'decimeter^3',),
    'cm': ('centimeter',),
    'cm2': ('cm^2', 'centimeter^2',),
    'cm3': ('cm^3', 'centimeter^3',),
    'mm': ('milimeter',),
    'mm2': ('mm^2', 'milimeter^2'),
    'mm3': ('mm^3', 'milimeter^3'),
    'degF': ('f', 'fahrenheit', 'farhenheit', 'farenheit'),
    'degC': ('c', 'celsius', 'celcius'),
    'byte': ('B', 'bytes',),
    'bit': ('b', 'bits',),
    'kbyte': ('KB', 'kB', 'kb', 'kilobyte',),
    'Mbyte': ('MB', 'megabyte',),
    'ozm': ('oz', 'ounce', 'ounces'),
    'lbm': ('lb', 'lbs', 'pound', 'pounds'),
    'miPh': ('mph',),
    'ftPh': ('fps',),
    'foot': ("'",),
    'square': ('sq',),
    'ft2': ('ft^2', 'foot^2'),
    'ft3': ('ft^3', 'foot^3'),
    'inch': ('inches', '"'),
    'inch2': ('inch^2', 'square inch'),
    'inch3': ('inch^3', 'cube inch'),
    'flozUS': ('flus', 'floz', 'fl', 'fl oz', 'fl oz uk'),
    'flozUK': ('fluk', 'fl oz uk', 'fl uk'),
}


EXPANSIONS = {
    'foot': ('feet', 'ft'),
    'mili': ('milli',),
    'meter': ('metres', 'meter', 'meters'),
    '^2': ('sq', 'square'),
    '^3': ('cube', 'cubed'),
}


for annotation, items in ANNOTATION_REPLACEMENTS.items():
    items = set(items)
    items.add(annotation)

    for key, expansions in EXPANSIONS.iteritems():
        for expansion in expansions:
            for item in set(items):
                items.add(item.replace(key, expansion))

    ANNOTATION_REPLACEMENTS[annotation] = sorted(items)



# Mostly for language specific stuff, defaulting to US for now since I'm not
# easily able to detect the language in a fast way from within alfred
LOCALIZED_UNITS = (
    ('metre', 'meter'),
    ('litre', 'liter'),
)


def localize(input_):
    for k, v in LOCALIZED_UNITS:
        if k in input_:
            return input_.replace(k, v)
    return input_


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


FOOT_INCH_RE = re.compile(r'''(\d+)'(\d+)"?''')
FOOT_INCH_REPLACE = r'(\1*12)+\2 inch'

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

