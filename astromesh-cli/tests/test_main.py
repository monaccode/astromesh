"""Tests for the CLI main entry point."""

from astromesh_cli.main import app


def test_app_name():
    assert app.info.name == "astromeshctl"


def test_app_has_commands():
    """Check that key commands are registered."""
    command_names = [cmd.name for cmd in app.registered_commands]
    callback_names = [
        cmd.callback.__name__ for cmd in app.registered_commands if cmd.callback
    ]
    group_names = [g.name for g in app.registered_groups]

    # Typer groups (sub-apps)
    assert "status" in group_names
    assert "agents" in group_names
    assert "providers" in group_names
    assert "traces" in group_names
    assert "tools" in group_names

    # Direct commands
    assert "run" in command_names
    assert "dev" in command_names
    assert "ask" in command_names
    assert "metrics" in command_names

    # version is registered via @app.command() decorator — name defaults to None
    # but its callback function is named "version"
    assert "version" in callback_names


def test_app_has_no_args_is_help():
    """App should show help when called with no arguments."""
    assert app.info.no_args_is_help is True
