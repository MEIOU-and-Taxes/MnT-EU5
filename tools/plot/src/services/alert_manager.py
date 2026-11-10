import json
import os

from src.constants import ALERTS_PATH
from src.parsing.computed_series import extract_variable_names, \
    extract_condition_values_str
from src.parsing.ast_engine import validate_expression, evaluate_condition
from src.parsing.transformers.region import parse_data_regional_metrics
from src.parsing.transformers.market import parse_data_market_metrics
from src.parsing.transformers.country import parse_data_country_metrics

DEFAULT_ALERTS = [
    {
        "id": "sample-1",
        "name": "High Debt Spiral",
        "dataset_type": "country",
        "entity_filter": "All",
        "condition": "total_debt > (income * 24) and bank_interest > 0.05",
        "enabled": False
    },
    {
        "id": "sample-2",
        "name": "Famine / Food Depletion",
        "dataset_type": "market",
        "entity_filter": "All",
        "condition": "[Food Stockpile Perc] < 0.20 or [Monthly Food] < -100",
        "enabled": False
    },
    {
        "id": "sample-3",
        "name": "Rapid Population Decline",
        "dataset_type": "region",
        "entity_filter": "All",
        "condition": "rate([Total population]) < -1000",
        "enabled": False
    }
]

# Set of already triggered alert keys: (rule_id, entity, moment, condition)
_triggered_alert_keys = set()

def load_alerts() -> list:
    """Loads configured alert rules from ALERTS_PATH, returning defaults if not found."""
    if not os.path.exists(ALERTS_PATH):
        save_alerts(DEFAULT_ALERTS)
        return list(DEFAULT_ALERTS)
    try:
        with open(ALERTS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
    except Exception as e:
        print(f"Error reading {ALERTS_PATH}: {e}")
    return list(DEFAULT_ALERTS)


def save_alerts(rules: list):
    """Persists alert rules to ALERTS_PATH."""
    try:
        with open(ALERTS_PATH, "w", encoding="utf-8") as f:
            json.dump(rules, f, indent=2)
    except Exception as e:
        print(f"Error saving {ALERTS_PATH}: {e}")


def get_dataset_records(dataset_type: str):
    """Fetches raw aggregated dataset dictionaries for the specified dataset type."""
    d_type = (dataset_type or "").strip().lower()
    if d_type in ("country", "country_metric", "credit"):
        return parse_data_country_metrics()
    elif d_type in ("market", "markets"):
        return parse_data_market_metrics()
    elif d_type in ("region", "regional"):
        return parse_data_regional_metrics()
    return []


def build_entity_time_contexts(dataset_type: str, entity_filter: str = "All"):
    """
    Groups data by entity and moment into comprehensive context dictionaries
    containing all metrics for that entity at that moment.
    Returns: dict mapping entity_name -> sorted list of (moment, vars_dict)
    """
    records = get_dataset_records(dataset_type)
    by_entity_moment = {}

    target_filter = (entity_filter or "All").strip().lower()

    for r in records:
        m = r["moment"]
        ent = r.get("country") or r.get("market") or r.get("region") or r.get("tag") or ""
        if target_filter != "all" and ent.strip().lower() != target_filter and r.get("tag", "").lower() != target_filter:
            continue

        ctx = by_entity_moment.setdefault((ent, m), {
            "moment": m, "year": m, "entity": ent, "country": ent, "market": ent, "region": ent,
            "locations": float(r.get("locations", 0.0)),
            "population": float(r.get("population", 0.0)),
            "total_population": float(r.get("total_population", r.get("population", 0.0))),
        })

        if r.get("tag"):
            ctx["tag"] = r["tag"]

        met = r.get("metric") or r.get("country_metric") or r.get("statistic") or r.get("regional_metric")
        if met:
            val = float(r.get("value", 0.0))
            ctx[met] = val
            ctx[met.lower()] = val
            ctx[met.replace(' ', '_')] = val
            ctx[met.lower().replace(' ', '_')] = val

    entity_series = {}
    for (ent, m), ctx in by_entity_moment.items():
        entity_series.setdefault(ent, []).append((m, ctx))

    for ent in entity_series:
        entity_series[ent].sort(key=lambda x: x[0])

    return entity_series


def evaluate_alert_rule(rule: dict, latest_only=False):
    """
    Evaluates an alert rule against loaded data.
    Returns: (status: str, matches: list of dicts, error_msg: str)
      status: "FIRED", "NOT_FIRED", or "ERROR"
    """
    cond_str = rule.get("condition", "").strip()
    if not cond_str:
        return "ERROR", [], "Condition expression is empty."

    try:
        clean_expr, var_map = validate_expression(cond_str)
    except Exception as e:
        return "ERROR", [], f"Invalid syntax: {e}"

    dataset_type = rule.get("dataset_type", "country")
    entity_filter = rule.get("entity_filter", "All")

    entity_series = build_entity_time_contexts(dataset_type, entity_filter)
    if not entity_series:
        return "NOT_FIRED", [], ""

    matches = []
    precompiled = (clean_expr, var_map)
    required_vars = extract_variable_names(clean_expr, var_map)

    for ent, moments in entity_series.items():
        if not moments:
            continue

        # If evaluating latest_only, find the most recent moment where all required variables are present and non-zero
        if latest_only:
            target_moments = []
            for m_item in reversed(moments):
                ctx = m_item[1]
                # Check if at least one metric referenced by the rule exists in this context
                has_metric = any((v in ctx or v.lower() in ctx or v.lower().replace(' ', '_') in ctx) for v in required_vars)
                if has_metric or not required_vars:
                    target_moments = [m_item]
                    break
            eval_list = target_moments
        else:
            eval_list = moments

        for m, ctx in eval_list:
            # Skip if none of the referenced variables are populated in this context
            if required_vars and not any((v in ctx or v.lower() in ctx or v.lower().replace(' ', '_') in ctx) for v in required_vars):
                continue

            fired = evaluate_condition(cond_str, ctx, precompiled=precompiled, series_history=moments, moment=m)
            if fired:
                val_summary = extract_condition_values_str(cond_str, ctx, precompiled=precompiled, series_history=moments, moment=m)
                matches.append({
                    "moment": m,
                    "entity": ent,
                    "rule_id": rule.get("id"),
                    "rule_name": rule.get("name"),
                    "condition": cond_str,
                    "values": val_summary
                })

    matches.sort(key=lambda x: (x["moment"], x["entity"]), reverse=True)
    status = "FIRED" if matches else "NOT_FIRED"
    return status, matches, ""


def check_active_alerts(latest_only=True):
    """Evaluates all enabled alert rules and returns newly fired matches."""
    rules = load_alerts()
    newly_fired = []
    for rule in rules:
        if not rule.get("enabled", True):
            continue
        status, matches, _ = evaluate_alert_rule(rule, latest_only=latest_only)
        if status == "FIRED":
            for m in matches:
                sig = (m.get("rule_id"), m.get("entity"), m.get("moment"), m.get("condition"))
                if sig not in _triggered_alert_keys:
                    _triggered_alert_keys.add(sig)
                    newly_fired.append(m)
    return newly_fired

def clear_triggered_alerts():
    """Clears history of fired alert keys."""
    global _triggered_alert_keys
    _triggered_alert_keys.clear()