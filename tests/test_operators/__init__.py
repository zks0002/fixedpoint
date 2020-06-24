#!/usr/bin/env python3.8
# Copyright 2020, Schweitzer Engineering Laboratories, Inc
# SEL Confidential
import random
import struct
import re
import sys
import operator
from math import ceil, log2

from ..init import (
    uut,
    UTLOG,
    LOGID,
    nose,
)
from .. import tools
from ..test_initialization_methods import (
    nondefault_props_gen,
    initint_gen,
    initstr_gen,
)

@tools.setup(progress_bar=True, require_matlab=True)
def test_addition():
    """Verify binary +, +=
    """
    seed = random.getrandbits(31)
    UTLOG.debug("MATLAB RANDOM SEED: %d", seed, **LOGID)
    tools.MATLAB.generate_stimulus(seed, tools.NUM_ITERATIONS)
    unpacker = struct.Struct(
        '512s' # 512-character string - binary augend
        'I' # unsigned int - augend signedness
        'I' # unsigned int - augend m
        'I' # unsigned int - augend n
        '4x' # padding
        '512s' # 512-character string - binary addend
        'I' # unsigned int - addend signedness
        'I' # unsigned int - addend m
        'I' # unsigned int - addend n
        '4x' # padding
        '256s' # 256-character string - hex result
        '256s' # 256-character string - hex reflected result
    )
    for data in tools.test_iterator(tools.MATLAB.yield_stimulus(unpacker, 3)):
        ainit, asign, am, an, binit, bsign, bm, bn, add, radd = data
        ainit = ainit.decode()
        binit = binit.decode()
        add = add.decode()
        radd = radd.decode()

        a = uut.FixedPoint(ainit, asign, am, an, rounding='in')
        aa = uut.FixedPoint(a)
        b = uut.FixedPoint(binit, bsign, bm, bn, rounding='in')

        result = int(add, 16)
        rresult = int(radd, 16)

        # Addition is commutative, so both results should be equal
        nose.tools.assert_equal(result, rresult)

        # __add__
        x = a + b
        y = b + a
        # MATLAB adds an extra sign bit for negative results
        result &= x.bitmask
        rresult &= y.bitmask
        # Expected results from MATLAB
        nose.tools.assert_equal(x.bits, result)
        nose.tools.assert_equal(y.bits, rresult)

        # Operands should not change
        nose.tools.assert_equal(a.bits, int(ainit, 2))
        nose.tools.assert_equal(b.bits, int(binit, 2))

        # __iadd__
        a += b
        b += aa
        nose.tools.assert_equal(a.bits, result)
        nose.tools.assert_equal(b.bits, rresult)
        nose.tools.assert_equal(a.qformat, b.qformat)

        # __radd__
        floater = random.getrandbits(52) * 2**-random.randrange(52) * random.choice([1, -1])
        reflected = floater + a
        regular = a + floater
        nose.tools.assert_equal(regular, reflected)
        nose.tools.assert_equal(regular.qformat, reflected.qformat)

@tools.setup(progress_bar=True, require_matlab=True)
def test_subtraction():
    """Verify binary -, -=
    """
    seed = random.getrandbits(31)
    UTLOG.debug("MATLAB RANDOM SEED: %d", seed, **LOGID)
    tools.MATLAB.generate_stimulus(seed, tools.NUM_ITERATIONS)
    unpacker = struct.Struct(
        '512s' # 512-character string - binary minuend
        'I' # unsigned int - minuend signedness
        'I' # unsigned int - minuend m
        'I' # unsigned int - minuend n
        '4x' # padding
        '512s' # 512-character string - binary subtrahend
        'I' # unsigned int - subtrahend signedness
        'I' # unsigned int - subtrahend m
        'I' # unsigned int - subtrahend n
        '4x' # padding
        '256s' # 256-character string - hex result
        '256s' # 256-character string - hex reflected result
    )
    errmsg = [
        r'\[SN\d+\]:? Unsigned subtraction causes overflow\.',
    ]
    for data in tools.test_iterator(tools.MATLAB.yield_stimulus(unpacker, 3)):
        ainit, asign, am, an, binit, bsign, bm, bn, sub, rsub = data
        ainit = ainit.decode()
        binit = binit.decode()
        sub = sub.decode()
        rsub = rsub.decode()

        a = uut.FixedPoint(ainit, asign, am, an, rounding='in')
        aa = uut.FixedPoint(a)
        b = uut.FixedPoint(binit, bsign, bm, bn, rounding='in')

        result = int(sub, 16)
        rresult = int(rsub, 16)

        # If either operand is signed, we do signed subtraction
        if a.signed or b.signed:
            # __sub__
            x = a - b
            y = b - a

            # MATLAB adds an extra sign bit for negative results
            result &= x.bitmask
            rresult &= y.bitmask
            # Expected results from MATLAB
            nose.tools.assert_equal(x.bits, result)
            nose.tools.assert_equal(y.bits, rresult)

            # Operands should not change
            nose.tools.assert_equal(a.bits, int(ainit, 2))
            nose.tools.assert_equal(b.bits, int(binit, 2))

            # __isub__
            a -= b
            b -= aa
            nose.tools.assert_equal(a.bits, result)
            nose.tools.assert_equal(b.bits, rresult)
            nose.tools.assert_equal(a.qformat, b.qformat)

            # __rsub__
            z = a if a.signed else b
            floater = random.getrandbits(52) * 2**-random.randrange(52) * random.choice([1, -1])
            reflected = floater - z
            regular = z - floater
            nose.tools.assert_equal(regular.qformat, reflected.qformat)

        # If both operands are unsigned, we care about overflow
        else:
            big, small, uresult = (a, b, rresult) if (abig := a > b) else (b, a, result)
            bbig = uut.FixedPoint(big)
            with nose.tools.assert_raises_regex(uut.FixedPointOverflowError, errmsg[0]):
                small - big

            # Do the operation anyway, with a warning. Verify the warning
            a.overflow_alert, b.overflow_alert = 'warning', 'warning'
            with tools.CaptureWarnings() as warn:
                z = small - big
            for log, regex in zip(warn.logs, errmsg):
                nose.tools.assert_regex(log, regex)

            # Verify we're clamped at 0
            nose.tools.assert_equal(z, 0)
            nose.tools.assert_true(z.clamped)

            # Change to wrap
            a.overflow, b.overflow = 'wrap', 'wrap'
            a.overflow_alert, b.overflow_alert = 'ignore', 'ignore'
            w = small - big
            v = big - small

            # Verify against MATLAB
            uresult &= w.bitmask
            vresult = v.bitmask & (result if abig else rresult)
            nose.tools.assert_equal(w.bits, uresult)
            nose.tools.assert_equal(v.bits, vresult)

            # Operands should not change
            nose.tools.assert_equal((big if abig else small).bits, int(ainit, 2))
            nose.tools.assert_equal((small if abig else big).bits, int(binit, 2))

            # __isub__
            big -= small
            small -= bbig
            nose.tools.assert_equal(big.bits, vresult)
            nose.tools.assert_equal(small.bits, uresult)
            nose.tools.assert_equal(big.qformat, small.qformat)

            # __rsub__
            regular = big - small
            reflected = float(big) - small
            nose.tools.assert_equal(regular.qformat, reflected.qformat)

@tools.setup(progress_bar=True, require_matlab=True)
def test_multiplication():
    """Verify *, *=
    """
    seed = random.getrandbits(31)
    UTLOG.debug("MATLAB RANDOM SEED: %d", seed, **LOGID)
    tools.MATLAB.generate_stimulus(seed, tools.NUM_ITERATIONS)
    unpacker = struct.Struct(
        '512s' # 512-character string - binary multiplicand
        'I' # unsigned int - multiplicand signedness
        'I' # unsigned int - multiplicand m
        'I' # unsigned int - multiplicand n
        '4x' # padding
        '512s' # 512-character string - binary multiplier
        'I' # unsigned int - multiplier signedness
        'I' # unsigned int - multiplier m
        'I' # unsigned int - multiplier n
        '4x' # padding
        '256s' # 256-character string - hex result
        '256s' # 256-character string - hex reflected result
    )
    for data in tools.test_iterator(tools.MATLAB.yield_stimulus(unpacker, 3)):
        ainit, asign, am, an, binit, bsign, bm, bn, add, radd = data
        ainit = ainit.decode()
        binit = binit.decode()
        add = add.decode()
        radd = radd.decode()

        a = uut.FixedPoint(ainit, asign, am, an, rounding='in')
        aa = uut.FixedPoint(a)
        b = uut.FixedPoint(binit, bsign, bm, bn, rounding='in')

        result = int(add, 16)
        rresult = int(radd, 16)

        # Addition is commutative, so both results should be equal
        nose.tools.assert_equal(result, rresult)

        # __mul__
        x = a * b
        y = b * a
        # MATLAB adds an extra sign bit for negative results
        result &= x.bitmask
        rresult &= y.bitmask
        # Expected results from MATLAB
        nose.tools.assert_equal(x.bits, result)
        nose.tools.assert_equal(y.bits, rresult)

        # Operands should not change
        nose.tools.assert_equal(a.bits, int(ainit, 2))
        nose.tools.assert_equal(b.bits, int(binit, 2))

        # __imul__
        a *= b
        b *= aa
        nose.tools.assert_equal(a.bits, result)
        nose.tools.assert_equal(b.bits, rresult)
        nose.tools.assert_equal(a.qformat, b.qformat)

        # __rmul__
        floater = random.getrandbits(52) * 2**-random.randrange(52) * random.choice([1, -1])
        reflected = floater * a
        regular = a * floater
        nose.tools.assert_equal(regular, reflected)
        nose.tools.assert_equal(regular.qformat, reflected.qformat)


@tools.setup(progress_bar=False)
def test_unsupported_operators():
    """Verify unsupported operators
    """
    def unsupported_operator(op, func):
        """Verify error messages on unsupported operators
        """
        # Indicate what we're testing in the nose printout
        sys.stderr.write(f'\b\b\b\b\b\b: {op} ... ')

        a = uut.FixedPoint(random.getrandbits(10))
        b = uut.FixedPoint(random.getrandbits(10))
        f = 1.0
        d = 1

        regex = re.escape(op.replace('%', '%%'))
        errmsg = f"unsupported operand type\\(s\\) for {regex}: %r and %r"

        with nose.tools.assert_raises_regex(TypeError, errmsg % ('FixedPoint', 'FixedPoint')):
            func(a, b)
        with nose.tools.assert_raises_regex(TypeError, errmsg % ('FixedPoint', 'int')):
            func(a, d)
        with nose.tools.assert_raises_regex(TypeError, errmsg % ('int', 'FixedPoint')):
            func(d, b)
        with nose.tools.assert_raises_regex(TypeError, errmsg % ('float', 'FixedPoint')):
            func(f, b)
        with nose.tools.assert_raises_regex(TypeError, errmsg % ('FixedPoint', 'float')):
            func(a, f)

    for args in [
        ('@', operator.matmul),
        ('@=', operator.imatmul),
        ('/', operator.truediv),
        ('/=', operator.itruediv),
    ]:
        yield unsupported_operator, *args


@nose.tools.nottest
def divfloatgen():
    """Generate floats such that the quotient won't lose precision."""
    for nbit in tools.test_iterator():
        divok, modok = False, False
        while not (divok and modok):
            s1, s2 = random.randrange(2), random.randrange(2)
            m1, m2 = random.randint(1, 52), random.randint(1, 52)
            n1, n2 = random.randint(0, 52 - m1), random.randint(0, 52 - m2)
            init1 = tools.random_float(s1, m1, n1, {})
            init2 = tools.random_float(s2, m2, n2, {})
            divok = init2 != 0 and (uut.FixedPoint.min_m(init1) +
                                    uut.FixedPoint.min_n(init2)) < 51
            modok = init2 != 0 and (uut.FixedPoint.min_m(init2) +
                                    max(uut.FixedPoint.min_n(x)
                                        for x in (init1, init2))) < 51

        yield init1, init2


@tools.setup(progress_bar=True)
def test_floordiv():
    """Verify //, //=
    """
    roundings = tuple(x.name for x in uut.properties.Rounding)
    errmsg = r"integer division or modulo by zero"
    for fnum, fden in divfloatgen():
        rounding = random.choice(roundings)
        num = uut.FixedPoint(fnum, rounding=rounding)
        nnum = uut.FixedPoint(num)
        m, n = num.m, num.n
        den = uut.FixedPoint(fden, rounding=rounding)

        if den.bits == 0:
            with nose.tools.assert_raises_regex(ZeroDivisionError, errmsg):
                num // den
            with nose.tools.assert_raises_regex(ZeroDivisionError, errmsg):
                num // fden
            with nose.tools.assert_raises_regex(ZeroDivisionError, errmsg):
                fnum // den
            with nose.tools.assert_raises_regex(ZeroDivisionError, errmsg):
                num //= den
            with nose.tools.assert_raises_regex(ZeroDivisionError, errmsg):
                num //= fden
            continue

        exp = uut.FixedPoint(fnum // fden, rounding=rounding)
        # __floordiv__
        nose.tools.assert_equal(num // den, exp, f"\n\n{num!r}\n\n{den!r}\n\n")

        # __floordiv__ with implicit cast
        nose.tools.assert_equal(num // fden, exp)

        # __rfloordiv__
        nose.tools.assert_equal(fnum // den, exp)

        # __ifloordiv__
        num //= den
        nose.tools.assert_equal(num, exp)

        # __ifloordiv__ with implicit cast
        nnum //= fden
        nose.tools.assert_equal(nnum, exp)

        # Check bit widths
        if fnum < 0 or fden < 0:
            nose.tools.assert_equal(num.m, m + den.n + 1)
            nose.tools.assert_equal(num.n, den.m + n)
            nose.tools.assert_true(num.signed)
        else:
            nose.tools.assert_equal(num.m, m + den.n)
            arg = 2**(den.m + n) - 2**(n - den.n)
            nose.tools.assert_equal(num.n, ceil(log2(arg)))
            nose.tools.assert_false(num.signed)

@tools.setup(progress_bar=True)
def test_modfloat():
    """Verify %, %= with float
    """
    roundings = tuple(x.name for x in uut.properties.Rounding)
    errmsg = r"integer division or modulo by zero"
    for fnum, fden in divfloatgen():
        rounding = random.choice(roundings)
        rounding = 'convergent'
        num = uut.FixedPoint(fnum, rounding=rounding)
        nnum = uut.FixedPoint(num)
        m, n = num.m, num.n
        den = uut.FixedPoint(fden, rounding=rounding)

        if den.bits == 0:
            with nose.tools.assert_raises_regex(ZeroDivisionError, errmsg):
                num % den
            with nose.tools.assert_raises_regex(ZeroDivisionError, errmsg):
                num % fden
            with nose.tools.assert_raises_regex(ZeroDivisionError, errmsg):
                fnum % den
            with nose.tools.assert_raises_regex(ZeroDivisionError, errmsg):
                num %= den
            with nose.tools.assert_raises_regex(ZeroDivisionError, errmsg):
                num %= fden
            continue

        exp = uut.FixedPoint(fnum % fden, rounding=rounding)
        # __mod__
        nose.tools.assert_equal(num % den, exp, f"\n\n{num!r}\n\n{den!r}\n\n{exp!r}\n\n")

        # __mod__ with implicit cast
        nose.tools.assert_equal(num % fden, exp)

        # __rmod__
        nose.tools.assert_equal(fnum % den, exp)

        # __imod__
        num %= den
        nose.tools.assert_equal(num, exp)

        # __imod__ with implicit cast
        nnum %= fden
        nose.tools.assert_equal(nnum, exp)

        # Check bit widths
        nose.tools.assert_equal(num.signed, den.signed)
        nose.tools.assert_equal(num.m, den.m)
        nose.tools.assert_equal(num.n, max(n, den.n))


@tools.setup(progress_bar=True)
def test_modint():
    """Verify %, %= with int
    """
    roundings = tuple(x.name for x in uut.properties.Rounding)
    errmsg = r"integer division or modulo by zero"
    for a, b in zip(initint_gen(), initint_gen()):
        rounding = random.choice(roundings)
        num = uut.FixedPoint(inum := a[0], *a[1], *a[2], rounding=rounding)
        nnum, m, n = uut.FixedPoint(num), num.m, num.n
        den = uut.FixedPoint(iden := b[0], *b[1], *b[2], rounding=rounding)

        if den.bits == 0:
            with nose.tools.assert_raises_regex(ZeroDivisionError, errmsg):
                num % den
            with nose.tools.assert_raises_regex(ZeroDivisionError, errmsg):
                num % iden
            with nose.tools.assert_raises_regex(ZeroDivisionError, errmsg):
                inum % den
            with nose.tools.assert_raises_regex(ZeroDivisionError, errmsg):
                num %= den
            with nose.tools.assert_raises_regex(ZeroDivisionError, errmsg):
                num %= iden
            continue

        exp = uut.FixedPoint(inum % iden, rounding=rounding)
        # __mod__
        nose.tools.assert_equal(num % den, exp, f"\n\n{num!r}\n\n{den!r}\n\n")

        # __mod__ with implicit cast
        nose.tools.assert_equal(num % iden, exp)

        # __rmod__
        nose.tools.assert_equal(inum % den, exp)

        # __imod__
        num %= den
        nose.tools.assert_equal(num, exp)

        # __imod__ with implicit cast
        nnum %= iden
        nose.tools.assert_equal(nnum, exp)

        # Check q format
        nose.tools.assert_equal(den.signed, num.signed)
        nose.tools.assert_equal(num.m, den.m)
        nose.tools.assert_equal(num.n, 0)


@tools.setup(progress_bar=True)
def test_divmod():
    """Verify divmod()
    """
    roundings = tuple(x.name for x in uut.properties.Rounding)
    for fnum, fden in divfloatgen():
        rounding = random.choice(roundings)
        num = uut.FixedPoint(fnum, rounding=rounding)
        den = uut.FixedPoint(fden, rounding=rounding)
        ediv, emod = num // den, num % den
        for div, mod in divmod(num, den), divmod(num, fden), divmod(fnum, den):
            tools.verify_attributes(div,
                bits=ediv.bits,
                signed=ediv.signed,
                m=ediv.m,
                n=ediv.n,
                str_base=16,
                rounding=ediv.rounding,
                overflow=ediv.overflow,
                overflow_alert=ediv.overflow_alert,
                mismatch_alert=ediv.mismatch_alert,
                implicit_cast_alert=ediv.implicit_cast_alert,
            )
            tools.verify_attributes(mod,
                bits=emod.bits,
                signed=emod.signed,
                m=emod.m,
                n=emod.n,
                str_base=16,
                rounding=emod.rounding,
                overflow=emod.overflow,
                overflow_alert=emod.overflow_alert,
                mismatch_alert=emod.mismatch_alert,
                implicit_cast_alert=emod.implicit_cast_alert,
            )


@nose.tools.with_setup(teardown=lambda: uut.FixedPoint.CALLBACK.update({'/': None}))
@tools.setup(progress_bar=True)
def test_callback_operators():
    """Verify callback operators
    """
    def callback_operator(op, func):
        """Verify callbacks can be configured
        """
        sys.stderr.write(f'\b\b\b\b\b\b {op}: ... ')

        y = uut.FixedPoint(random.getrandbits(10))

        errmsg = f"unsupported operand type\\(s\\) for {re.escape(op)}: %r and %r"

        with nose.tools.assert_raises_regex(TypeError, errmsg % ('FixedPoint', 'FixedPoint')):
            func(y, y)
        with nose.tools.assert_raises_regex(TypeError, errmsg % ('FixedPoint', 'int')):
            func(y, random.randint(-100, 100))
        with nose.tools.assert_raises_regex(TypeError, errmsg % ('int', 'FixedPoint')):
            func(random.randint(-100, 100), y)
        with nose.tools.assert_raises_regex(TypeError, errmsg % ('float', 'FixedPoint')):
            func(random.random() - 0.5, y)
        with nose.tools.assert_raises_regex(TypeError, errmsg % ('FixedPoint', 'float')):
            func(y, random.random() - 0.5)

        for i, (a, b) in enumerate(zip(nondefault_props_gen(), nondefault_props_gen())):
            x = uut.FixedPoint(a[0], *a[1], **a[2])
            y = uut.FixedPoint(b[0], *b[1], **b[2])
            x.mismatch_alert = 'ignore'
            y.mismatch_alert = 'ignore'
            uut.FixedPoint.CALLBACK[op[0]] = lambda left, right: uut.FixedPoint(i)
            for result in (func(x, y),
                           func(x, random.randint(-100, 100)),
                           func(random.randint(-100, 100), x)):
                tools.verify_attributes(result,
                                        signed=False,
                                        m=uut.FixedPoint.min_m(i) or 1,
                                        n=0,
                                        bits=i,
                                        str_base=16,
                                        rounding='nearest',
                                        overflow='clamp',
                                        overflow_alert='error',
                                        mismatch_alert='warning',
                                        implicit_cast_alert='warning')

        uut.FixedPoint.CALLBACK[op[0]] = None
        with nose.tools.assert_raises_regex(TypeError, errmsg % ('FixedPoint', 'FixedPoint')):
            func(y, y)
        with nose.tools.assert_raises_regex(TypeError, errmsg % ('FixedPoint', 'int')):
            func(y, random.randint(-100, 100))
        with nose.tools.assert_raises_regex(TypeError, errmsg % ('int', 'FixedPoint')):
            func(random.randint(-100, 100), y)
        with nose.tools.assert_raises_regex(TypeError, errmsg % ('float', 'FixedPoint')):
            func(random.random() - 0.5, y)
        with nose.tools.assert_raises_regex(TypeError, errmsg % ('FixedPoint', 'float')):
            func(y, random.random() - 0.5)

    for args in  [
        ('/', operator.truediv),
        ('/=', operator.itruediv),
        ('@', operator.matmul),
        ('@=', operator.imatmul),
    ]:
        yield callback_operator, *args


@tools.setup(progress_bar=True)
def test_power():
    """Verify **, **=
    """
    errmsg = [
        r"unsupported operand type\(s\) for \*\* or pow\(\): %r and 'FixedPoint'",
        r'Only positive integers are supported for exponentiation\.',
    ]
    for init, _, _, s, m, _, bits in initint_gen():
        x = uut.FixedPoint(init)

        # With fixedpoint as exponent
        y = random.randint(-1000, 1000)
        with nose.tools.assert_raises_regex(TypeError, errmsg[0] % 'int'):
            y**x
        with nose.tools.assert_raises_regex(TypeError, errmsg[0] % 'int'):
            y **= x

        y = random.random()
        with nose.tools.assert_raises_regex(TypeError, errmsg[0] % 'float'):
            y**x
        with nose.tools.assert_raises_regex(TypeError, errmsg[0] % 'float'):
            y **= x

        # Non-integer exponent
        with nose.tools.assert_raises_regex(TypeError, errmsg[1]):
            x**y
        with nose.tools.assert_raises_regex(TypeError, errmsg[1]):
            x **= y

        # Non-positive exponent
        y = -random.randrange(tools.NUM_ITERATIONS)
        with nose.tools.assert_raises_regex(TypeError, errmsg[1]):
            x**y
        with nose.tools.assert_raises_regex(TypeError, errmsg[1]):
            x **= y

        y = random.randrange(30) + 1
        z = x**y
        nose.tools.assert_equal(z.m, x.m * y)
        nose.tools.assert_equal(z.n, x.n * y)
        nose.tools.assert_equal(z < 0, x < 0 and y % 2)
        nose.tools.assert_equal(z > 0, x > 0 or (y % 2 == 0 and x.bits != 0))
        nose.tools.assert_equal(int(x)**y, int(z))

        xx = uut.FixedPoint(x)
        xx **= y
        nose.tools.assert_equal(z.m, xx.m)
        nose.tools.assert_equal(z.n, xx.n)
        nose.tools.assert_equal(z < 0, xx < 0)
        nose.tools.assert_equal(z > 0, xx > 0)
        nose.tools.assert_equal(int(xx), int(z))

@tools.setup(progress_bar=True)
def test_left_shift():
    """Verify <<, <<=
    """
    errmsg = [
        r"unsupported operand type\(s\) for <<: 'int' and 'FixedPoint'",
        r"unsupported operand type\(s\) for <<=: 'int' and 'FixedPoint'",
    ]
    for init, args, kwargs, s, m, n, bits in initstr_gen():
        x = uut.FixedPoint(init, *args)

        bitmask = 2**len(x) - 1

        # Choose at most 10 shift values to test
        shifts = random.sample(list(range(len(x) + 1)), min(10, len(x)))
        for shift in shifts:
            expected = (bits << shift) & bitmask
            y = x << shift
            nose.tools.assert_equal(y.bits, expected)

            x <<= shift
            nose.tools.assert_equal(x.bits, expected)
            x.from_string(hex(bits))

            # Account for sign extension
            if x.signed and x.bits['msb']:
                # Get the negative representation
                expected = bits & (posmask := (bitmask >> 1))
                expected -= bits & (posmask + 1)
                # Now perform the shift and then mask away bits
                expected = (expected >> shift) & bitmask
            else:
                expected = (bits >> shift) & bitmask

            y = x << -shift
            nose.tools.assert_equal(y.bits, expected)

            x <<= -shift
            nose.tools.assert_equal(x.bits, expected)
            x.from_string(hex(bits))

            with nose.tools.assert_raises_regex(TypeError, errmsg[0]):
                shift << x
            with nose.tools.assert_raises_regex(TypeError, errmsg[1]):
                shift <<= x

    # Verify that passing in something other than a string throws an error
    errmsg = re.escape(f'Expected {type(1)}; got {type(1.0)}.')
    with nose.tools.assert_raises_regex(TypeError, errmsg):
        x << 1.0
    with nose.tools.assert_raises_regex(TypeError, errmsg):
        x <<= 1.0

@tools.setup(progress_bar=True)
def test_right_shift():
    """Verify >>, >>=
    """
    errmsg = [
        r"unsupported operand type\(s\) for >>: 'int' and 'FixedPoint'",
        r"unsupported operand type\(s\) for >>=: 'int' and 'FixedPoint'",
    ]
    for init, args, kwargs, s, m, n, bits in initstr_gen():
        x = uut.FixedPoint(init, *args)

        bitmask = 2**len(x) - 1

        # Choose at most 10 shift values to test
        shifts = random.sample(list(range(len(x) + 1)), min(10, len(x)))
        for shift in shifts:
            expected = (bits << shift) & bitmask
            y = x >> -shift
            nose.tools.assert_equal(y.bits, expected)

            x >>= -shift
            nose.tools.assert_equal(x.bits, expected)
            x.from_string(hex(bits))

            # Account for sign extension
            if x.signed and x.bits['msb']:
                # Get the negative representation
                expected = bits & (posmask := (bitmask >> 1))
                expected -= bits & (posmask + 1)
                # Now perform the shift and then mask away bits
                expected = (expected >> shift) & bitmask
            else:
                expected = (bits >> shift) & bitmask

            y = x >> shift
            nose.tools.assert_equal(y.bits, expected)

            x >>= shift
            nose.tools.assert_equal(x.bits, expected)
            x.from_string(hex(bits))

            with nose.tools.assert_raises_regex(TypeError, errmsg[0]):
                shift >> x
            with nose.tools.assert_raises_regex(TypeError, errmsg[1]):
                shift >>= x

    # Verify that passing in something other than a string throws an error
    errmsg = re.escape(f'Expected {type(1)}; got {type(1.0)}.')
    with nose.tools.assert_raises_regex(TypeError, errmsg):
        x >> 1.0
    with nose.tools.assert_raises_regex(TypeError, errmsg):
        x >>= 1.0

@tools.setup(progress_bar=True)
def test_bitwise_and():
    """Verify &, &=
    """
    prev = uut.FixedPoint(random.random(), random.randrange(2))
    for init, args, kwargs, s, m, n, bits in initstr_gen():
        a = uut.FixedPoint(init, *args)

        exp = a.bits & prev.bits

        # FixedPoint & FixedPoint
        x = a & prev
        nose.tools.assert_equal(x.bits, exp)

        # FixedPoint & int
        y = a & prev.bits
        nose.tools.assert_equal(y.bits, exp)

        # int & FixedPoint
        z = a.bits & prev
        nose.tools.assert_equal(z.bits, exp)

        # __iand__
        with a:
            a &= prev
            nose.tools.assert_equal(a.bits, exp)

        prev = a

    # Verify that passing in something other than an int throws an error
    errmsg = re.escape(f'Expected {type(1)} or {type(x)}; got {type(1.0)}.')
    with nose.tools.assert_raises_regex(TypeError, errmsg):
        x & 1.0
    with nose.tools.assert_raises_regex(TypeError, errmsg):
        x &= 1.0

@tools.setup(progress_bar=True)
def test_bitwise_or():
    """Verify |, |=
    """
    prev = uut.FixedPoint(random.random(), random.randrange(2))
    for init, args, kwargs, s, m, n, bits in initstr_gen():
        x = uut.FixedPoint(init, *args)

        pexp = (bitmask := (x.bits | prev.bits)) & prev.bitmask
        xexp = bitmask & x.bitmask

        # FixedPoint | FixedPoint
        a = x | prev
        nose.tools.assert_equal(a.bits, xexp)
        b = prev | x
        nose.tools.assert_equal(b.bits, pexp)

        # FixedPoint | int
        c = x | prev.bits
        nose.tools.assert_equal(c.bits, xexp)
        d = prev | x.bits
        nose.tools.assert_equal(d.bits, pexp)

        # int | FixedPoint
        e = x.bits | prev
        nose.tools.assert_equal(e.bits, pexp)
        f = prev.bits | x
        nose.tools.assert_equal(f.bits, xexp)

        # __ior__
        with x:
            x |= prev
            nose.tools.assert_equal(x.bits, xexp)
        with x:
            x |= prev.bits
            nose.tools.assert_equal(x.bits, xexp)
        with prev:
            prev |= x
            nose.tools.assert_equal(prev.bits, pexp)
        prev |= x.bits
        nose.tools.assert_equal(prev.bits, pexp)

        prev = a

    # Verify that passing in something other than an int throws an error
    errmsg = re.escape(f'Expected {type(1)} or {type(x)}; got {type(1.0)}.')
    with nose.tools.assert_raises_regex(TypeError, errmsg):
        x | 1.0
    with nose.tools.assert_raises_regex(TypeError, errmsg):
        x |= 1.0

@tools.setup(progress_bar=True)
def test_bitwise_xor():
    """Verify ^, ^=
    """
    prev = uut.FixedPoint(random.random(), random.randrange(2))
    for init, args, kwargs, s, m, n, bits in initstr_gen():
        x = uut.FixedPoint(init, *args)

        pexp = (bitmask := x.bits ^ prev.bits) & prev.bitmask
        xexp = bitmask & x.bitmask

        # FixedPoint ^ FixedPoint
        a = x ^ prev
        nose.tools.assert_equal(a.bits, xexp)
        b = prev ^ x
        nose.tools.assert_equal(b.bits, pexp)

        # FixedPoint ^ int
        c = x ^ prev.bits
        nose.tools.assert_equal(c.bits, xexp)
        d = prev ^ x.bits
        nose.tools.assert_equal(d.bits, pexp)

        # int ^ FixedPoint
        e = x.bits ^ prev
        nose.tools.assert_equal(e.bits, pexp)
        f = prev.bits ^ x
        nose.tools.assert_equal(f.bits, xexp)

        # __ixor__
        with x:
            x ^= prev
            nose.tools.assert_equal(x.bits, xexp)
        with x:
            x ^= prev.bits
            nose.tools.assert_equal(x.bits, xexp)
        with prev:
            prev ^= x
            nose.tools.assert_equal(prev.bits, pexp)
        prev ^= x.bits
        nose.tools.assert_equal(prev.bits, pexp)

        prev = a

    # Verify that passing in something other than an int throws an error
    errmsg = re.escape(f'Expected {type(1)} or {type(x)}; got {type(1.0)}.')
    with nose.tools.assert_raises_regex(TypeError, errmsg):
        x ^ 1.0
    with nose.tools.assert_raises_regex(TypeError, errmsg):
        x ^= 1.0

@tools.setup(progress_bar=True)
def test_negation_operator():
    """Verify unary -
    """
    errmsg = [
        r'\[SN\d+\]:? Negating 0?[box]?[\da-f]+ \(Q%d\.%d\) causes overflow\.',
        r'WARNING \[SN\d+\]: Adjusting Q format to Q%s\.%s to allow negation\.',
        r'Unsigned numbers cannot be negated\.',
    ]
    for init, args, kwargs, _, _, _, _ in nondefault_props_gen():
        x = uut.FixedPoint(init, *args, **kwargs)
        UTLOG.info("TEST VECTOR: %d", x._FixedPoint__id['extra']['sn'], **LOGID)

        if not x.signed:
            with nose.tools.assert_raises_regex(uut.FixedPointError, errmsg[2]):
                -x

            # Change to max negative for coverage
            x.m += 1
            x.signed = True
            x.from_string(str(1 << (len(x) - 1)))

        # Overflow condition: maximum negative
        m_exp = x.m
        if x.bits['msb'] == 1 and x.bits[1:] == 0:
            m_exp += 1
            if x.overflow_alert == 'error':
                with nose.tools.assert_raises_regex(uut.FixedPointOverflowError, errmsg[0] % (x.m, x.n)):
                    -x
                x.overflow_alert = 'warning'

            if x.overflow_alert == 'warning':
                with tools.CaptureWarnings() as warn:
                    y = -x
                log = warn.logs
                nose.tools.assert_equal(len(log), 2)
                nose.tools.assert_regex(log[0], errmsg[0] % (x.m, x.n))
                nose.tools.assert_regex(log[1], errmsg[1] % (y.m, y.n))
                nose.tools.assert_equal(y.m, m_exp)
                x.overflow_alert = 'ignore'

        with tools.CaptureWarnings() as warn:
            y = -x
        nose.tools.assert_equal(len(warn.logs), 0, '\n\n'.join(warn.logs))

        nose.tools.assert_equal(x, -y, f'\n\n{x!r}\n\n{y!r}\n\n')
        nose.tools.assert_true(y.signed)
        nose.tools.assert_equal(y.m, m_exp)
        nose.tools.assert_equal(y.n, x.n)

@tools.setup(progress_bar=True)
def test_posation():
    """Verify unary +
    """
    # Every property except should be equivalent. Get a list of property
    # accessors for later
    properties = [
        name for name, attr in uut.FixedPoint.__dict__.items()
        if isinstance(attr, property)
    ]

    for init, args, kwargs, _, _, _, _ in nondefault_props_gen():
        x = uut.FixedPoint(init, *args, **kwargs)
        y = +x

        nose.tools.assert_equal(x, y)

        # Verify that other properties are unchanged
        for prop in properties:
            props = [z.__class__.__dict__[prop].fget(z) for z in [x,y]]
            nose.tools.assert_equal(*props)

@tools.setup(progress_bar=True)
def test_bitwise_inversion():
    """Verify unary ~
    """
    # Every property except bits and _signedint should be equivalent. Get a
    # list of property accessors for later
    properties = [
        name for name, attr in uut.FixedPoint.__dict__.items()
        if isinstance(attr, property) and name not in ['_signedint', 'bits']
    ]

    for init, args, kwargs, _, _, _, _ in nondefault_props_gen():
        x = uut.FixedPoint(init, *args, **kwargs)
        y = ~x

        # Verify that bits are inverted
        nose.tools.assert_equal(x.bits ^ y.bits, x.bitmask, f'{x:#x} & {y:#x}')

        # Verify that other properties are unchanged
        for prop in properties:
            props = [z.__class__.__dict__[prop].fget(z) for z in [x,y]]
            nose.tools.assert_equal(*props)

@tools.setup(progress_bar=True)
def test_comparisons():
    """Verify comparison
    """
    @tools.setup(progress_bar=True)
    def test_comparison_operator(op, func):
        """Verify comparisons
        """
        sys.stderr.write(f'\b\b\b\b\b {op} ... ')
        Lmax = 20
        overflow = [x.name for x in uut.properties.Overflow]
        rounding = [x.name for x in uut.properties.Rounding]
        strbases = list(uut.properties.StrConv.keys())
        alerts = [x.name for x in uut.properties.Alert]
        for i in tools.test_iterator():
            L = random.randrange(2, Lmax)
            s = random.randrange(2)
            m = random.randrange(s, L)
            n = random.randrange(m == 0, L - m)
            a = tools.random_float(s, m, n, {})
            x = uut.FixedPoint(a, s, m, n,
                overflow=random.choice(overflow),
                rounding=random.choice(rounding),
                str_base=random.choice(strbases),
                overflow_alert=random.choice(alerts),
                mismatch_alert=random.choice(alerts),
                implicit_cast_alert=random.choice(alerts),
            )

            L = random.randrange(2, Lmax)
            s = random.randrange(2)
            m = random.randrange(s, L)
            n = random.randrange(m == 0, L - m)
            b = tools.random_float(s, m, n, {})
            y = uut.FixedPoint(b, s, m, n,
                overflow=random.choice(overflow),
                rounding=random.choice(rounding),
                str_base=random.choice(strbases),
                overflow_alert=random.choice(alerts),
                mismatch_alert=random.choice(alerts),
                implicit_cast_alert=random.choice(alerts),
            )

            UTLOG.info("Iteration %d\na = %.20f\nb = %.20f", i, a, b, **LOGID)

            nose.tools.assert_equal(func(a, b), func(x, y), op + str(i))
            nose.tools.assert_equal(func(a, b), func(a, y), op + str(i))
            nose.tools.assert_equal(func(a, b), func(x, b), op + str(i))

    for args in [
        ('<', operator.lt),
        ('<=', operator.le),
        ('>', operator.gt),
        ('>=', operator.ge),
        ('==', operator.eq),
        ('!=', operator.ne),
    ]:
        yield test_comparison_operator, *args

