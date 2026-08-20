"""Test configuration: fail immediately if code attempts network access."""

from __future__ import annotations

import socket
from collections.abc import Iterator

import pytest


@pytest.fixture(autouse=True)
def block_network(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    def denied(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("tests must not access the network")

    monkeypatch.setattr(socket, "socket", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    yield
