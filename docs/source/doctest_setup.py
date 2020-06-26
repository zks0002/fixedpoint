import os
import sys
import re
import logging
import unittest.mock
from typing import Literal

from fixedpoint import FixedPoint
import fixedpoint.logging


def reset_sn(sn: int = 0) -> None:
    """Resets the FixedPoint serial number"""
    FixedPoint._SERIAL_NUMBER = sn


def alphabetize_mismatches(record: logging.LogRecord) -> Literal[True]:
    """Filters a log record and alphabetizes mismatches"""
    newargs = list(record.args)
    for i, warning in enumerate(newargs):
        if not isinstance(warning, list):
            continue
        props = re.search(r"\['([a-z]+)', '([a-z]+)'\]", arg := str(warning))
        if not props:
            continue
        sub = sorted([props.group(x) for x in (1, 2)])
        newargs[i] = arg.replace(props.group(0), str(sub))

    record.args = tuple(newargs)

    return True


def patch_min_n(rval: int = 2) -> unittest.mock._patch:
    """Patches FixedPoint.min_n to always return the same value"""
    patcher = unittest.mock.patch('fixedpoint.FixedPoint.min_n',
                                  return_value=rval)
    patcher.start()
    return patcher


def unpatch(patcher: unittest.mock._patch) -> None:
    """Returns the patched object to normal functionality"""
    patcher.stop()


# Make warnings print to stdout instead of stderr
fixedpoint.logging.WARNER_CONSOLE_HANDLER.stream = sys.stdout
fixedpoint.logging.WARNER.removeFilter(alphabetize_mismatches)
fixedpoint.logging.WARNER.addFilter(alphabetize_mismatches)


# A way to select specific doctests to run
def should_skip(testname: str) -> bool:
    """Determines if a test should be skipped."""
    envvar = os.environ.get('FIXEDPOINTDOCTEST', '')
    enabled = [x.strip() for x in envvar.split(',;:') if x]
    return bool(envvar and testname not in enabled)
