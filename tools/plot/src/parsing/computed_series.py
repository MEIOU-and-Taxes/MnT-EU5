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

ALLOWED_COMPARATORS = {
    ast.Eq: op.eq,
    ast.NotEq: op.ne,
    ast.Lt: op.lt,
    ast.LtE: op.le,
    ast.Gt: op.gt,
    ast.GtE: op.ge,
}

ALLOWED_BOOLOPS = {
    ast.And: lambda vals: all(vals),
    ast.Or: lambda vals: any(vals),
}

ALLOWED_UNARYOPS = {
    ast.USub: op.neg,
    ast.UAdd: op.pos,
    ast.Not: lambda x: not bool(x),
}

BUILTIN_FUNCS = {
    'countif', 'if', 'iff', 'abs', 'min', 'max', 'round',
    'rate', 'relative_rate', 'rel_rate', 'acceleration', 'ratio', 'difference',
    'density_by_location', 'density_by_population'
}
BUILTIN_VARS = {'prev', 'true', 'false'}

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
    """Parses and checks that the expression contains only allowed arithmetic, comparison, and call nodes."""
    clean, var_map = prepare_expression(expr_str)
    parsed = ast.parse(clean, mode='eval')

    def check_node(n):
        if isinstance(n, ast.Expression):
            check_node(n.body)
        elif isinstance(n, ast.Constant):
            if not isinstance(n.value, (int, float, bool, str)):
                raise ValueError(f"Literal '{n.value}' is not a permitted constant")
        elif hasattr(ast, 'Num') and isinstance(n, ast.Num):
            pass
        elif isinstance(n, ast.Name):
            pass
        elif isinstance(n, ast.UnaryOp):
            if type(n.op) not in ALLOWED_UNARYOPS:
                raise ValueError(f"Unary operator '{type(n.op).__name__}' is not allowed")
            check_node(n.operand)
        elif isinstance(n, ast.BinOp):
            if type(n.op) not in ALLOWED_OPERATORS:
                raise ValueError(f"Binary operator '{type(n.op).__name__}' is not allowed")
            check_node(n.left)
            check_node(n.right)
        elif isinstance(n, ast.Compare):
            for op_elem in n.ops:
                if type(op_elem) not in ALLOWED_COMPARATORS:
                    raise ValueError(f"Comparator '{type(op_elem).__name__}' is not allowed")
            check_node(n.left)
            for c in n.comparators:
                check_node(c)
        elif isinstance(n, ast.BoolOp):
            if type(n.op) not in ALLOWED_BOOLOPS:
                raise ValueError(f"Logical operator '{type(n.op).__name__}' is not allowed")
            for val in n.values:
                check_node(val)
        elif isinstance(n, ast.IfExp):
            check_node(n.test)
            check_node(n.body)
            check_node(n.orelse)
        elif isinstance(n, ast.Call):
            if not isinstance(n.func, ast.Name) or n.func.id.lower() not in BUILTIN_FUNCS:
                f_name = getattr(n.func, 'id', str(n.func))
                raise ValueError(f"Function '{f_name}' is not supported. Permitted functions: {', '.join(sorted(BUILTIN_FUNCS))}")
            if n.func.id.lower() == 'countif' and len(n.args) not in (1, 2):
                raise ValueError("CountIf requires 1 or 2 arguments: CountIf(Condition, [Effect=1])")
            for a in n.args:
                check_node(a)
        else:
            raise ValueError(f"Syntax element '{type(n).__name__}' is not supported")

    check_node(parsed)
    return clean, var_map


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


def _resolve_var_val(var_name, variables):
    candidates = [
        var_name,
        var_name.lower(),
        var_name.replace('_', ' '),
        var_name.replace(' ', '_'),
        var_name.lower().replace('_', ' '),
        var_name.lower().replace(' ', '_')
    ]
    for cand in candidates:
        if cand in variables:
            return variables[cand]
    return 0.0


def _eval_node(node, variables, var_map=None, series_history=None, moment=None):
    """Recursively evaluates an AST node."""
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool):
            return node.value
        if isinstance(node.value, (int, float)):
            return float(node.value)
        return node.value
    elif hasattr(ast, 'Num') and isinstance(node, ast.Num):
        return float(node.n)
    elif isinstance(node, ast.Name):
        var_name = node.id
        if var_map and var_name in var_map:
            var_name = var_map[var_name]

        low = var_name.lower()
        if low == 'true':
            return True
        if low == 'false':
            return False
        if low == 'prev':
            return float(variables.get('PREV', variables.get('prev', 0.0)))

        val = _resolve_var_val(var_name, variables)
        if isinstance(val, (int, float, bool)):
            return val
        try:
            return float(val)
        except (ValueError, TypeError):
            return val

    elif isinstance(node, ast.UnaryOp):
        operand = _eval_node(node.operand, variables, var_map, series_history, moment)
        op_type = type(node.op)
        if op_type in ALLOWED_UNARYOPS:
            res = ALLOWED_UNARYOPS[op_type](operand)
            return float(res) if isinstance(res, bool) else res
        raise ValueError(f"Unsupported unary operator: {op_type}")

    elif isinstance(node, ast.BinOp):
        left = _eval_node(node.left, variables, var_map, series_history, moment)
        right = _eval_node(node.right, variables, var_map, series_history, moment)
        op_type = type(node.op)
        if op_type in ALLOWED_OPERATORS:
            if op_type in (ast.Div, ast.FloorDiv):
                if abs(right) < 1e-12:
                    return 0.0
            return ALLOWED_OPERATORS[op_type](left, right)
        raise ValueError(f"Unsupported binary operator: {op_type}")

    elif isinstance(node, ast.Compare):
        left = _eval_node(node.left, variables, var_map, series_history, moment)
        is_true = True
        for op_node, comp_node in zip(node.ops, node.comparators):
            comp_val = _eval_node(comp_node, variables, var_map, series_history, moment)
            cmp_func = ALLOWED_COMPARATORS[type(op_node)]
            try:
                if not cmp_func(left, comp_val):
                    is_true = False
                    break
            except TypeError:
                is_true = False
                break
            left = comp_val
        return is_true

    elif isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            for v_node in node.values:
                if not bool(_eval_node(v_node, variables, var_map, series_history, moment)):
                    return False
            return True
        elif isinstance(node.op, ast.Or):
            for v_node in node.values:
                if bool(_eval_node(v_node, variables, var_map, series_history, moment)):
                    return True
            return False
        return False

    elif isinstance(node, ast.IfExp):
        test_val = _eval_node(node.test, variables, var_map, series_history, moment)
        if bool(test_val):
            return _eval_node(node.body, variables, var_map, series_history, moment)
        return _eval_node(node.orelse, variables, var_map, series_history, moment)

    elif isinstance(node, ast.Call):
        func_name = node.func.id.lower()

        # Domain calculation functions across series history
        if func_name in ('rate', 'relative_rate', 'rel_rate', 'acceleration', 'ratio', 'difference', 'density_by_location', 'density_by_population'):
            arg_node = node.args[0]
            val = float(_eval_node(arg_node, variables, var_map, series_history, moment))

            if func_name == 'density_by_location':
                locs = float(_resolve_var_val('locations', variables) or _resolve_var_val('num_locations', variables))
                return (val / locs) if locs > 0 else 0.0

            if func_name == 'density_by_population':
                pop = float(_resolve_var_val('population', variables) or _resolve_var_val('total_population', variables))
                return ((val / pop) * 1_000_000.0) if pop > 0 else 0.0

            if series_history and moment is not None:
                moments_list = [m for m, ctx in series_history]
                if moment in moments_list:
                    idx = moments_list.index(moment)
                    if func_name == 'rate':
                        if idx >= 1:
                            prev_ctx = series_history[idx - 1][1]
                            prev_val = float(_eval_node(arg_node, prev_ctx, var_map, series_history, series_history[idx - 1][0]))
                            # Require both current and previous data points to be present
                            if abs(val) < 1e-12 and abs(prev_val) < 1e-12:
                                return 0.0
                            return val - prev_val
                        return 0.0
                    elif func_name in ('relative_rate', 'rel_rate'):
                        if idx >= 1:
                            prev_ctx = series_history[idx - 1][1]
                            prev_val = float(_eval_node(arg_node, prev_ctx, var_map, series_history, series_history[idx - 1][0]))
                            # If current value is 0 while previous was non-zero, check if metric is actually present in context
                            # to avoid false -100% drops caused by asynchronous log writes
                            if abs(val) < 1e-12:
                                return 0.0
                            return (((val - prev_val) / prev_val) * 100.0) if abs(prev_val) > 1e-12 else 0.0
                        return 0.0
                    elif func_name == 'acceleration':
                        if idx >= 2:
                            prev1 = float(_eval_node(arg_node, series_history[idx - 1][1], var_map, series_history, series_history[idx - 1][0]))
                            prev2 = float(_eval_node(arg_node, series_history[idx - 2][1], var_map, series_history, series_history[idx - 2][0]))
                            if abs(val) < 1e-12 or abs(prev1) < 1e-12 or abs(prev2) < 1e-12:
                                return 0.0
                            return (val - prev1) - (prev1 - prev2)
                        return 0.0
                    elif func_name == 'difference':
                        base_val = float(_eval_node(arg_node, series_history[0][1], var_map, series_history, series_history[0][0]))
                        if abs(val) < 1e-12 or abs(base_val) < 1e-12:
                            return 0.0
                        return val - base_val
                    elif func_name == 'ratio':
                        base_val = float(
                            _eval_node(arg_node, series_history[0][1], var_map, series_history, series_history[0][0]))
                        if abs(val) < 1e-12 or abs(base_val) < 1e-12:
                            return 0.0
                        return ((val / base_val) - 1.0) * 100.0
            return 0.0

        if func_name == 'countif':
            if len(node.args) == 0:
                return 0.0
            cond_val = bool(_eval_node(node.args[0], variables, var_map, series_history, moment))
            effect_val = _eval_node(node.args[1], variables, var_map, series_history, moment) if len(node.args) > 1 else 1.0
            return float(effect_val) if cond_val else 0.0
        elif func_name in ('if', 'iff'):
            if len(node.args) < 2:
                return 0.0
            cond_val = bool(_eval_node(node.args[0], variables, var_map, series_history, moment))
            if cond_val:
                return _eval_node(node.args[1], variables, var_map, series_history, moment)
            return _eval_node(node.args[2], variables, var_map, series_history, moment) if len(node.args) > 2 else 0.0
        elif func_name == 'abs':
            return abs(float(_eval_node(node.args[0], variables, var_map, series_history, moment)))
        elif func_name == 'min':
            return min(float(_eval_node(a, variables, var_map, series_history, moment)) for a in node.args)
        elif func_name == 'max':
            return max(float(_eval_node(a, variables, var_map, series_history, moment)) for a in node.args)
        elif func_name == 'round':
            val = float(_eval_node(node.args[0], variables, var_map, series_history, moment))
            ndigits = int(_eval_node(node.args[1], variables, var_map, series_history, moment)) if len(node.args) > 1 else 0
            return round(val, ndigits)
        raise ValueError(f"Unsupported function call: {func_name}")

    else:
        raise ValueError(f"Unsupported AST node expression: {type(node)}")


def evaluate_expression(expr_str: str, variables: dict, precompiled=None) -> float:
    """Evaluates a math formula string safely using an AST."""
    if not expr_str or not expr_str.strip():
        return 0.0
    try:
        clean_expr, var_map = precompiled if precompiled else prepare_expression(expr_str)
        parsed = ast.parse(clean_expr, mode='eval')
        res = _eval_node(parsed.body, variables, var_map)
        if isinstance(res, bool):
            return 1.0 if res else 0.0
        return float(res) if res is not None else 0.0
    except Exception:
        return 0.0


def evaluate_condition(condition_str: str, variables: dict, precompiled=None, series_history=None, moment=None) -> bool:
    if not condition_str or not condition_str.strip():
        return False
    try:
        clean_expr, var_map = precompiled if precompiled else prepare_expression(condition_str)
        parsed = ast.parse(clean_expr, mode='eval')
        res = _eval_node(parsed.body, variables, var_map, series_history=series_history, moment=moment)
        return bool(res)
    except Exception:
        return False


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
                    call_val = _eval_node(node, variables, var_map, series_history, moment)
                    val_str = f"{call_val:.2f}%" if "relative" in f_name or "rel_" in f_name or "ratio" in f_name else format_metric_3digits(call_val)
                    eval_pairs.append(f"{call_label}={val_str}")
                except Exception:
                    pass

        # Also extract raw metrics
        used_vars = extract_variable_names(clean_expr, var_map)
        for v in used_vars:
            val = _resolve_var_val(v, variables)
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