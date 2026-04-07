import os

from referral_assistant.launcher import (
    build_cli_command,
    build_dashboard_command,
    build_pythonpath_env,
    subprocess_windowless_kwargs,
)


def test_build_dashboard_command_contains_host_and_port() -> None:
    command = build_dashboard_command("0.0.0.0", 9000)

    assert command[-4:] == ["--host", "0.0.0.0", "--port", "9000"]


def test_build_cli_command_targets_module_command() -> None:
    command = build_cli_command("run-once")

    assert command[-2:] == ["referral_assistant.cli", "run-once"]


def test_build_pythonpath_env_includes_src_path() -> None:
    env = build_pythonpath_env()

    assert "PYTHONPATH" in env
    assert "KalshiShare\\src" in env["PYTHONPATH"]


def test_subprocess_windowless_kwargs_matches_platform() -> None:
    kwargs = subprocess_windowless_kwargs()

    if os.name == "nt":
        assert "startupinfo" in kwargs or "creationflags" in kwargs
    else:
        assert kwargs == {}
