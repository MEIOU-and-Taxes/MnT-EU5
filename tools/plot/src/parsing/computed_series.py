"""Module to calculate derived metrics from mathematical formulas specified in CSV."""
import ast
import csv
import operator as op
import os
import re
import shutil

from src.constants import APPDATA_DIR

COMPUTED_SERIES_FILENAME = "computed_series.csv"
COMPUTED_SERIES_APPDATA_PATH = os.path.join(APPDATA_DIR, COMPUTED_SERIES_FILENAME)

DEFAULT_COMPUTED_SERIES_CSV = """dataset_type,new_metric_name,expression,description
country,Debt/Income,total_debt / income,Total debt divided by annual/monthly income
country,Adjusted Burden,[Debt/Income] * bank_interest,Interest payment burden
country,Credit Supply/Demand,Supply / Demand,Credit supply to demand ratio
region,Gold/Gold Mine,Gold / gold_mine,Gold price divided by gold mines
region,Food net,[Food production] + [Food consumption],Remaining produced food
market,Estate/state trade capacity,[Burgher Trade Capacity] / [Merchant Capacity],
"""

# Safe AST operators map
ALLOWED_OPERATORS = {
    ast.Add: op.add,
    ast.Sub: op.sub,
    ast.Mult: op.mul,
    ast.Div: op.truediv,
    ast.FloorDiv: op.floordiv,
    ast.Mod: op.mod,
    ast.Pow: op.pow,
    ast.USub: op.neg,
    ast.UAdd: op.pos,
}

_reported_parsing_errors = set()


def prepare_expression(expr_str: str):
    """
    Converts carets to power operators and maps bracketed variables (e.g., [Credit Demand])
    to safe identifier tokens so variable names containing spaces/symbols parse cleanly.
    """
    clean = expr_str.strip().replace('^', '**')
    var_map = {}

    def repl(m):
        raw_name = m.group(1).strip()
        safe_id = f"__bvar_{len(var_map)}__"
        var_map[safe_id] = raw_name
        return safe_id

    clean = re.sub(r'\[([^\]]+)\]', repl, clean)
    return clean, var_map


def validate_expression(expr_str: str):
    """Parses and checks that the expression contains only allowed arithmetic nodes."""
    clean, var_map = prepare_expression(expr_str)
    parsed = ast.parse(clean, mode='eval')

    def check_node(n):
        if isinstance(n, ast.Expression):
            check_node(n.body)
        elif isinstance(n, ast.Constant):
            if not isinstance(n.value, (int, float)):
                raise ValueError(f"Literal '{n.value}' is not a numeric constant")
        elif hasattr(ast, 'Num') and isinstance(n, ast.Num):
            pass
        elif isinstance(n, ast.Name):
            pass
        elif isinstance(n, ast.UnaryOp):
            if type(n.op) not in ALLOWED_OPERATORS:
                raise ValueError(f"Unary operator '{type(n.op).__name__}' is not allowed")
            check_node(n.operand)
        elif isinstance(n, ast.BinOp):
            if type(n.op) not in ALLOWED_OPERATORS:
                raise ValueError(f"Binary operator '{type(n.op).__name__}' is not allowed")
            check_node(n.left)
            check_node(n.right)
        else:
            raise ValueError(f"Syntax element '{type(n).__name__}' is not supported")

    check_node(parsed)
    return clean, var_map


def extract_variable_names(clean_expr: str, var_map: dict) -> list:
    """Extracts all variable identifiers used in an expression."""
    parsed = ast.parse(clean_expr, mode='eval')
    names = []
    for node in ast.walk(parsed):
        if isinstance(node, ast.Name):
            raw_name = var_map.get(node.id, node.id)
            names.append(raw_name)
    return names


def get_available_variables_for_dataset(dataset_type: str, prior_names: list = None) -> set:
    """Returns the set of valid metric/variable names for a dataset."""
    from src.parsing.definitions import COUNTRY_FIRST_HEADERS, SOCIETAL_VALUE_NAMES, CREDIT_HEADERS, market_stats, POPULATION_HEADERS
    import src.parsing.stores as stores

    vars_set = set()
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
        if c not in known_canon and f"{c} price" not in known_canon:
            missing.append(var)
    return missing


def _eval_node(node, variables, var_map=None):
    """Recursively evaluates an AST node across binary/unary trees, constants, and variables."""
    if isinstance(node, ast.Constant):
        return float(node.value)
    elif hasattr(ast, 'Num') and isinstance(node, ast.Num):
        return float(node.n)
    elif isinstance(node, ast.Name):
        var_name = node.id
        if var_map and var_name in var_map:
            var_name = var_map[var_name]

        # Resolution across multiple naming styles (exact, lower, spaced, underscored)
        candidates = [
            var_name,
            var_name.lower(),
            var_name.replace('_', ' '),
            var_name.replace(' ', '_'),
            var_name.lower().replace('_', ' '),
            var_name.lower().replace(' ', '_')
        ]
        val = None
        for cand in candidates:
            if cand in variables:
                val = variables[cand]
                break

        try:
            return float(val) if val is not None else 0.0
        except (ValueError, TypeError):
            return 0.0
    elif isinstance(node, ast.UnaryOp):
        operand = _eval_node(node.operand, variables, var_map)
        op_type = type(node.op)
        if op_type in ALLOWED_OPERATORS:
            return ALLOWED_OPERATORS[op_type](operand)
        raise ValueError(f"Unsupported unary operator: {op_type}")
    elif isinstance(node, ast.BinOp):
        left = _eval_node(node.left, variables, var_map)
        right = _eval_node(node.right, variables, var_map)
        op_type = type(node.op)
        if op_type in ALLOWED_OPERATORS:
            if op_type in (ast.Div, ast.FloorDiv):
                if abs(right) < 1e-12:
                    return 0.0
            return ALLOWED_OPERATORS[op_type](left, right)
        raise ValueError(f"Unsupported binary operator: {op_type}")
    else:
        raise ValueError(f"Unsupported AST node expression: {type(node)}")


def evaluate_expression(expr_str: str, variables: dict, precompiled=None) -> float:
    """Evaluates a math formula string safely using an AST."""
    if not expr_str or not expr_str.strip():
        return 0.0
    try:
        if precompiled:
            clean_expr, var_map = precompiled
        else:
            clean_expr, var_map = prepare_expression(expr_str)
        parsed = ast.parse(clean_expr, mode='eval')
        res = _eval_node(parsed.body, variables, var_map)
        return float(res) if res is not None else 0.0
    except Exception:
        return 0.0


def ensure_computed_series_file():
    """Initializes computed_series.csv in APPDATA if not already present."""
    if not os.path.exists(COMPUTED_SERIES_APPDATA_PATH):
        if os.path.exists(COMPUTED_SERIES_FILENAME):
            shutil.copy(COMPUTED_SERIES_FILENAME, COMPUTED_SERIES_APPDATA_PATH)
        else:
            with open(COMPUTED_SERIES_APPDATA_PATH, "w", encoding="utf-8") as f:
                f.write(DEFAULT_COMPUTED_SERIES_CSV)


def load_raw_computed_series_rows():
    """Loads all formula rows as raw dictionaries for UI editing."""
    ensure_computed_series_file()
    filepath = COMPUTED_SERIES_APPDATA_PATH if os.path.exists(COMPUTED_SERIES_APPDATA_PATH) else COMPUTED_SERIES_FILENAME
    rows = []
    if not os.path.exists(filepath):
        return rows
    try:
        with open(filepath, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for r in reader:
                rows.append({
                    "dataset_type": r.get("dataset_type", "").strip().lower(),
                    "new_metric_name": r.get("new_metric_name", "").strip(),
                    "expression": r.get("expression", "").strip(),
                    "description": r.get("description", "").strip(),
                })
    except Exception as e:
        print(f"Error loading computed series rows: {e}")
    return rows


def save_computed_series_rows(rows):
    """Writes formula rows back to computed_series.csv in APPDATA."""
    ensure_computed_series_file()
    filepath = COMPUTED_SERIES_APPDATA_PATH
    with open(filepath, mode="w", encoding="utf-8", newline="") as f:
        fieldnames = ["dataset_type", "new_metric_name", "expression", "description"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow({
                "dataset_type": r.get("dataset_type", "").strip().lower(),
                "new_metric_name": r.get("new_metric_name", "").strip(),
                "expression": r.get("expression", "").strip(),
                "description": r.get("description", "").strip(),
            })


def _show_parsing_error_dialog(err_msg: str, line_num: int):
    """Displays a warning dialog to the user if GUI is initialized."""
    err_key = (line_num, err_msg)
    if err_key in _reported_parsing_errors:
        return
    _reported_parsing_errors.add(err_key)

    try:
        from PyQt6.QtWidgets import QApplication, QMessageBox
        if QApplication.instance():
            QMessageBox.critical(
                None,
                "Computed Series Parsing Error",
                f"Failed to parse formula in '{COMPUTED_SERIES_FILENAME}' on line {line_num}:\n\n{err_msg}"
            )
    except Exception:
        pass


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
            print(f"[COMPUTED SERIES ERROR] Line {row_idx}: {details}")
            _show_parsing_error_dialog(details, row_idx)

    return definitions