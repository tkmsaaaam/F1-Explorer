from unittest.mock import MagicMock

import pytest

import analyze_practice
import analyze_qualifying


@pytest.mark.parametrize("loader", [analyze_practice._circuit_info_or_none, analyze_qualifying._circuit_info_or_none])
def test_circuit_info_failure_is_non_fatal(loader):
    session = MagicMock()
    session.get_circuit_info.side_effect = AttributeError("add_marker_distance")
    log = MagicMock()

    assert loader(session, log) is None
    log.warning.assert_called_once()
