import json
import os
import uuid

from src.constants import ALERTS_PATH
from src.parsing.computed_series import validate_expression, evaluate_condition
from src.parsing.transformers import parse_data_country_metrics, parse_data_market_metrics, parse_data_regional_metrics

DEFAULT_ALERTS = [
    {
        "id": "sample-1",
        "name": "High Debt Spiral",
        "dataset_type": "country",
        "entity_filter": "All",
        "condition": "total_debt > (income * 24) and bank_interest > 0.05",
        "density_mode": "none",
        "baseline_mode": "none",
        "derivative_order": 0,
        "enabled": False,
        "notify_popup": True,
        "notify_sound": True
    },
    {
        "id": "sample-2",
        "name": "Famine / Food Depletion",
        "dataset_type": "market",
        "entity_filter": "All",
        "condition": "[Food Stockpile Perc] < 0.20 or [Monthly Food] < -100",
        "density_mode": "none",
        "baseline_mode": "none",
        "derivative_order": 0,
        "enabled": False,
        "notify_popup": True,
        "notify_sound": True
    },
    {
        "id": "sample-3",
        "name": "Rapid Population Decline",
        "dataset_type": "region",
        "entity_filter": "All",
        "condition": "[Total population] < -1000",
        "density_mode": "none",
        "baseline_mode": "none",
        "derivative_order": 1,
        "enabled": False,
        "notify_popup": True,
        "notify_sound": False
    }
]


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


def apply_transformations(series_moments: list, density_mode="none", baseline_mode="none", derivative_order=0):
    """
    Applies density (per location/pop), baseline (ratio/diff), and derivative (rate/accel)
    to numeric metrics across time series moments for a single entity.
    """
    if not series_moments:
        return []

    # 1. Density normalization
    dense_series = []
    for m, ctx in series_moments:
        c = dict(ctx)
        locs = c.get("locations", 0.0)
        pop = c.get("total_population", c.get("population", 0.0))

        if density_mode == "location" and locs > 0:
            for k, v in list(c.items()):
                if isinstance(v, (int, float)) and k not in ("moment", "year", "locations", "population", "total_population"):
                    c[k] = v / locs
        elif density_mode == "population" and pop > 0:
            for k, v in list(c.items()):
                if isinstance(v, (int, float)) and k not in ("moment", "year", "locations", "population", "total_population"):
                    c[k] = (v / pop) * 1_000_000.0

        dense_series.append((m, c))

    # 2. Baseline transformation (% change or diff from base year)
    base_transformed = []
    if baseline_mode in ("ratio", "difference") and dense_series:
        base_ctx = dense_series[0][1]
        for m, ctx in dense_series:
            c = dict(ctx)
            for k, v in list(ctx.items()):
                if isinstance(v, (int, float)) and k not in ("moment", "year", "locations", "population", "total_population"):
                    base_v = base_ctx.get(k)
                    if base_v is not None:
                        if baseline_mode == "ratio":
                            c[k] = (((v / base_v) - 1.0) * 100.0) if abs(base_v) > 1e-12 else 0.0
                        else:
                            c[k] = v - base_v
            base_transformed.append((m, c))
    else:
        base_transformed = dense_series

    # 3. Derivative transformation (order 1: rate, order 2: acceleration)
    deriv_transformed = []
    if derivative_order == 1:
        for i in range(1, len(base_transformed)):
            curr_m, curr_c = base_transformed[i]
            prev_m, prev_c = base_transformed[i - 1]
            c = dict(curr_c)
            for k, v in curr_c.items():
                if isinstance(v, (int, float)) and k not in ("moment", "year", "locations", "population", "total_population"):
                    prev_v = prev_c.get(k, 0.0)
                    c[k] = v - prev_v
            deriv_transformed.append((curr_m, c))
    elif derivative_order == 2:
        for i in range(2, len(base_transformed)):
            curr_m, curr_c = base_transformed[i]
            prev1_m, prev1_c = base_transformed[i - 1]
            prev2_m, prev2_c = base_transformed[i - 2]
            c = dict(curr_c)
            for k, v in curr_c.items():
                if isinstance(v, (int, float)) and k not in ("moment", "year", "locations", "population", "total_population"):
                    d_curr = v - prev1_c.get(k, 0.0)
                    d_prev = prev1_c.get(k, 0.0) - prev2_c.get(k, 0.0)
                    c[k] = d_curr - d_prev
            deriv_transformed.append((curr_m, c))
    else:
        deriv_transformed = base_transformed

    return deriv_transformed


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
    density_mode = rule.get("density_mode", "none")
    baseline_mode = rule.get("baseline_mode", "none")
    derivative_order = int(rule.get("derivative_order", 0))

    entity_series = build_entity_time_contexts(dataset_type, entity_filter)
    if not entity_series:
        return "NOT_FIRED", [], ""

    matches = []
    precompiled = (clean_expr, var_map)

    for ent, moments in entity_series.items():
        transformed = apply_transformations(moments, density_mode, baseline_mode, derivative_order)
        if latest_only and transformed:
            transformed = [transformed[-1]]

        for m, ctx in transformed:
            fired = evaluate_condition(cond_str, ctx, precompiled=precompiled)
            if fired:
                matches.append({
                    "moment": m,
                    "entity": ent,
                    "rule_id": rule.get("id"),
                    "rule_name": rule.get("name"),
                    "condition": cond_str,
                    "notify_popup": rule.get("notify_popup", True),
                    "notify_sound": rule.get("notify_sound", True),
                })

    matches.sort(key=lambda x: (x["moment"], x["entity"]), reverse=True)
    status = "FIRED" if matches else "NOT_FIRED"
    return status, matches, ""


def check_active_alerts(latest_only=True):
    """Evaluates all enabled alert rules and returns fired matches."""
    rules = load_alerts()
    all_fired = []
    for rule in rules:
        if not rule.get("enabled", True):
            continue
        status, matches, _ = evaluate_alert_rule(rule, latest_only=latest_only)
        if status == "FIRED":
            all_fired.extend(matches)
    return all_fired