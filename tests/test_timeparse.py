from datetime import timedelta

import pytest

from bot.utils.timeparse import parse_duration


def test_parse_duration_compound() -> None:
    assert parse_duration("1h30m") == timedelta(minutes=90)
    assert parse_duration("2d 4h") == timedelta(days=2, hours=4)


def test_parse_duration_rejects_invalid() -> None:
    with pytest.raises(ValueError):
        parse_duration("tomorrow")
    with pytest.raises(ValueError):
        parse_duration("1s")
