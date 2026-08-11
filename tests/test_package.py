"""Smoke tests for the initial package layout."""

import nexagent


def test_package_imports() -> None:
    assert nexagent.__doc__ == "NexAgent package."
