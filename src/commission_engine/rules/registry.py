"""Client registry: clients.yaml -> per-client config and commission rule.

Adding a client is a clients.yaml entry and, at most, one new rule class
registered in RULE_TYPES. The engine, loader, and report code never change
per client — that is the product thesis, protect it.
"""

import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict

from .base import CommissionRule
from .flat import FlatRate
from .tiered import Tier, Tiered


def default_clients_file() -> Path:
    """clients.yaml location: repo root in a source checkout; inside the
    bundle when frozen by PyInstaller, unless an editable copy sits next to
    the executable (the sidecar wins so config stays changeable post-build)."""
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        sidecar = exe_dir / "clients.yaml"
        if sidecar.exists():
            return sidecar
        return Path(getattr(sys, "_MEIPASS", exe_dir)) / "clients.yaml"
    return Path(__file__).resolve().parents[3] / "clients.yaml"


class OrgConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    prepared_for: str | None = None
    prepared_by: str | None = None


class RuleSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: str
    params: dict[str, Any]


class ClientConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    client_id: str
    display_name: str
    rule: RuleSpec
    source_type: str = "csv"
    target_low: Decimal | None = None
    target_high: Decimal | None = None
    presented_method: str | None = None
    presented_rationale: str | None = None


def _build_flat(params: dict[str, Any]) -> FlatRate:
    return FlatRate(Decimal(str(params["rate"])))


def _build_tiered(params: dict[str, Any]) -> Tiered:
    tiers = [
        Tier(
            up_to=None if t.get("up_to") is None else Decimal(str(t["up_to"])),
            rate=Decimal(str(t["rate"])),
        )
        for t in params["tiers"]
    ]
    return Tiered(tiers)


RULE_TYPES = {
    "flat": _build_flat,
    "tiered": _build_tiered,
}


def build_rule(spec: RuleSpec) -> CommissionRule:
    try:
        factory = RULE_TYPES[spec.type]
    except KeyError:
        raise ValueError(
            f"unknown rule type {spec.type!r}; known types: {sorted(RULE_TYPES)}"
        ) from None
    return factory(spec.params)


def load_organization(path: str | Path | None = None) -> OrgConfig:
    """The organization block: who the reports are prepared for and by."""
    path = Path(path) if path else default_clients_file()
    raw = yaml.safe_load(path.read_text())
    org = raw.get("organization") or {}
    return OrgConfig(
        prepared_for=org.get("prepared_for"),
        prepared_by=org.get("prepared_by"),
    )


def load_clients(path: str | Path | None = None) -> dict[str, ClientConfig]:
    path = Path(path) if path else default_clients_file()
    raw = yaml.safe_load(path.read_text())
    clients: dict[str, ClientConfig] = {}
    for client_id, cfg in raw["clients"].items():
        rule_raw = dict(cfg["rule"])
        rule_type = rule_raw.pop("type")
        target = cfg.get("target_range") or {}
        if (target.get("low") is None) != (target.get("high") is None):
            raise ValueError(
                f"client {client_id!r}: target_range needs both low and high (or neither)"
            )
        clients[client_id] = ClientConfig(
            client_id=client_id,
            display_name=cfg.get("display_name", client_id),
            rule=RuleSpec(type=rule_type, params=rule_raw),
            source_type=(cfg.get("source") or {}).get("type", "csv"),
            target_low=None if target.get("low") is None else Decimal(str(target["low"])),
            target_high=None if target.get("high") is None else Decimal(str(target["high"])),
            presented_method=cfg.get("presented_method"),
            presented_rationale=cfg.get("presented_rationale"),
        )
    return clients


def get_client(client_id: str, path: str | Path | None = None) -> ClientConfig:
    clients = load_clients(path)
    try:
        return clients[client_id]
    except KeyError:
        raise ValueError(
            f"unknown client {client_id!r}; configured clients: {sorted(clients)}"
        ) from None
