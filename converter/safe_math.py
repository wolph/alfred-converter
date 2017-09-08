import re
import math
import constants
import decimal


safe_dict = dict()
for k in constants.MATH_FUNCTIONS:
    if hasattr(decimal.Decimal, k):
        safe_dict[k] = getattr(decimal.Decimal, k)
    elif hasattr(math, k):
        safe_dict[k] = getattr(math, k)

safe_dict['abs'] = abs
safe_dict['Decimal'] = decimal.Decimal
safe_dict['e'] = decimal.Decimal(math.e)
safe_dict['pi'] = decimal.Decimal(math.pi)
safe_dict['inf'] = decimal.Decimal('Inf')
safe_dict['infinity'] = decimal.Decimal('Inf')

DECIMAL_RE = re.compile(r'(\d*\.\d+|\d+\.?)')
DECIMAL_REPLACE = r'Decimal("\g<1>")'

AUTOMUL_RE = re.compile(r'\)\s*(\w+)')
AUTOMUL_REPLACE = ') * \g<1>'

BIN_RE = re.compile(r'(?!\.)\b0b([01]+)\b', re.IGNORECASE)


def BIN_REPLACE(match):
    return str(int(match.group(1), 2))


OCT_RE = re.compile(r'(?:[^\.]\b|^)0([0-7]+)\b')


def OCT_REPLACE(match):
    return str(int(match.group(1), 8))


HEX_RE = re.compile(r'\b0x([a-f0-9]+)\b', re.IGNORECASE)


def HEX_REPLACE(match):
    return str(int(match.group(1), 16))


class SyntaxErr(SyntaxError):
    def __init__(self, error):
        self.error = error

    def __str__(self):  # pragma: no cover
        return '%s: %s' % (self.error.msg, self.error.text)


def fix_parentheses(query):
    diff = query.count('(') - query.count(')')
    if diff > 0:
        query = query + ')' * diff
    elif diff < 0:
        query = '(' * abs(diff) + query

    return query


def fix_partial_queries(query):
    return query.rstrip(constants.RIGHT_TRIMABLE_OPERATORS)


def safe_eval(query):
    '''safely evaluate a query while automatically evaluating some mathematical
    functions

    >>> safe_eval('.1 * 0.01')
    Decimal('0.001')
    >>> safe_eval('0x10')
    Decimal('16')
    >>> safe_eval('10')
    Decimal('10')
    >>> safe_eval('010')
    Decimal('8')
    >>> safe_eval('0b10')
    Decimal('2')
    '''
    query = HEX_RE.sub(HEX_REPLACE, query)
    query = BIN_RE.sub(BIN_REPLACE, query)
    query = OCT_RE.sub(OCT_REPLACE, query)
    query = DECIMAL_RE.sub(DECIMAL_REPLACE, query)
    query = AUTOMUL_RE.sub(AUTOMUL_REPLACE, query)
    query = fix_partial_queries(query)
    query = fix_parentheses(query)

    for k, v in constants.PRE_EVAL_REPLACEMENTS.items():
        query = query.replace(k, v)

    try:
        return eval(query, {'__builtins__': None}, safe_dict)
    except SyntaxError as e:
        raise SyntaxErr(e)

