"""Tests IR v0.2 — Moteur de règles déclaratives (Smart Contracts PoL).

Couvre :
- RuleCondition : évaluation de chaque opérateur
- RuleAction : to_dict / from_dict
- IRRule : evaluate() AND / OR, to_pol_text(), sérialisation
- parse_rule_from_text() : format SI...ALORS, IF...THEN, CONDITION/ACTION
- RulesRegistry : add, get, list_all, delete, evaluate_all, evaluate_one (fichier tmp)
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from src.artcb.ir.rules import (
    ConditionOperator,
    IRRule,
    RuleAction,
    RuleCondition,
    RuleEvaluationResult,
    RuleStatus,
    RulesRegistry,
    parse_rule_from_text,
)


# ─────────────────────────────────────────────────────────────────────────────
#  RuleCondition
# ─────────────────────────────────────────────────────────────────────────────

class TestRuleCondition:

    def test_gt_true(self):
        c = RuleCondition("pol_score", ConditionOperator.GT, 0.9)
        assert c.evaluate({"pol_score": 0.95}) is True

    def test_gt_false(self):
        c = RuleCondition("pol_score", ConditionOperator.GT, 0.9)
        assert c.evaluate({"pol_score": 0.9}) is False

    def test_gte_equal(self):
        c = RuleCondition("balance", ConditionOperator.GTE, 100.0)
        assert c.evaluate({"balance": 100.0}) is True

    def test_lt_true(self):
        c = RuleCondition("block_count", ConditionOperator.LT, 500)
        assert c.evaluate({"block_count": 200}) is True

    def test_lte_equal(self):
        c = RuleCondition("x", ConditionOperator.LTE, 10)
        assert c.evaluate({"x": 10}) is True

    def test_eq_string(self):
        c = RuleCondition("wallet", ConditionOperator.EQ, "artcb1alice")
        assert c.evaluate({"wallet": "artcb1alice"}) is True
        assert c.evaluate({"wallet": "artcb1bob"}) is False

    def test_neq_true(self):
        c = RuleCondition("status", ConditionOperator.NEQ, "inactive")
        assert c.evaluate({"status": "active"}) is True

    def test_in_operator(self):
        c = RuleCondition("role", ConditionOperator.IN, ["admin", "miner", "validator"])
        assert c.evaluate({"role": "admin"}) is True
        assert c.evaluate({"role": "user"}) is False

    def test_contains_operator(self):
        c = RuleCondition("memo", ConditionOperator.CONTAINS, "artcb")
        assert c.evaluate({"memo": "transfer artcb tokens"}) is True
        assert c.evaluate({"memo": "hello world"}) is False

    def test_missing_variable_returns_false(self):
        c = RuleCondition("missing_key", ConditionOperator.GT, 0)
        assert c.evaluate({}) is False

    def test_to_dict_from_dict(self):
        c = RuleCondition("pol_score", ConditionOperator.GTE, 0.85)
        d = c.to_dict()
        assert d == {"variable": "pol_score", "operator": ">=", "value": 0.85}
        c2 = RuleCondition.from_dict(d)
        assert c2.variable == "pol_score"
        assert c2.operator == ConditionOperator.GTE
        assert c2.value == 0.85


# ─────────────────────────────────────────────────────────────────────────────
#  RuleAction
# ─────────────────────────────────────────────────────────────────────────────

class TestRuleAction:

    def test_to_dict(self):
        a = RuleAction("reward_bonus", "set", 0.5)
        assert a.to_dict() == {"target": "reward_bonus", "action_type": "set", "value": 0.5}

    def test_from_dict(self):
        a = RuleAction.from_dict({"target": "notify", "action_type": "call", "value": "telegram:alert"})
        assert a.target == "notify"
        assert a.action_type == "call"
        assert a.value == "telegram:alert"


# ─────────────────────────────────────────────────────────────────────────────
#  IRRule — evaluate()
# ─────────────────────────────────────────────────────────────────────────────

class TestIRRule:

    def _make_rule(self, combinator: str = "AND") -> IRRule:
        return IRRule(
            rule_id="rule_test01",
            label="Test rule",
            conditions=[
                RuleCondition("pol_score", ConditionOperator.GT, 0.8),
                RuleCondition("balance", ConditionOperator.GTE, 100.0),
            ],
            actions=[RuleAction("bonus", "set", 1.0)],
            combinator=combinator,
        )

    def test_evaluate_and_triggered(self):
        rule = self._make_rule("AND")
        ctx = {"pol_score": 0.95, "balance": 150.0}
        result = rule.evaluate(ctx)
        assert result.triggered is True
        assert result.status == RuleStatus.TRUE
        assert len(result.actions_applicable) == 1

    def test_evaluate_and_not_triggered(self):
        rule = self._make_rule("AND")
        ctx = {"pol_score": 0.95, "balance": 50.0}  # balance < 100
        result = rule.evaluate(ctx)
        assert result.triggered is False
        assert result.status == RuleStatus.FALSE
        assert result.actions_applicable == []

    def test_evaluate_or_triggered_partial(self):
        rule = self._make_rule("OR")
        ctx = {"pol_score": 0.95, "balance": 50.0}  # seul pol_score true
        result = rule.evaluate(ctx)
        assert result.triggered is True

    def test_evaluate_or_not_triggered(self):
        rule = self._make_rule("OR")
        ctx = {"pol_score": 0.5, "balance": 50.0}
        result = rule.evaluate(ctx)
        assert result.triggered is False

    def test_to_pol_text(self):
        rule = self._make_rule()
        text = rule.to_pol_text()
        assert "rule_test01" in text
        assert "pol_score" in text
        assert "set(bonus, 1.0)" in text

    def test_to_dict_from_dict_roundtrip(self):
        rule = self._make_rule()
        d = rule.to_dict()
        rule2 = IRRule.from_dict(d)
        assert rule2.rule_id == rule.rule_id
        assert rule2.label == rule.label
        assert len(rule2.conditions) == 2
        assert len(rule2.actions) == 1
        assert rule2.combinator == "AND"

    def test_conditions_results_count(self):
        rule = self._make_rule()
        result = rule.evaluate({"pol_score": 0.9, "balance": 200.0})
        assert len(result.conditions_results) == 2


# ─────────────────────────────────────────────────────────────────────────────
#  parse_rule_from_text()
# ─────────────────────────────────────────────────────────────────────────────

class TestParseRuleFromText:

    def test_parse_si_alors(self):
        text = "SI pol_score > 0.9 ALORS set(bonus, 0.5)"
        rule = parse_rule_from_text(text, rule_id="rule_parse_01")
        assert rule is not None
        assert rule.rule_id == "rule_parse_01"
        assert len(rule.conditions) == 1
        assert rule.conditions[0].variable == "pol_score"
        assert rule.conditions[0].operator == ConditionOperator.GT
        assert float(rule.conditions[0].value) == pytest.approx(0.9)
        assert rule.actions[0].action_type == "set"
        assert rule.actions[0].target == "bonus"

    def test_parse_if_then(self):
        text = "if balance_artcb >= 100 then transfer(artcb1bob, 10.0)"
        rule = parse_rule_from_text(text, rule_id="rule_parse_02")
        assert rule is not None
        assert rule.conditions[0].variable == "balance_artcb"
        assert rule.conditions[0].operator == ConditionOperator.GTE
        assert rule.actions[0].action_type == "transfer"
        assert rule.actions[0].target == "artcb1bob"

    def test_parse_unparseable_returns_none(self):
        rule = parse_rule_from_text("ceci n'est pas une règle", rule_id="x")
        assert rule is None

    def test_parse_structured_condition_action(self):
        text = "RULE [rule_x] Halving check | CONDITION: block_count > 210000 | ACTION: set(halving, 1)"
        rule = parse_rule_from_text(text, rule_id="rule_halving")
        assert rule is not None
        assert rule.conditions[0].variable == "block_count"


# ─────────────────────────────────────────────────────────────────────────────
#  RulesRegistry (fichier temporaire)
# ─────────────────────────────────────────────────────────────────────────────

class TestRulesRegistry:

    def _registry(self, tmp_path: Path) -> RulesRegistry:
        return RulesRegistry(path=str(tmp_path / "test_rules.json"))

    def _rule(self, rule_id: str = "rule_001") -> IRRule:
        return IRRule(
            rule_id=rule_id,
            label=f"Règle {rule_id}",
            conditions=[RuleCondition("x", ConditionOperator.GT, 5)],
            actions=[RuleAction("y", "set", 1.0)],
        )

    def test_add_and_get(self, tmp_path):
        reg = self._registry(tmp_path)
        rule = self._rule()
        reg.add(rule)
        fetched = reg.get("rule_001")
        assert fetched is not None
        assert fetched.rule_id == "rule_001"

    def test_add_replaces_same_id(self, tmp_path):
        reg = self._registry(tmp_path)
        rule1 = IRRule(rule_id="r1", label="v1", conditions=[], actions=[])
        rule2 = IRRule(rule_id="r1", label="v2", conditions=[], actions=[])
        reg.add(rule1)
        reg.add(rule2)
        assert len(reg.list_all()) == 1
        assert reg.get("r1").label == "v2"

    def test_list_all(self, tmp_path):
        reg = self._registry(tmp_path)
        for i in range(3):
            reg.add(self._rule(f"rule_{i:03d}"))
        assert len(reg.list_all()) == 3

    def test_delete(self, tmp_path):
        reg = self._registry(tmp_path)
        reg.add(self._rule("r_del"))
        assert reg.delete("r_del") is True
        assert reg.get("r_del") is None

    def test_delete_nonexistent(self, tmp_path):
        reg = self._registry(tmp_path)
        assert reg.delete("ghost") is False

    def test_evaluate_all(self, tmp_path):
        reg = self._registry(tmp_path)
        reg.add(self._rule("r_eval"))
        results = reg.evaluate_all({"x": 10})  # x > 5 → triggered
        assert len(results) == 1
        assert results[0].triggered is True

    def test_evaluate_one_found(self, tmp_path):
        reg = self._registry(tmp_path)
        reg.add(self._rule("r_one"))
        result = reg.evaluate_one("r_one", {"x": 3})  # x > 5 → false
        assert result is not None
        assert result.triggered is False

    def test_evaluate_one_not_found(self, tmp_path):
        reg = self._registry(tmp_path)
        result = reg.evaluate_one("ghost", {})
        assert result is None

    def test_empty_registry_file_missing(self, tmp_path):
        reg = self._registry(tmp_path)
        assert reg.list_all() == []
