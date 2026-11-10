"""Module to calculate derived metrics from mathematical formulas specified in CSV."""
import ast
import csv
import os

from src.parsing.ast_engine import (
    BUILTIN_FUNCS, BUILTIN_VARS,
    prepare_expression, validate_expression, resolve_var_val, eval_node
)
from src.parsing.computed_series_storage import (
    COMPUTED_SERIES_FILENAME, COMPUTED_SERIES_APPDATA_PATH,
    ensure_computed_series_file, notify_parsing_error
)


def extract_variable_names(clean_expr: str, var_map: dict) -> list:
    """Extracts all variable identifiers used in an expression, omitting built-in functions/constants."""
    parsed = ast.parse(clean_expr, mode='eval')
    names = []
    for node in ast.walk(parsed):
        if isinstance(node, ast.Name):
            raw_name = var_map.get(node.id, node.id)
            if raw_name.lower() in BUILTIN_FUNCS or raw_name.lower() in BUILTIN_VARS:
                continue
            names.append(raw_name)
    return names


def get_available_variables_for_dataset(dataset_type: str, prior_names: list = None) -> set:
    """Returns the set of valid metric/variable names for a dataset."""
    from src.parsing.definitions import COUNTRY_FIRST_HEADERS, SOCIETAL_VALUE_NAMES, CREDIT_HEADERS, market_stats, POPULATION_HEADERS
    import src.parsing.stores as stores

    vars_set = set(["PREV", "prev"])
    d_type = (dataset_type or "").strip().lower()

    if d_type in ("country", "country_metric", "country_stats", "credit", "credit_metric", "credit_stats"):
        vars_set.update(COUNTRY_FIRST_HEADERS)
        vars_set.update(SOCIETAL_VALUE_NAMES)
        vars_set.update(CREDIT_HEADERS)
        vars_set.update([
            "Supply", "Demand", "Credit supply", "Credit demand", "locations", "num_locations",
            "Population", "population", "total_population"
        ])
    elif d_type in ("market", "markets", "market_metric", "market_stats"):
        vars_set.update(market_stats)
        vars_set.update(["locations", "population", "total_population"])
    elif d_type in ("region", "regional", "regional_metric", "regional_stats"):
        vars_set.update(POPULATION_HEADERS)
        vars_set.update([
            "locations", "population", "total_population",
            "Gravel Road", "Paved Road",
            "Castle", "University", "Gold mine", "Farm", "Harbour", "Port"
        ])
        if stores.rt_cumulative_store:
            for k in stores.rt_cumulative_store.keys():
                vars_set.add(k[2])
        if stores.bt_cumulative_store:
            for k in stores.bt_cumulative_store.keys():
                vars_set.add(k[2])
        if stores.gp_cumulative_store:
            for k in stores.gp_cumulative_store.keys():
                good = k[2]
                vars_set.add(good)
                if good.lower().endswith(" price"):
                    vars_set.add(good[:-6].strip())
                    vars_set.add(f"price_{good[:-6].strip()}")

    if prior_names:
        vars_set.update(prior_names)

    return vars_set


def check_missing_variables(clean_expr: str, var_map: dict, dataset_type: str, prior_names: list = None) -> list:
    """Returns a list of variables in the expression that do not exist in the dataset."""
    known = get_available_variables_for_dataset(dataset_type, prior_names)
    canon = lambda s: s.strip().lower().replace('_', ' ')
    known_canon = {canon(k) for k in known}
    used = extract_variable_names(clean_expr, var_map)
    missing = []
    for var in used:
        c = canon(var)
        if c in ("prev", "true", "false"):
            continue
        if c not in known_canon and f"{c} price" not in known_canon:
            missing.append(var)
    return missing


def load_computed_series_definitions():
    """Reads configured formulas from computed_series.csv and validates them."""
    ensure_computed_series_file()
    definitions = []
    filepath = COMPUTED_SERIES_APPDATA_PATH if os.path.exists(COMPUTED_SERIES_APPDATA_PATH) else COMPUTED_SERIES_FILENAME
    if not os.path.exists(filepath):
        return definitions

    try:
        with open(filepath, mode="r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception as e:
        print(f"Failed to read computed series config: {e}")
        return definitions

    if not lines:
        return definitions

    reader = csv.DictReader(lines)
    for row_idx, row in enumerate(reader, start=2):
        d_type = row.get("dataset_type", "").strip().lower()
        name = row.get("new_metric_name", "").strip()
        expr = row.get("expression", "").strip()
        if not (d_type and name and expr):
            continue

        try:
            clean_expr, var_map = validate_expression(expr)
            definitions.append({
                "dataset_type": d_type,
                "metric_name": name,
                "expression": expr,
                "clean_expr": clean_expr,
                "var_map": var_map,
                "description": row.get("description", "").strip(),
                "line": row_idx
            })
        except Exception as err:
            details = f"Metric: {name}\nExpression: {expr}\nError: {err}"
            notify_parsing_error(details, row_idx)

    return definitions


def extract_condition_values_str(condition_str: str, variables: dict, precompiled=None, series_history=None, moment=None) -> str:
    """Evaluates individual function calls and variables inside the condition to provide human-readable values."""
    if not condition_str:
        return ""
    try:
        from src.parsing.numeric_utils import format_metric_3digits
        clean_expr, var_map = precompiled if precompiled else prepare_expression(condition_str)
        parsed = ast.parse(clean_expr, mode='eval')

        eval_pairs = []
        # Find calls like relative_rate(...) or direct variables
        for node in ast.walk(parsed):
            if isinstance(node, ast.Call):
                f_name = node.func.id.lower()
                arg_name = ""
                if node.args and isinstance(node.args[0], ast.Name):
                    raw_id = node.args[0].id
                    arg_name = var_map.get(raw_id, raw_id)
                elif node.args:
                    arg_name = "..."
                call_label = f"{f_name}({arg_name})"
                try:
                    call_val = eval_node(node, variables, var_map, series_history, moment)
                    val_str = f"{call_val:.2f}%" if "relative" in f_name or "rel_" in f_name or "ratio" in f_name else format_metric_3digits(call_val)
                    eval_pairs.append(f"{call_label}={val_str}")
                except Exception:
                    pass

        # Also extract raw metrics
        used_vars = extract_variable_names(clean_expr, var_map)
        for v in used_vars:
            val = resolve_var_val(v, variables)
            eval_pairs.append(f"{v}={format_metric_3digits(val)}")

        # Deduplicate preserving order
        seen = set()
        unique = []
        for p in eval_pairs:
            if p not in seen:
                seen.add(p)
                unique.append(p)
        return ", ".join(unique)
    except Exception:
        return ""