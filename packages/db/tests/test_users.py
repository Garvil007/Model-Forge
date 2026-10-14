from __future__ import annotations

from typing import Any

from modelforge_db import KmsEncryptor, NotFoundError, UserRepository

from .conftest import unique_id


def test_create_and_get_by_id(table: Any) -> None:
    repo = UserRepository(table)
    user_id = unique_id()

    created = repo.create(user_id, f"{user_id}@example.com", plan="pro", settings={"theme": "dark"})
    fetched = repo.get_by_id(user_id)

    assert fetched == created
    assert fetched.plan == "pro"
    assert fetched.settings == {"theme": "dark"}


def test_get_by_id_missing_raises_not_found(table: Any) -> None:
    repo = UserRepository(table)

    try:
        repo.get_by_id(unique_id())
    except NotFoundError:
        pass
    else:
        raise AssertionError("expected NotFoundError")


def test_get_by_email_finds_user(table: Any) -> None:
    repo = UserRepository(table)
    user_id = unique_id()
    email = f"{user_id}@example.com"
    repo.create(user_id, email)

    found = repo.get_by_email(email)

    assert found is not None
    assert found.user_id == user_id


def test_get_by_email_is_case_insensitive(table: Any) -> None:
    repo = UserRepository(table)
    user_id = unique_id()
    email = f"{user_id}@Example.com"
    repo.create(user_id, email)

    found = repo.get_by_email(email.upper())

    assert found is not None
    assert found.user_id == user_id


def test_get_by_email_returns_none_when_absent(table: Any) -> None:
    repo = UserRepository(table)

    assert repo.get_by_email(f"{unique_id()}@example.com") is None


def test_update_settings_merges_into_existing_user(table: Any) -> None:
    repo = UserRepository(table)
    user_id = unique_id()
    repo.create(user_id, f"{user_id}@example.com")

    updated = repo.update_settings(user_id, {"notifications": False})

    assert updated.settings == {"notifications": False}
    assert repo.get_by_id(user_id).settings == {"notifications": False}


def test_update_settings_on_missing_user_raises_not_found(table: Any) -> None:
    repo = UserRepository(table)

    try:
        repo.update_settings(unique_id(), {})
    except NotFoundError:
        pass
    else:
        raise AssertionError("expected NotFoundError")


def test_hf_token_round_trips_through_kms_encryption(table: Any, kms_key_id: str) -> None:
    repo = UserRepository(table)
    user_id = unique_id()
    repo.create(user_id, f"{user_id}@example.com")
    encryptor = KmsEncryptor(kms_key_id)

    repo.set_hf_token(user_id, "hf_super_secret_token", encryptor)

    stored_ciphertext = repo.get_by_id(user_id).hf_token_ciphertext
    assert stored_ciphertext is not None
    assert "hf_super_secret_token" not in stored_ciphertext
    assert repo.get_hf_token(user_id, encryptor) == "hf_super_secret_token"


def test_get_hf_token_returns_none_when_never_set(table: Any) -> None:
    repo = UserRepository(table)
    user_id = unique_id()
    repo.create(user_id, f"{user_id}@example.com")

    assert repo.get_by_id(user_id).hf_token_ciphertext is None
