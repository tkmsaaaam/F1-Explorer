"""Scalar boundary conversions retain builtin values and missing-data behavior."""
from datetime import timedelta
from decimal import Decimal
import math

import numpy as np
import pandas as pd
import pytest

from f1_explorer.scalars import as_float, as_int, as_seconds


@pytest.mark.parametrize('value', [2, -1.5, '2', b'2', bytearray(b'2'), memoryview(b'2'), Decimal('2.5'), np.int64(2), np.float64(2.5)])
def test_numeric_conversions_match_builtins(value):
    assert as_float(value) == float(value)
    assert as_int(value) == int(value)


@pytest.mark.parametrize('value', [None, pd.NA, object()])
@pytest.mark.parametrize('convert', [as_float, as_int])
def test_missing_and_unsupported_values_are_not_zero(value, convert):
    with pytest.raises(TypeError):
        convert(value)


def test_seconds_preserve_fraction_and_missing_value():
    assert as_seconds(timedelta(seconds=1.25)) == 1.25
    assert as_seconds(pd.Timedelta(1250, unit="ms")) == 1.25
    assert math.isnan(as_seconds(pd.NaT))
    assert math.isnan(as_float(float('nan')))
    with pytest.raises(TypeError):
        as_seconds(1250)
