"""
Encryption at rest for stored provider credentials (BYOK).

Fernet with a single master key from `settings.credential_encryption_key`
protects against a stolen DB dump - an attacker with the Postgres data
alone can't read tenant LLM keys. It does NOT protect against an attacker
who also has the running app's environment/secret store; that requires
envelope encryption via a real KMS (AWS/GCP/Vault). This module is the
deliberate upgrade seam: swap the two functions below for `boto3` KMS
`encrypt`/`decrypt` calls (or equivalent) without touching any caller.

Key rotation is out of scope for v1 - rotating `CREDENTIAL_ENCRYPTION_KEY`
requires re-encrypting every `ProviderCredential` row (a one-off script);
`cryptography.fernet.MultiFernet` supports rotation-with-grace-period if
that becomes necessary later.
"""
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from neurowave_engine.core.config import settings


class CredentialEncryptionError(Exception):
    pass


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    if not settings.credential_encryption_key:
        raise CredentialEncryptionError(
            "CREDENTIAL_ENCRYPTION_KEY is not set - required to store or read BYOK provider credentials. "
            "Generate one with: python -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\""
        )
    return Fernet(settings.credential_encryption_key.encode())


def encrypt_credential(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_credential(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as e:
        raise CredentialEncryptionError("Stored credential could not be decrypted - key mismatch or corrupt data") from e
