"""Tests for TerraformRunner — mocked subprocess calls."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from astromesh_orbit.terraform.runner import TerraformRunner, TerraformNotFoundError


@pytest.fixture
def runner():
    return TerraformRunner()


async def test_check_installed_success(runner: TerraformRunner):
    with patch.object(runner, "_run", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = (0, json.dumps({"terraform_version": "1.9.0"}), "")
        version = await runner.check_installed()
        assert version == "1.9.0"


async def test_check_installed_not_found(runner: TerraformRunner):
    with patch.object(runner, "_run", new_callable=AsyncMock) as mock_run:
        mock_run.side_effect = FileNotFoundError
        with pytest.raises(TerraformNotFoundError):
            await runner.check_installed()


async def test_init_calls_terraform(runner: TerraformRunner, tmp_path: Path):
    with patch.object(runner, "_run", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = (0, "Terraform has been successfully initialized!", "")
        await runner.init(tmp_path)
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args[:2] == ["terraform", "init"]


async def test_plan_parses_output(runner: TerraformRunner, tmp_path: Path):
    plan_output = (
        "Plan: 8 to add, 0 to change, 0 to destroy.\n"
        "\n"
        "  + google_cloud_run_v2_service.runtime\n"
        "  + google_sql_database_instance.main\n"
    )
    with patch.object(runner, "_run", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = (0, plan_output, "")
        result = await runner.plan(tmp_path)
        assert "8 to add" in result.raw_output


async def test_apply_returns_outputs(runner: TerraformRunner, tmp_path: Path):
    apply_out = "Apply complete! Resources: 8 added, 0 changed, 0 destroyed."
    output_json = json.dumps({"runtime_url": {"value": "https://runtime.run.app"}})
    with patch.object(runner, "_run", new_callable=AsyncMock) as mock_run:
        mock_run.side_effect = [
            (0, apply_out, ""),  # apply
            (0, output_json, ""),  # output
        ]
        result = await runner.apply(tmp_path, auto_approve=True)
        assert result.success is True
        assert result.outputs["runtime_url"] == "https://runtime.run.app"


async def test_apply_failure(runner: TerraformRunner, tmp_path: Path):
    with patch.object(runner, "_run", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = (1, "", "Error: insufficient permissions")
        result = await runner.apply(tmp_path, auto_approve=True)
        assert result.success is False
        assert "insufficient permissions" in result.raw_output


async def test_destroy_calls_terraform(runner: TerraformRunner, tmp_path: Path):
    with patch.object(runner, "_run", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = (0, "Destroy complete! Resources: 8 destroyed.", "")
        await runner.destroy(tmp_path, auto_approve=True)
        args = mock_run.call_args[0][0]
        assert "destroy" in args


async def test_output_parses_json(runner: TerraformRunner, tmp_path: Path):
    output_json = json.dumps(
        {
            "runtime_url": {"value": "https://runtime.run.app"},
            "db_connection": {"value": "10.0.0.5:5432"},
        }
    )
    with patch.object(runner, "_run", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = (0, output_json, "")
        outputs = await runner.output(tmp_path)
        assert outputs["runtime_url"] == "https://runtime.run.app"
        assert outputs["db_connection"] == "10.0.0.5:5432"
