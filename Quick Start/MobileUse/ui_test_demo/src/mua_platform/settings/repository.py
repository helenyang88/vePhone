from collections.abc import Mapping
from datetime import UTC, datetime

from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from mua_platform.settings.crypto import SettingCipher, SettingDecryptionError
from mua_platform.settings.models import Setting


class SettingRepository:
    def __init__(
        self,
        db: Session,
        cipher: SettingCipher,
        fallbacks: Mapping[str, str] | None = None,
    ) -> None:
        self.db = db
        self.cipher = cipher
        self.fallbacks = fallbacks or {}

    def get(self, key: str) -> str | None:
        setting = self.db.get(Setting, key)
        if setting is None:
            return self.fallbacks.get(key)
        try:
            return self.cipher.decrypt(key, setting.encrypted_value)
        except SettingDecryptionError:
            return self.fallbacks.get(key)

    def set_many(self, values: Mapping[str, str]) -> datetime:
        if any(value == "" for value in values.values()):
            raise ValueError("setting_value_must_not_be_empty")

        updated_at = datetime.now(UTC)
        for key, plaintext in values.items():
            encrypted_value = self.cipher.encrypt(key, plaintext)
            statement = insert(Setting).values(
                key=key,
                encrypted_value=encrypted_value,
                updated_at=updated_at,
            )
            self.db.execute(
                statement.on_conflict_do_update(
                    index_elements=[Setting.key],
                    set_={
                        "encrypted_value": encrypted_value,
                        "updated_at": updated_at,
                    },
                )
            )
        self.db.flush()
        return updated_at
