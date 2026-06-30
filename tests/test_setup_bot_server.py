from pathlib import Path


def test_systemd_setup_restarts_strategy_bot_after_dependency_updates():
    script = Path("setup_bot_server.sh").read_text()

    assert "\n    sudo systemctl restart binance-strategy-bot.service" in script
    assert "\n    sudo systemctl start binance-strategy-bot.service" not in script


def test_python_dependency_setup_supports_noninteractive_uv_install_path():
    script = Path("setup_bot_server.sh").read_text()

    assert 'UV_BIN="$HOME/.local/bin/uv"' in script
    assert 'if [ ! -d ".venv" ]; then' in script
    assert '"$UV_BIN" venv' in script
    assert '"$UV_BIN" python install' in script
    assert '"$UV_BIN" pip install -e .' in script
