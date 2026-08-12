import pytest

from cua_platform.settings.schemas import RunnerConfig, RunnerExecutionSettingsError


def test_cua_execution_snapshot_requires_account_not_product_or_tos():
    config = RunnerConfig(
        mode="mobile_use",
        access_key_id="AKLT00000000WXYZ",
        secret_access_key="secret-value",
        account_id="2103274899",
    )

    snapshot = config.execution_snapshot()

    assert snapshot["account_id"] == "2103274899"
    assert "product_id" not in snapshot
    assert "tos_bucket" not in snapshot
    assert "tos_region" not in snapshot


def test_cua_execution_snapshot_reports_missing_account_id():
    config = RunnerConfig(
        mode="mobile_use",
        access_key_id="AKLT00000000WXYZ",
        secret_access_key="secret-value",
    )

    with pytest.raises(RunnerExecutionSettingsError) as exc_info:
        config.execution_snapshot()

    assert exc_info.value.missing_fields == ["account_id"]
