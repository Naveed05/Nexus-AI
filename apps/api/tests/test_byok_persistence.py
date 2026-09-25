from pathlib import Path

from nexus.core.models import EncryptedFileCredentialStore, ProviderNotConfiguredError


def test_encrypted_byok_store_survives_reconstruction(tmp_path: Path):
    path = tmp_path / "byok.json"
    first = EncryptedFileCredentialStore(str(path))
    first.set("local-user", "groq", "gsk_test_secret_value")
    assert first.get("local-user", "groq").masked().endswith("alue")

    second = EncryptedFileCredentialStore(str(path))
    assert second.get("local-user", "groq").key == "gsk_test_secret_value"


def test_encrypted_byok_store_delete_persists(tmp_path: Path):
    path = tmp_path / "byok.json"
    first = EncryptedFileCredentialStore(str(path))
    first.set("local-user", "groq", "gsk_test_secret_value")
    first.delete("local-user", "groq")

    second = EncryptedFileCredentialStore(str(path))
    try:
        second.get("local-user", "groq")
    except ProviderNotConfiguredError:
        return
    raise AssertionError("deleted credential was restored")
