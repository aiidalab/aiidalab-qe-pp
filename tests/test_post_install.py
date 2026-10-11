from click.testing import CliRunner

from aiidalab_qe_pp import __main__ as plugin_cli


def test_verify_post_install_passes(monkeypatch, tmp_path):
    critic_executable = tmp_path / "critic2"
    critic_executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    critic_executable.chmod(0o755)

    monkeypatch.setattr(plugin_cli, "load_profile", lambda _profile: None)
    monkeypatch.setattr(plugin_cli, "load_code", lambda _label: object())
    monkeypatch.setattr(plugin_cli.shutil, "which", lambda _name: "/usr/bin/tool")
    monkeypatch.setattr(plugin_cli, "critic_executable", critic_executable)

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
