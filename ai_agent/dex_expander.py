"""DEX expansion planner that evaluates unused venues and proposes additions."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from registries import DEXES, TOKENS

POOL_REGISTRY_DEFAULT = os.path.join(os.getcwd(), "pool_registry.json")


@dataclass
class DexStatus:
    """Represents validation information for a single DEX."""

    name: str
    has_pools: bool
    pool_count: int
    missing_tokens: List[str]
    required_fields: List[str]
    ready_for_pricing: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dex": self.name,
            "has_pools": self.has_pools,
            "pool_count": self.pool_count,
            "missing_tokens": self.missing_tokens,
            "required_fields": self.required_fields,
            "ready_for_pricing": self.ready_for_pricing,
        }


class DexExpansionPlanner:
    """Analyzes registry coverage and suggests the next DEX to integrate."""

    def __init__(self, pool_registry_path: str = POOL_REGISTRY_DEFAULT) -> None:
        self.pool_registry_path = pool_registry_path
        self.registry = self._load_registry()

    def _load_registry(self) -> Dict[str, Any]:
        try:
            with open(self.pool_registry_path, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, json.JSONDecodeError):
            return {}

    def evaluate(self) -> List[DexStatus]:
        statuses: List[DexStatus] = []
        for dex_name, dex_info in DEXES.items():
            pools = self.registry.get(dex_name, {})
            missing_tokens = self._missing_tokens(pools)
            required_fields = self._missing_fields(dex_info)
            ready = not required_fields and not missing_tokens
            statuses.append(
                DexStatus(
                    name=dex_name,
                    has_pools=bool(pools),
                    pool_count=len(pools),
                    missing_tokens=missing_tokens,
                    required_fields=required_fields,
                    ready_for_pricing=ready,
                )
            )
        return statuses

    def recommend_new_dexes(self, limit: int = 1) -> List[Dict[str, Any]]:
        """Return code suggestions for DEXes that are defined but not yet used."""

        statuses = self.evaluate()
        candidates = [status for status in statuses if not status.has_pools and status.ready_for_pricing]
        recommendations: List[Dict[str, Any]] = []
        for status in candidates[:limit]:
            template = self._build_template(status.name)
            validation = self._build_validation_steps(status.name)
            recommendations.append(
                {
                    "dex": status.name,
                    "code_template": template,
                    "validation_steps": validation,
                }
            )
        return recommendations

    def _missing_tokens(self, pools: Dict[str, Any]) -> List[str]:
        missing: List[str] = []
        for pool in pools.values():
            for token_key in ("token0", "token1"):
                token_address = pool.get(token_key)
                if not token_address:
                    continue
                if not self._token_known(token_address):
                    missing.append(token_address)
        return missing

    @staticmethod
    def _token_known(address: str) -> bool:
        lowered = address.lower()
        for info in TOKENS.values():
            if info["address"].lower() == lowered:
                return True
        return False

    def _missing_fields(self, dex_info: Dict[str, Any]) -> List[str]:
        required: List[str] = []
        dex_type = dex_info.get("type")
        if dex_type in {"v2", "v3", "v3_algebra", "dodo", "kyber_dmm"}:
            if not dex_info.get("router"):
                required.append("router")
        if dex_type in {"v3", "v3_algebra"} and not dex_info.get("quoter"):
            required.append("quoter")
        if dex_type == "curve" and not dex_info.get("pool"):
            required.append("pool")
        if dex_type == "balancer" and not dex_info.get("vault"):
            required.append("vault")
        return required

    def _build_template(self, dex_name: str) -> str:
        dex_info = DEXES[dex_name]
        sample_pair = self._suggest_pair()
        return (
            f"# Add to pool_registry.json under \"{dex_name}\"\n"
            f"\"{sample_pair['label']}\": {{\n"
            f"  \"pool\": \"<POOL_ADDRESS>\",\n"
            f"  \"token0\": \"{sample_pair['token0']}\",\n"
            f"  \"token1\": \"{sample_pair['token1']}\",\n"
            f"  \"type\": \"{dex_info.get('type', 'v2')}\"\n"
            "}\n"
        )

    def _suggest_pair(self) -> Dict[str, str]:
        stable = TOKENS.get("USDC") or next(iter(TOKENS.values()))
        quote = TOKENS.get("WETH") or TOKENS.get("WPOL") or next(iter(TOKENS.values()))
        return {
            "label": f"{stable['symbol']}/{quote['symbol']}",
            "token0": stable["address"],
            "token1": quote["address"],
        }

    def _build_validation_steps(self, dex_name: str) -> List[str]:
        dex_info = DEXES[dex_name]
        router = dex_info.get("router") or dex_info.get("vault") or dex_info.get("pool")
        steps = [
            f"1. Confirm connectivity to {dex_name} (router/pool: {router}).",
            "2. Add at least one high-liquidity pair to pool_registry.json using the template above.",
            "3. Run PriceDataFetcher.fetch_all_pools() to ensure quotes and derived prices succeed.",
            "4. Only after prices and TVL validate, enable the DEX inside trading or arbitrage finder modules.",
        ]
        return steps


__all__ = ["DexExpansionPlanner", "DexStatus"]
