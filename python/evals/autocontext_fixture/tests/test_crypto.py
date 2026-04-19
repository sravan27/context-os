"""Crypto tests."""
from src.utils.crypto import hash_password, verify_password


def test_hash_verify_roundtrip():
    stored = hash_password("hunter2")
    assert verify_password("hunter2", stored)
    assert not verify_password("wrong", stored)


def test_verify_rejects_garbage():
    assert not verify_password("x", "not-a-hash")
