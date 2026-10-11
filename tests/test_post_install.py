from types import SimpleNamespace

from click.testing import CliRunner

from aiidalab_qe_pp import __main__ as plugin_cli


def test_verify_post_install_passes(monkeypatch, tmp_path):
    python_executable = tmp_path / "python3"
    python_executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    python_executable.chmod(0o755)
    critic_executable = tmp_path / "critic2"
    critic_executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    critic_executable.chmod(0o755)

    monkeypatch.setattr(plugin_cli, "load_profile", lambda _profile: None)
    codes = {
        "python3@localhost": SimpleNamespace(
            filepath_executable=str(python_executable)
        ),
        "critic2@localhost": SimpleNamespace(
            filepath_executable=str(critic_executable)
        ),
    }
    monkeypatch.setattr(plugin_cli, "load_code", codes.__getitem__)

    result = CliRunner().invoke(plugin_cli.cli, ["verify-post-install"])

    assert result.exit_code == 0, result.output
    assert "setup is valid" in result.output


def test_verify_post_install_reports_missing_code(monkeypatch, tmp_path):
    from aiida.common.exceptions import NotExistent

    monkeypatch.setattr(plugin_cli, "load_profile", lambda _profile: None)
    monkeypatch.setattr(
        plugin_cli,
        "load_code",
        lambda label: (_ for _ in ()).throw(NotExistent(label)),
    )
    monkeypatch.setattr(plugin_cli.shutil, "which", lambda _name: "/usr/bin/tool")
    monkeypatch.setattr(plugin_cli, "critic_executable", tmp_path / "missing")

    result = CliRunner().invoke(plugin_cli.cli, ["verify-post-install"])

    assert result.exit_code != 0
    assert "critic2@localhost is not configured" in result.output


def test_verify_post_install_reports_non_executable_code_path(monkeypatch, tmp_path):
    python_executable = tmp_path / "python3"
    python_executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    python_executable.chmod(0o755)
    critic_executable = tmp_path / "critic2"
    critic_executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    critic_executable.chmod(0o644)
    codes = {
        "python3@localhost": SimpleNamespace(
            filepath_executable=str(python_executable)
        ),
        "critic2@localhost": SimpleNamespace(
            filepath_executable=str(critic_executable)
        ),
    }
    monkeypatch.setattr(plugin_cli, "load_profile", lambda _profile: None)
    monkeypatch.setattr(plugin_cli, "load_code", codes.__getitem__)

    result = CliRunner().invoke(plugin_cli.cli, ["verify-post-install"])

    assert result.exit_code != 0
    assert "critic2@localhost executable is missing" in result.output
