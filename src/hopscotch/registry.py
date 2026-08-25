"""Agent Registry: publish, discover, authorize.

FALLBACK IMPLEMENTATION, stated plainly. Google's managed Agent Registry is part
of the Gemini Enterprise Agent Platform and requires organisation-level setup a
personal Cloud account does not have -- probed and confirmed unavailable on this
project. This is the substitute promised in deploy/probe.sh: a Firestore-backed
registry enforcing exactly the scopes declared in registry/*.agent.yaml, with
the same three responsibilities.

  publish()    versioned agent cards, so a capability has an owner and a history
  discover()   the entry point -- another department FINDS an agent here
  authorize()  the gateway check: may this identity use this scope?

Discovery is deliberately a first-class operation rather than a listing page.
An agent nobody can find is not shared infrastructure; it is a private script
with extra ceremony.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .config import settings
from .telemetry import span

COLLECTION = "agent_registry"
CARDS_DIR = Path(__file__).resolve().parents[2] / "registry"


class ScopeDenied(PermissionError):
    """The gateway refused. Carries why, because a silent denial is unfixable."""


@dataclass(frozen=True)
class AgentCard:
    name: str
    version: str
    department: str
    model: str
    spiffe_id: str
    scopes: frozenset[str]
    deny_by_default: bool
    armor_template: str

    @classmethod
    def from_yaml(cls, path: Path) -> "AgentCard":
        doc = yaml.safe_load(path.read_text())
        meta, spec = doc["metadata"], doc["spec"]
        return cls(
            name=meta["name"],
            version=str(meta["version"]),
            department=meta.get("owner_department", "unknown"),
            model=spec.get("model", ""),
            spiffe_id=spec.get("identity", {}).get("spiffe_id", ""),
            scopes=frozenset(spec.get("scopes") or []),
            deny_by_default=bool(spec.get("gateway", {}).get("deny_by_default", True)),
            armor_template=spec.get("guardrails", {}).get("model_armor_template", ""),
        )

    def to_doc(self) -> dict:
        return {
            "name": self.name, "version": self.version,
            "department": self.department, "model": self.model,
            "spiffe_id": self.spiffe_id, "scopes": sorted(self.scopes),
            "deny_by_default": self.deny_by_default,
            "armor_template": self.armor_template,
            "published_at": datetime.now(timezone.utc).isoformat(),
        }


def load_cards(directory: Path | None = None) -> list[AgentCard]:
    d = directory or CARDS_DIR
    return [AgentCard.from_yaml(p) for p in sorted(d.glob("*.agent.yaml"))]


def _client():
    from google.cloud import firestore

    from .store import client_kwargs
    return firestore.Client(**client_kwargs())


def publish(card: AgentCard) -> str:
    """Publish one version. The document id is name@version, so a bump is a new
    row rather than an overwrite -- you can see what an agent used to be able
    to do."""
    doc_id = f"{card.name}@{card.version}"
    with span("registry.publish", agent=card.name, version=card.version):
        _client().collection(COLLECTION).document(doc_id).set(card.to_doc())
    return doc_id


def discover(*, department: str | None = None, scope: str | None = None) -> list[dict]:
    """Find agents. This is the user action, not a side effect of deployment."""
    with span("registry.discover", department=department or "", scope=scope or "") as s:
        rows = [d.to_dict() for d in _client().collection(COLLECTION).stream()]
        if department:
            rows = [r for r in rows if r.get("department") == department]
        if scope:
            rows = [r for r in rows if scope in (r.get("scopes") or [])]
        s.set_attribute("hits", len(rows))
        return sorted(rows, key=lambda r: (r.get("name", ""), r.get("version", "")))


def authorize(cards: list[AgentCard], agent_name: str, scope: str) -> None:
    """Gateway check. Raises ScopeDenied with a reason, never returns False.

    Deny by default: an agent absent from the registry has no scopes at all,
    rather than inheriting a permissive default. That is the whole point of
    publishing.
    """
    by_name = {c.name: c for c in cards}
    card = by_name.get(agent_name)
    with span("gateway.authorize", agent=agent_name, scope=scope) as s:
        if card is None:
            s.set_attribute("decision", "deny_unregistered")
            raise ScopeDenied(
                f"{agent_name} is not published to the registry; "
                "unregistered agents hold no scopes")
        if scope not in card.scopes:
            s.set_attribute("decision", "deny_scope")
            raise ScopeDenied(
                f"{agent_name} ({card.department}) may not '{scope}'. "
                f"Declared scopes: {', '.join(sorted(card.scopes))}")
        s.set_attribute("decision", "allow")
