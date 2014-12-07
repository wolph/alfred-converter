import re
import math
import constants
import decimal


safe_dict = dict((k, getattr(math, k, None)) for k in constants.MATH_FUNCTIONS)
safe_dict['abs'] = abs
safe_dict['Decimal'] = decimal.Decimal
safe_dict['e'] = decimal.Decimal(math.e)
safe_dict['pi'] = decimal.Decimal(math.pi)
safe_dict['inf'] = decimal.Decimal('Inf')
safe_dict['infinity'] = decimal.Decimal('Inf')

DECIMAL_RE = re.compile(r'(\d*\.\d+|\d+\.?)')
DECIMAL_REPLACE = 'Decimal("\g<1>")'

AUTOMUL_RE = re.compile(r'\)\s*(\w+)')
AUTOMUL_REPLACE = ') * \g<1>'


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
    query = DECIMAL_RE.sub(DECIMAL_REPLACE, query)
    query = AUTOMUL_RE.sub(AUTOMUL_REPLACE, query)
    query = fix_partial_queries(query)
    query = fix_parentheses(query)
    for k, v in constants.PRE_EVAL_REPLACEMENTS.items():
        query = query.replace(k, v)

    try:
        return eval(query, {'__builtins__': None}, safe_dict)
    except SyntaxError, e:
        raise SyntaxErr(e)

