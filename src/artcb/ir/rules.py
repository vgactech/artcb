"""IR v0.2 — Moteur de règles déclaratives (Smart Contracts PoL).

Un IRRule encode une condition D+H+P → action G dans un graphe IR.
L'évaluateur vérifie la condition contre un contexte et retourne
si la règle est déclenchée et quelle action exécuter.

Exemples d'usage :
  - "SI pol_score(wallet) > 0.9 ALORS reward_bonus = 0.5 ARTCB"
  - "SI bloc_count > 210000 ALORS halving actif"
  - "SI balance(alice) >= 100 ALORS transfer_autorisé"
  - "SI nft.owner == wallet ALORS accès_niveau_2 accordé"

Ce module est la spécification des règles.
L'exécution automatique est le rôle de l'agent IA ou d'un scheduler (IR v0.3).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


# ── Types de règles ─────────────────────────────────────────────────────────

class RuleStatus(StrEnum):
    PENDING  = "pending"    # règle créée, pas encore évaluée
    TRUE     = "true"       # condition remplie → action applicable
    FALSE    = "false"      # condition non remplie
    ERROR    = "error"      # erreur d'évaluation
    EXECUTED = "executed"   # action exécutée (IR v0.3+)


class ConditionOperator(StrEnum):
    GT  = ">"
    GTE = ">="
    LT  = "<"
    LTE = "<="
    EQ  = "=="
    NEQ = "!="
    IN  = "in"
    CONTAINS = "contains"


# ── Structures de données ────────────────────────────────────────────────────

@dataclass
class RuleCondition:
    """Une condition élémentaire : variable op valeur.

    Exemples :
        RuleCondition("pol_score", ">", 0.9)
        RuleCondition("balance_artcb", ">=", 100.0)
        RuleCondition("nft_owner", "==", "artcb1alice...")
    """
    variable: str                   # nom de la variable dans le contexte
    operator: ConditionOperator     # opérateur de comparaison
    value: Any                      # valeur cible

    def evaluate(self, context: dict[str, Any]) -> bool:
        """Évalue la condition contre un contexte dict."""
        actual = context.get(self.variable)
        if actual is None:
            return False
        try:
            match self.operator:
                case ConditionOperator.GT:       return float(actual) > float(self.value)
                case ConditionOperator.GTE:      return float(actual) >= float(self.value)
                case ConditionOperator.LT:       return float(actual) < float(self.value)
                case ConditionOperator.LTE:      return float(actual) <= float(self.value)
                case ConditionOperator.EQ:       return str(actual) == str(self.value)
                case ConditionOperator.NEQ:      return str(actual) != str(self.value)
                case ConditionOperator.IN:       return str(actual) in self.value
                case ConditionOperator.CONTAINS: return str(self.value) in str(actual)
                case _:                          return False
        except (TypeError, ValueError):
            return False

    def to_dict(self) -> dict:
        return {"variable": self.variable, "operator": str(self.operator), "value": self.value}

    @classmethod
    def from_dict(cls, d: dict) -> RuleCondition:
        return cls(d["variable"], ConditionOperator(d["operator"]), d["value"])


@dataclass
class RuleAction:
    """Une action à exécuter quand la condition est vraie.

    Exemples :
        RuleAction("reward_bonus", "set", 0.5)
        RuleAction("access_level", "set", 2)
        RuleAction("notify", "call", "telegram:alert")
    """
    target: str          # variable ou service cible
    action_type: str     # "set" | "call" | "transfer" | "mint_nft" | "log"
    value: Any           # valeur ou paramètre

    def to_dict(self) -> dict:
        return {"target": self.target, "action_type": self.action_type, "value": self.value}

    @classmethod
    def from_dict(cls, d: dict) -> RuleAction:
        return cls(d["target"], d["action_type"], d["value"])


@dataclass
class IRRule:
    """
    Règle IR v0.2 — smart contract déclaratif PoL.

    Correspond à la structure :
        H (hypothèse/condition) → [vérifié D (décision)] → G (goal/action)

    La règle est gravée dans un bloc ARTCB via /ai/memo avec memo_type="smart_rule".
    Son graph_id sert d'identifiant unique immuable.
    """
    rule_id: str                        # identifiant unique (graph_id du bloc)
    label: str                          # description humaine courte
    conditions: list[RuleCondition]     # toutes doivent être vraies (AND)
    actions: list[RuleAction]           # actions à exécuter si TRUE
    combinator: str = "AND"             # "AND" | "OR"
    author_wallet: str = ""             # wallet qui a créé la règle
    created_at: str = ""                # ISO timestamp
    block_index: int | None = None      # index du bloc où la règle est gravée
    status: RuleStatus = RuleStatus.PENDING
    metadata: dict[str, Any] = field(default_factory=dict)

    def evaluate(self, context: dict[str, Any]) -> RuleEvaluationResult:
        """
        Évalue toutes les conditions contre le contexte fourni.

        context = dictionnaire de variables mesurables :
            {
                "pol_score": 0.92,
                "balance_artcb": 150.0,
                "block_count": 521,
                "wallet_address": "artcb1...",
                "nft_owner": "artcb1...",
                ...
            }
        """
        results = []
        errors = []

        for cond in self.conditions:
            try:
                results.append(cond.evaluate(context))
            except Exception as e:
                errors.append(str(e))
                results.append(False)

        if errors:
            return RuleEvaluationResult(
                rule_id=self.rule_id,
                label=self.label,
                triggered=False,
                status=RuleStatus.ERROR,
                conditions_results=results,
                errors=errors,
                actions_applicable=[],
            )

        triggered = all(results) if self.combinator == "AND" else any(results)
        return RuleEvaluationResult(
            rule_id=self.rule_id,
            label=self.label,
            triggered=triggered,
            status=RuleStatus.TRUE if triggered else RuleStatus.FALSE,
            conditions_results=results,
            errors=[],
            actions_applicable=self.actions if triggered else [],
        )

    def to_pol_text(self) -> str:
        """Convertit la règle en texte naturel mémorisable via PoL."""
        conds = []
        for c in self.conditions:
            conds.append(f"{c.variable} {c.operator} {c.value}")
        cond_str = f" {self.combinator} ".join(conds)
        acts = []
        for a in self.actions:
            acts.append(f"{a.action_type}({a.target}, {a.value})")
        act_str = "; ".join(acts)
        return (
            f"RULE [{self.rule_id}] {self.label} | "
            f"CONDITION: {cond_str} | "
            f"ACTION: {act_str} | "
            f"AUTHOR: {self.author_wallet}"
        )

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "label": self.label,
            "conditions": [c.to_dict() for c in self.conditions],
            "actions": [a.to_dict() for a in self.actions],
            "combinator": self.combinator,
            "author_wallet": self.author_wallet,
            "created_at": self.created_at,
            "block_index": self.block_index,
            "status": str(self.status),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict) -> IRRule:
        return cls(
            rule_id=d["rule_id"],
            label=d["label"],
            conditions=[RuleCondition.from_dict(c) for c in d.get("conditions", [])],
            actions=[RuleAction.from_dict(a) for a in d.get("actions", [])],
            combinator=d.get("combinator", "AND"),
            author_wallet=d.get("author_wallet", ""),
            created_at=d.get("created_at", ""),
            block_index=d.get("block_index"),
            status=RuleStatus(d.get("status", "pending")),
            metadata=d.get("metadata", {}),
        )


@dataclass
class RuleEvaluationResult:
    """Résultat d'une évaluation de règle."""
    rule_id: str
    label: str
    triggered: bool
    status: RuleStatus
    conditions_results: list[bool]
    errors: list[str]
    actions_applicable: list[RuleAction]

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "label": self.label,
            "triggered": self.triggered,
            "status": str(self.status),
            "conditions_results": self.conditions_results,
            "errors": self.errors,
            "actions_applicable": [a.to_dict() for a in self.actions_applicable],
        }


# ── Parser de règle en langage naturel ──────────────────────────────────────

def parse_rule_from_text(text: str, rule_id: str = "", author: str = "") -> IRRule | None:
    """
    Tente de parser une règle depuis un texte naturel.

    Format reconnu (flexible) :
        "SI <variable> <op> <valeur> ALORS <action>(<target>, <val>)"
        "IF <variable> <op> <value> THEN <action>(<target>, <val>)"
        "CONDITION: ... ACTION: ..."

    Retourne None si le texte n'est pas parsable.
    """
    import uuid
    from datetime import UTC, datetime

    text_lower = text.lower()

    # Détecter format CONDITION: ... ACTION:
    if "condition:" in text_lower and "action:" in text_lower:
        return _parse_structured_rule(text, rule_id, author)

    # Détecter format SI ... ALORS / IF ... THEN
    for si, alors in [("si ", " alors "), ("if ", " then ")]:
        if si in text_lower:
            parts = text_lower.split(alors, 1)
            if len(parts) == 2:
                cond_str = parts[0].replace(si, "").strip()
                act_str = parts[1].strip()
                cond = _parse_condition(cond_str)
                act = _parse_action(act_str)
                if cond and act:
                    return IRRule(
                        rule_id=rule_id or f"rule_{uuid.uuid4().hex[:8]}",
                        label=text[:80],
                        conditions=[cond],
                        actions=[act],
                        author_wallet=author,
                        created_at=datetime.now(UTC).isoformat(),
                    )
    return None


def _parse_condition(text: str) -> RuleCondition | None:
    """Parse 'variable op valeur' depuis texte."""
    for op in [">=", "<=", "!=", ">", "<", "=="]:
        if op in text:
            parts = text.split(op, 1)
            if len(parts) == 2:
                var = parts[0].strip()
                val_raw = parts[1].strip()
                try:
                    val = float(val_raw)
                except ValueError:
                    val = val_raw.strip("'\"")
                return RuleCondition(var, ConditionOperator(op), val)
    return None


def _parse_action(text: str) -> RuleAction | None:
    """Parse 'action(target, valeur)' depuis texte."""
    # Pattern: action_type(target, value)
    m = re.match(r"(\w+)\(([^,]+),\s*([^)]+)\)", text.strip())
    if m:
        action_type, target, val_raw = m.group(1), m.group(2).strip(), m.group(3).strip()
        try:
            val = float(val_raw)
        except ValueError:
            val = val_raw.strip("'\"")
        return RuleAction(target, action_type, val)
    # Fallback : "set target to val"
    m2 = re.match(r"set\s+(\w+)\s+(?:to|=)\s+(.+)", text.strip())
    if m2:
        try:
            val = float(m2.group(2).strip())
        except ValueError:
            val = m2.group(2).strip().strip("'\"")
        return RuleAction(m2.group(1), "set", val)
    return None


def _parse_structured_rule(text: str, rule_id: str, author: str) -> IRRule | None:
    """Parse format RULE [...] | CONDITION: ... | ACTION: ..."""
    import uuid
    from datetime import UTC, datetime

    cond_match = re.search(r"CONDITION[S]?:\s*(.+?)(?:\s*\||\s*ACTION)", text, re.IGNORECASE)
    act_match  = re.search(r"ACTION[S]?:\s*(.+?)(?:\s*\||\s*AUTHOR|$)", text, re.IGNORECASE)
    label_match = re.search(r"RULE\s*\[([^\]]+)\]\s*([^|]+)", text, re.IGNORECASE)

    cond = _parse_condition(cond_match.group(1).strip()) if cond_match else None
    act  = _parse_action(act_match.group(1).strip()) if act_match else None
    label = label_match.group(2).strip() if label_match else text[:80]

    if cond and act:
        return IRRule(
            rule_id=rule_id or f"rule_{uuid.uuid4().hex[:8]}",
            label=label,
            conditions=[cond],
            actions=[act],
            author_wallet=author,
            created_at=datetime.now(UTC).isoformat(),
        )
    return None


# ── Registre de règles (stockage local) ─────────────────────────────────────

class RulesRegistry:
    """
    Registre des règles actives — stocké dans data/ir_rules.json.
    Les règles sont aussi gravées dans la blockchain via /ai/memo.
    """

    def __init__(self, path: str | None = None) -> None:
        from pathlib import Path
        self._path = Path(path) if path else Path("data") / "ir_rules.json"
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> list[IRRule]:
        if not self._path.exists():
            return []
        try:
            raw = json.loads(self._path.read_text())
            return [IRRule.from_dict(r) for r in raw]
        except Exception:
            return []

    def _save(self, rules: list[IRRule]) -> None:
        self._path.write_text(json.dumps([r.to_dict() for r in rules], indent=2, ensure_ascii=False))

    def add(self, rule: IRRule) -> IRRule:
        rules = self._load()
        # Remplacer si même rule_id
        rules = [r for r in rules if r.rule_id != rule.rule_id]
        rules.append(rule)
        self._save(rules)
        return rule

    def get(self, rule_id: str) -> IRRule | None:
        return next((r for r in self._load() if r.rule_id == rule_id), None)

    def list_all(self) -> list[IRRule]:
        return self._load()

    def delete(self, rule_id: str) -> bool:
        rules = self._load()
        before = len(rules)
        rules = [r for r in rules if r.rule_id != rule_id]
        self._save(rules)
        return len(rules) < before

    def evaluate_all(self, context: dict[str, Any]) -> list[RuleEvaluationResult]:
        """Évalue toutes les règles actives contre le contexte fourni."""
        return [r.evaluate(context) for r in self._load()]

    def evaluate_one(self, rule_id: str, context: dict[str, Any]) -> RuleEvaluationResult | None:
        rule = self.get(rule_id)
        if rule is None:
            return None
        return rule.evaluate(context)


