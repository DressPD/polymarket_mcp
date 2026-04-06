from __future__ import annotations

import polymarket_mcp.main as main_mod


def test_main_runs_bot_and_always_closes(monkeypatch) -> None:
    calls = {"run": 0, "close": 0}

    class _Bot:
        def __init__(self, _settings):
            pass

        def run_forever(self):
            calls["run"] += 1
            raise RuntimeError("stop loop")

        def close(self):
            calls["close"] += 1

    monkeypatch.setattr(main_mod, "load_settings", lambda: object())
    monkeypatch.setattr(main_mod, "PolymarketBot", _Bot)

    try:
        main_mod.main()
    except RuntimeError as exc:
        assert str(exc) == "stop loop"

    assert calls["run"] == 1
    assert calls["close"] == 1
