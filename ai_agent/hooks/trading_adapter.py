"""Trading adapter that bridges the AI driver and the on-chain bot."""

from __future__ import annotations

from importlib import import_module
from typing import Any, Callable, Dict, Iterable, List, Optional

__all__ = ["build_trading_adapter"]


class TradingAdapterError(RuntimeError):
    """Raised when the adapter cannot attach to the trading bot."""


CANDIDATE_BOTS: List[Dict[str, Any]] = [
    {"module": "Zcore_mgr", "classes": ["ArbitrageBot", "AggregatorBot"]},
    {"module": "Zscan_mgr", "classes": ["ArbitrageBot", "AggregatorBot"]},
    {"module": "polygon_arb_bot", "classes": ["PolygonArbBot"]},
]

SCAN_METHODS = [
    "scan_for_opportunities",
    "scan",
    "run_single_scan",
    "run_scan_cycle",
]

EXECUTE_METHODS = [
    "execute_opportunity",
    "execute_proposal",
    "execute",
    "run_trade",
]

AUTO_METHODS = [
    "run_auto_mode",
    "run_continuous",
    "auto_run",
    "auto",
]


def build_trading_adapter() -> Dict[str, Callable[..., Any]]:
    """Instantiate the user's trading bot and expose a simple call surface."""

    bot = _instantiate_bot()
    scan_fn = _resolve_callable(bot, SCAN_METHODS)
    execute_fn = _resolve_callable(bot, EXECUTE_METHODS)
    auto_fn = _resolve_callable(bot, AUTO_METHODS)

    # Fall back to auto executor helpers when direct methods are missing
    if execute_fn is None and hasattr(bot, "auto_executor"):
        auto_exec = getattr(bot, "auto_executor")
        execute_fn = _resolve_callable(auto_exec, ["execute_opportunity"])

    if scan_fn is None or execute_fn is None or auto_fn is None:
        missing = [
            name
            for name, fn in [
                ("scan", scan_fn),
                ("execute", execute_fn),
                ("auto", auto_fn),
            ]
            if fn is None
        ]
        raise TradingAdapterError(
            f"Trading bot missing required callables: {', '.join(missing)}"
        )

    return {
        "scan": scan_fn,
        "execute": execute_fn,
        "auto": auto_fn,
    }


def _instantiate_bot() -> Any:
    errors: List[str] = []
    for candidate in CANDIDATE_BOTS:
        module_name = candidate["module"]
        try:
            module = import_module(module_name)
        except ImportError as exc:
            errors.append(f"{module_name}: {exc}")
            continue
        for class_name in candidate["classes"]:
            bot_cls = getattr(module, class_name, None)
            if bot_cls is None:
                continue
            try:
                return _construct_bot(bot_cls)
            except Exception as exc:  # pragma: no cover - defensive
                errors.append(f"{module_name}.{class_name}: {exc}")
                continue
    tried = ", ".join(entry["module"] for entry in CANDIDATE_BOTS)
    raise TradingAdapterError(
        f"Could not instantiate trading bot. Tried modules: {tried}. Errors: {errors}"
    )


def _construct_bot(bot_cls: Any) -> Any:
    try:
        return bot_cls()
    except TypeError:
        # Retry with sensible defaults used within this repo
        return bot_cls(auto_execute=True)


def _resolve_callable(obj: Any, names: Iterable[str]) -> Optional[Callable[..., Any]]:
    for name in names:
        candidate = getattr(obj, name, None)
        if callable(candidate):
            return candidate
    return None
