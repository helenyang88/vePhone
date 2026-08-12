import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

_ENVELOPE_VERSION = 1
_NONCE_LENGTH = 12
_MIN_ENVELOPE_LENGTH = 1 + _NONCE_LENGTH + 16 + 1


class SettingDecryptionError(RuntimeError):
    pass


class SettingCipher:
    def __init__(self, aes: AESGCM) -> None:
        self._aes = aes

    @classmethod
    def from_secret(cls, secret: str) -> "SettingCipher":
        key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b"mua-platform/settings/v1",
            info=b"setting-encryption",
        ).derive(secret.encode())
        return cls(AESGCM(key))

    def encrypt(self, key: str, plaintext: str) -> bytes:
        nonce = os.urandom(_NONCE_LENGTH)
        encrypted = self._aes.encrypt(
            nonce,
            plaintext.encode(),
            key.encode(),
        )
        return bytes([_ENVELOPE_VERSION]) + nonce + encrypted

    def decrypt(self, key: str, ciphertext: bytes) -> str:
        try:
            if (
                not isinstance(ciphertext, bytes)
                or len(ciphertext) < _MIN_ENVELOPE_LENGTH
                or ciphertext[0] != _ENVELOPE_VERSION
            ):
                raise ValueError
            nonce = ciphertext[1 : 1 + _NONCE_LENGTH]
            encrypted = ciphertext[1 + _NONCE_LENGTH :]
            return self._aes.decrypt(nonce, encrypted, key.encode()).decode()
        except (InvalidTag, UnicodeDecodeError, ValueError, TypeError) as exc:
            raise SettingDecryptionError("setting_decryption_failed") from exc
