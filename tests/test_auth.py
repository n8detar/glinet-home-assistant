from __future__ import annotations

import hashlib

import pytest

from custom_components.glinet_router.api import (
    GLiNetUnsupportedAlgorithm,
    build_login_hash,
)


def test_build_login_hash_negotiates_sha256(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "custom_components.glinet_router.api._password_crypt",
        lambda password, salt, algorithm: "$5$test$crypt",
    )

    result = build_login_hash(
        username="root",
        password="secret",
        salt="0123456789abcdef",
        nonce="nonce",
        algorithm=5,
        hash_method="sha256",
    )

    expected = hashlib.sha256(b"root:$5$test$crypt:nonce").hexdigest()
    assert result == expected


def test_build_login_hash_rejects_unknown_crypt_algorithm() -> None:
    with pytest.raises(GLiNetUnsupportedAlgorithm, match="crypt algorithm"):
        build_login_hash(
            username="root",
            password="secret",
            salt="salt",
            nonce="nonce",
            algorithm=99,
            hash_method="sha256",
        )


def test_build_login_hash_rejects_unknown_outer_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "custom_components.glinet_router.api._password_crypt",
        lambda password, salt, algorithm: "$5$test$crypt",
    )

    with pytest.raises(GLiNetUnsupportedAlgorithm, match="hash method"):
        build_login_hash(
            username="root",
            password="secret",
            salt="0123456789abcdef",
            nonce="nonce",
            algorithm=5,
            hash_method="sha3-999",
        )
