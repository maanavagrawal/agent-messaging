from __future__ import annotations

import subprocess

from fixlog.web.install_script import build_collector_install_script


def test_collector_install_script_contains_expected_flow() -> None:
    script = build_collector_install_script(
        base_url="https://fixlog.example.test/",
        package_url="git+https://github.com/example/fixlog.git@main",
    )

    assert "DEFAULT_FIXLOG_BASE_URL=https://fixlog.example.test" in script
    assert (
        "DEFAULT_FIXLOG_PACKAGE_URL=git+https://github.com/example/fixlog.git@main"
        in script
    )
    assert "python3 -m venv" in script
    assert "pip install --upgrade \"$FIXLOG_PACKAGE_URL\"" in script
    assert "\"$FIXLOG_BIN_DIR/fixlog\" connect" in script
    assert "--project \"$PROJECT\"" in script
    assert "--token flxdt_..." in script
    assert "--background" in script
    assert "\"$FIXLOG_BIN_DIR/fixlog\" service install --start" in script


def test_collector_install_script_is_valid_bash() -> None:
    script = build_collector_install_script(
        base_url="https://fixlog.example.test",
        package_url="git+https://github.com/example/fixlog.git@main",
    )

    result = subprocess.run(
        ["bash", "-n"],
        input=script,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
