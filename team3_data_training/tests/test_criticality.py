import pytest

from dags.common.gx_helpers import calculate_criticality


@pytest.mark.parametrize(
    "missing_column,invalid_percentage,expected",
    [
        (True, 0.0, "high"),
        (False, 51.0, "high"),
        (False, 100.0, "high"),
        (False, 10.0, "medium"),
        (False, 50.0, "medium"),
        (False, 30.0, "medium"),
        (False, 5.0, "low"),
        (False, 0.1, "low"),
        (False, 0.0, "none"),
    ],
)
def test_calculate_criticality(missing_column, invalid_percentage, expected):
    assert calculate_criticality(missing_column, invalid_percentage) == expected
