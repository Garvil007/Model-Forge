"""Envelope encryption for secrets (e.g. the user's Hugging Face token) via AWS KMS."""

from __future__ import annotations

import base64
from dataclasses import dataclass

from .client import get_kms_client


@dataclass(frozen=True)
class KmsEncryptor:
    key_id: str

    def encrypt(self, plaintext: str) -> str:
        response = get_kms_client().encrypt(
            KeyId=self.key_id, Plaintext=plaintext.encode("utf-8")
        )
        return base64.b64encode(response["CiphertextBlob"]).decode("ascii")

    def decrypt(self, ciphertext_b64: str) -> str:
        blob = base64.b64decode(ciphertext_b64)
        response = get_kms_client().decrypt(CiphertextBlob=blob)
        return response["Plaintext"].decode("utf-8")
