from pathlib import Path


def test_systemd_setup_restarts_strategy_bot_after_dependency_updates():
    script = Path("setup_bot_server.sh").read_text()

    assert "\n    sudo systemctl restart binance-strategy-bot.service" in script
    assert "\n    sudo systemctl start binance-strategy-bot.service" not in script
