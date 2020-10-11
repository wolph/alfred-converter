import re
import math
import decimal
import functools
import constants


safe_dict = dict()


def decimal_math(method_name, *args):
    decimal_args = []
    for arg in args:
        if not isinstance(arg, decimal.Decimal):  # pragma: no cover
            arg = decimal.Decimal(arg)

        decimal_args.append(arg)

    method = getattr(math, method_name)
    return decimal.Decimal(method(*args))


for k in constants.MATH_FUNCTIONS:
    if hasattr(decimal.Decimal, k):
        safe_dict[k] = getattr(decimal.Decimal, k)
    elif hasattr(math, k):
        safe_dict[k] = functools.partial(decimal_math, k)


# The following methods are copied from the Python manual:
# https://docs.python.org/3/library/decimal.html#decimal-recipes
def pi():
    """Compute Pi to the current precision.

    >>> print(pi())
    3.141592653589793238462643383

    """
    decimal.getcontext().prec += 2  # extra digits for intermediate steps
    three = decimal.Decimal(3)  # substitute "three=3.0" for regular floats
    lasts, t, s, n, na, d, da = 0, three, 3, 1, 0, 0, 24
    while s != lasts:
        lasts = s
        n, na = n + na, na + 8
        d, da = d + da, da + 32
        t = (t * n) / d
        s += t
    decimal.getcontext().prec -= 2
    return +s  # unary plus applies the new precision


def exp(x):
    """Return e raised to the power of x.  Result type matches input type.

    >>> print(exp(decimal.Decimal(1)))
    2.718281828459045235360287471
    >>> print(exp(decimal.Decimal(2)))
    7.389056098930650227230427461
    >>> print(exp(2.0))
    7.38905609893
    >>> print(exp(2+0j))
    (7.38905609893+0j)

    """
    decimal.getcontext().prec += 2
    i, lasts, s, fact, num = 0, 0, 1, 1, 1
    while s != lasts:
        lasts = s
        i += 1
        fact *= i
        num *= x
        s += num / fact
    decimal.getcontext().prec -= 2
    return +s


def cos(x):
    """Return the cosine of x as measured in radians.

    The Taylor series approximation works best for a small value of x.
    For larger values, first compute x = x % (2 * pi).

    >>> print(cos(decimal.Decimal('0.5')))
    0.8775825618903727161162815826
    >>> print(cos(0.5))
    0.87758256189
    >>> print(cos(0.5+0j))
    (0.87758256189+0j)

    """
    decimal.getcontext().prec += 2
    i, lasts, s, fact, num, sign = 0, 0, 1, 1, 1, 1
    while s != lasts:
        lasts = s
        i += 2
        fact *= i * (i - 1)
        num *= x * x
        sign *= -1
        s += num / fact * sign
    decimal.getcontext().prec -= 2
    return +s


def sin(x):
    """Return the sine of x as measured in radians.

    The Taylor series approximation works best for a small value of x.
    For larger values, first compute x = x % (2 * pi).

    >>> print(sin(decimal.Decimal('0.5')))
    0.4794255386042030002732879352
    >>> print(sin(0.5))
    0.479425538604
    >>> print(sin(0.5+0j))
    (0.479425538604+0j)

    """
    decimal.getcontext().prec += 2
    i, lasts, s, fact, num, sign = 1, 0, x, 1, x, 1
    while s != lasts:
        lasts = s
        i += 2
        fact *= i * (i - 1)
        num *= x * x
        sign *= -1
        s += num / fact * sign
    decimal.getcontext().prec -= 2
    return +s


safe_dict['abs'] = abs
safe_dict['Decimal'] = decimal.Decimal
safe_dict['e'] = decimal.Decimal(math.e)
safe_dict['pi'] = pi()
safe_dict['exp'] = exp
safe_dict['cos'] = cos
safe_dict['sin'] = sin
safe_dict['inf'] = decimal.Decimal('Inf')
safe_dict['infinity'] = decimal.Decimal('Inf')

DECIMAL_RE = re.compile(r'(\d*\.\d+|\d+\.?)')
DECIMAL_REPLACE = r'Decimal("\g<1>")'

AUTOMUL_RE = re.compile(r'\)\s*(\w+)')
AUTOMUL_REPLACE = r') * \g<1>'

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

    context = safe_dict.copy()
    context['math'] = math
    context['decimal'] = decimal
    try:
        return eval(query, {'__builtins__': None}, context)
    except SyntaxError as e:
        raise SyntaxErr(e)
