from __future__ import annotations

from polymarket_mcp.bot import PolymarketBot
from polymarket_mcp.models import ExecutedAction

from ._helpers import make_settings


def test_run_cycle_success_with_isolated_dependencies(monkeypatch) -> None:
    bot = PolymarketBot(make_settings())

    monkeypatch.setattr(bot.sources, "fetch_all", lambda: [object(), object()])
    monkeypatch.setattr(bot.markets, "list_candidate_markets", lambda _k: [object()])
    monkeypatch.setattr(bot.strategy, "decide", lambda _payload: [object()])
    monkeypatch.setattr(
        bot.execution,
        "execute",
        lambda _decisions: [ExecutedAction(status="dry_run_order", details={"market_id": "m1"})],
    )

    result = bot.run_cycle()

    assert result["signal_count"] == 2
    assert result["market_count"] == 1
    assert result["decision_count"] == 1
    assert result["action_count"] == 1
    assert result["errors"] == []


def test_run_cycle_collects_stage_errors_and_continues(monkeypatch) -> None:
    bot = PolymarketBot(make_settings())

    def _signals_fail():
        raise RuntimeError("signals down")

    def _strategy_fail(_payload):
        raise RuntimeError("strategy down")

    monkeypatch.setattr(bot.sources, "fetch_all", _signals_fail)
    monkeypatch.setattr(bot.markets, "list_candidate_markets", lambda _k: [object()])
    monkeypatch.setattr(bot.strategy, "decide", _strategy_fail)
    monkeypatch.setattr(bot.execution, "execute", lambda _decisions: [])

    result = bot.run_cycle()

    assert result["signal_count"] == 0
    assert result["market_count"] == 1
    assert result["decision_count"] == 0
    assert result["action_count"] == 0
    errors = result["errors"]
    assert isinstance(errors, list)
    assert any(str(err).startswith("signal_fetch_error:") for err in errors)
    assert any(str(err).startswith("strategy_error:") for err in errors)


def test_run_cycle_http_error_paths_and_execution_error(monkeypatch) -> None:
    import httpx

    bot = PolymarketBot(make_settings())

    def _sig_http():
        raise httpx.HTTPError("signals http")

    def _mkt_http(_k):
        raise httpx.HTTPError("markets http")

    def _exec_fail(_d):
        raise RuntimeError("exec crash")

    monkeypatch.setattr(bot.sources, "fetch_all", _sig_http)
    monkeypatch.setattr(bot.markets, "list_candidate_markets", _mkt_http)
    monkeypatch.setattr(bot.strategy, "decide", lambda _payload: [object()])
    monkeypatch.setattr(bot.execution, "execute", _exec_fail)

    result = bot.run_cycle()

    errors = result["errors"]
    assert isinstance(errors, list)
    assert any(str(err).startswith("signal_fetch_http_error:") for err in errors)
    assert any(str(err).startswith("market_fetch_http_error:") for err in errors)
    assert any(str(err).startswith("execution_error:") for err in errors)


def test_close_calls_underlying_clients() -> None:
    bot = PolymarketBot(make_settings())
    calls = {"s": 0, "m": 0}
    bot.sources.close = lambda: calls.__setitem__("s", calls["s"] + 1)
    bot.markets.close = lambda: calls.__setitem__("m", calls["m"] + 1)

    bot.close()

    assert calls["s"] == 1
    assert calls["m"] == 1


def test_run_forever_catches_cycle_exceptions(monkeypatch) -> None:
    bot = PolymarketBot(make_settings(poll_interval_seconds=1))
    calls = {"sleep": 0}
    printed: list[str] = []

    def _boom_cycle():
        raise RuntimeError("cycle exploded")

    def _sleep(_seconds: int) -> None:
        calls["sleep"] += 1
        raise KeyboardInterrupt

    monkeypatch.setattr(bot, "run_cycle", _boom_cycle)
    monkeypatch.setattr("polymarket_mcp.bot.time.sleep", _sleep)
    monkeypatch.setattr("builtins.print", lambda payload: printed.append(str(payload)))

    try:
        bot.run_forever()
    except KeyboardInterrupt:
        pass

    assert calls["sleep"] == 1
    assert len(printed) == 1
    assert "cycle_error:cycle exploded" in printed[0]
