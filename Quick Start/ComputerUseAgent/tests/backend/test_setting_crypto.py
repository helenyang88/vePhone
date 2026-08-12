from datetime import UTC
import subprocess
import sys

import pytest
from sqlalchemy import select

from cua_platform.db import Base, create_engine_and_session
from cua_platform.settings.crypto import SettingCipher, SettingDecryptionError
from cua_platform.settings.models import Setting
from cua_platform.settings.repository import SettingRepository
from cua_platform.settings.service import SettingsService


def test_settings_public_api_imports_in_fresh_process():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from cua_platform.settings import "
                "Setting, SettingCipher, SettingDecryptionError, SettingRepository"
            ),
        ],
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_cipher_uses_random_nonce_and_key_as_aad():
    cipher = SettingCipher.from_secret("x" * 32)

    first = cipher.encrypt("runner.secret_access_key", "same-secret")
    second = cipher.encrypt("runner.secret_access_key", "same-secret")

    assert first != second
    assert cipher.decrypt("runner.secret_access_key", first) == "same-secret"
    with pytest.raises(SettingDecryptionError, match="setting_decryption_failed"):
        cipher.decrypt("runner.ark_api_key", first)


@pytest.mark.parametrize(
    "ciphertext",
    [
        b"",
        b"\x02" + b"x" * 29,
        b"\x01" + b"x" * 28,
        b"\x01" + b"x" * 29,
    ],
)
def test_cipher_rejects_invalid_envelopes_with_stable_error(ciphertext):
    cipher = SettingCipher.from_secret("x" * 32)

    with pytest.raises(SettingDecryptionError, match="^setting_decryption_failed$"):
        cipher.decrypt("runner.ark_api_key", ciphertext)


def test_cipher_rejects_non_utf8_plaintext_with_stable_error():
    cipher = SettingCipher.from_secret("x" * 32)
    encrypted_invalid_utf8 = cipher._aes.encrypt(  # noqa: SLF001
        b"x" * 12,
        b"\xff",
        b"runner.ark_api_key",
    )
    ciphertext = b"\x01" + b"x" * 12 + encrypted_invalid_utf8

    with pytest.raises(SettingDecryptionError, match="^setting_decryption_failed$"):
        cipher.decrypt("runner.ark_api_key", ciphertext)


def test_repository_encrypts_batch_and_reads_it_after_recreation(settings):
    engine, session_factory = create_engine_and_session(settings)
    Base.metadata.create_all(engine)
    cipher = SettingCipher.from_secret(settings.app_secret_key)

    with session_factory() as db:
        repository = SettingRepository(db, cipher)
        updated_at = repository.set_many(
            {
                "runner.ark_api_key": "ark-secret",
                "runner.secret_access_key": "access-secret",
            }
        )
        db.commit()

        rows = db.scalars(select(Setting).order_by(Setting.key)).all()
        assert len(rows) == 2
        assert all(row.updated_at == updated_at for row in rows)
        assert updated_at.tzinfo == UTC
        assert b"ark-secret" not in rows[0].encrypted_value
        assert b"access-secret" not in rows[1].encrypted_value

        recreated = SettingRepository(db, SettingCipher.from_secret(settings.app_secret_key))
        assert recreated.get("runner.ark_api_key") == "ark-secret"
        assert recreated.get("runner.secret_access_key") == "access-secret"
        assert recreated.get("runner.missing") is None

    engine.dispose()


def test_repository_reencrypts_value_on_repeated_save(settings):
    engine, session_factory = create_engine_and_session(settings)
    Base.metadata.create_all(engine)

    with session_factory() as db:
        repository = SettingRepository(
            db,
            SettingCipher.from_secret(settings.app_secret_key),
        )
        repository.set_many({"runner.ark_api_key": "same-secret"})
        db.commit()
        first = db.get(Setting, "runner.ark_api_key").encrypted_value

        repository.set_many({"runner.ark_api_key": "same-secret"})
        db.commit()
        second = db.get(Setting, "runner.ark_api_key").encrypted_value

        assert first != second

    engine.dispose()


def test_repository_treats_tampered_ciphertext_as_unconfigured(settings):
    engine, session_factory = create_engine_and_session(settings)
    Base.metadata.create_all(engine)

    with session_factory() as db:
        repository = SettingRepository(
            db,
            SettingCipher.from_secret(settings.app_secret_key),
        )
        repository.set_many({"runner.ark_api_key": "ark-secret"})
        db.commit()

        row = db.get(Setting, "runner.ark_api_key")
        row.encrypted_value = row.encrypted_value[:-1] + bytes([row.encrypted_value[-1] ^ 1])
        db.commit()

        assert repository.get("runner.ark_api_key") is None

    engine.dispose()


def test_repository_batch_is_invisible_after_flush_failure_and_rollback(settings, monkeypatch):
    engine, session_factory = create_engine_and_session(settings)
    Base.metadata.create_all(engine)

    with session_factory() as db:
        repository = SettingRepository(
            db,
            SettingCipher.from_secret(settings.app_secret_key),
        )

        def fail_flush():
            raise RuntimeError("simulated_flush_failure")

        monkeypatch.setattr(db, "flush", fail_flush)
        with pytest.raises(RuntimeError, match="simulated_flush_failure"):
            repository.set_many(
                {
                    "runner.ark_api_key": "ark-secret",
                    "runner.secret_access_key": "access-secret",
                }
            )
        db.rollback()

    with session_factory() as db:
        assert db.scalars(select(Setting)).all() == []

    engine.dispose()


def test_repository_uses_fallback_until_value_is_saved(settings):
    engine, session_factory = create_engine_and_session(settings)
    Base.metadata.create_all(engine)

    with session_factory() as db:
        repository = SettingRepository(
            db,
            SettingCipher.from_secret(settings.app_secret_key),
            {"runner.mobile_use.product_id": "env_product"},
        )

        assert repository.get("runner.mobile_use.product_id") == "env_product"

        repository.set_many({"runner.mobile_use.product_id": "db_product"})
        db.commit()

        assert repository.get("runner.mobile_use.product_id") == "db_product"

    engine.dispose()


def test_settings_service_uses_runner_defaults_from_environment(settings):
    engine, session_factory = create_engine_and_session(settings)
    Base.metadata.create_all(engine)

    with session_factory() as db:
        service = SettingsService(
            SettingRepository(
                db,
                SettingCipher.from_secret(settings.app_secret_key),
                {
                    "runner.mode": "mobile_use",
                    "runner.mobile_use.access_key_id": "AKLTENV000000WXYZ",
                    "runner.mobile_use.secret_access_key": "env-secret",
                    "runner.mobile_use.product_id": "env-product",
                    "runner.mobile_use.tos_bucket": "env-bucket",
                    "runner.mobile_use.tos_endpoint": "tos-s3-cn-beijing.volces.com",
                    "runner.mobile_use.tos_region": "cn-beijing",
                    "runner.mobile_use.use_base64_screenshot": "false",
                    "runner.mobile_use.max_step": "200",
                    "runner.mobile_use.timeout_seconds": "300",
                    "runner.mobile_use.callback_info": '{"url":"https://callback.example.com"}',
                    "runner.mobile_use.output_schema": '{"type":"object"}',
                    "runner.mobile_use.retry_limit": "5",
                    "runner.mobile_use.system_prompt": "env system prompt",
                    "runner.mobile_use.screen_record": "true",
                    "runner.mobile_use.mcp_json": '{"mcpServers":{"x":{"url":"https://mcp.example.com"}}}',
                    "runner.mobile_use.max_output_tokens": "1024",
                    "runner.mobile_use.gps_info": "116.397128,39.916527,50,0,0,10",
                },
            )
        )

        config = service.get_runner_config()

    assert config.mode == "mobile_use"
    assert config.access_key_id == "AKLTENV000000WXYZ"
    assert config.secret_access_key == "env-secret"
    assert config.product_id == "env-product"
    assert config.tos_bucket == "env-bucket"
    assert config.tos_endpoint == "tos-s3-cn-beijing.volces.com"
    assert config.tos_region == "cn-beijing"
    assert config.use_base64_screenshot is False
    assert config.max_step == 200
    assert config.timeout_seconds == 300
    assert config.callback_info == {"url": "https://callback.example.com"}
    assert config.output_schema == '{"type":"object"}'
    assert config.retry_limit == 5
    assert config.system_prompt == "env system prompt"
    assert config.screen_record is True
    assert config.mcp_json == '{"mcpServers":{"x":{"url":"https://mcp.example.com"}}}'
    assert config.max_output_tokens == 1024
    assert config.gps_info == "116.397128,39.916527,50,0,0,10"

    engine.dispose()


def test_repository_rejects_empty_value_before_writing_batch(settings):
    engine, session_factory = create_engine_and_session(settings)
    Base.metadata.create_all(engine)

    with session_factory() as db:
        repository = SettingRepository(
            db,
            SettingCipher.from_secret(settings.app_secret_key),
        )

        with pytest.raises(ValueError, match="^setting_value_must_not_be_empty$"):
            repository.set_many(
                {
                    "runner.ark_api_key": "ark-secret",
                    "runner.secret_access_key": "",
                }
            )
        db.commit()

    with session_factory() as db:
        assert db.scalars(select(Setting)).all() == []

    engine.dispose()
