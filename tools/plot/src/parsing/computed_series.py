"""Module to calculate derived metrics from mathematical formulas specified in CSV."""
import ast
import csv
import operator as op
import os
import shutil

from src.constants import APPDATA_DIR

COMPUTED_SERIES_FILENAME = "computed_series.csv"
COMPUTED_SERIES_APPDATA_PATH = os.path.join(APPDATA_DIR, COMPUTED_SERIES_FILENAME)

DEFAULT_COMPUTED_SERIES_CSV = """dataset_type,new_metric_name,expression,description
country,Debt/Income,total_debt / income,Total debt divided by annual/monthly income
country,Navy/Army Ratio,navy_size / army_size,Ratio of navy size to army size
country,Credit Supply/Demand,Supply / Demand,Credit supply to demand ratio
region,Population Density,total_population / locations,Average population per location
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

def _eval_node(node, variables):
    """Safely evaluates an AST expression node against variable values."""
    if isinstance(node, ast.Constant):  # Python >= 3.8 numeric literals
        return float(node.value)
    elif isinstance(node, ast.Name):
        val = variables.get(node.id, variables.get(node.id.lower(), 0.0))
        try:
            return float(val) if val is not None else 0.0
        except (ValueError, TypeError):
            return 0.0
    elif isinstance(node, ast.UnaryOp):
        operand = _eval_node(node.operand, variables)
        op_type = type(node.op)
        if op_type in ALLOWED_OPERATORS:
            return ALLOWED_OPERATORS[op_type](operand)
        raise ValueError(f"Unsupported unary operator: {op_type}")
    elif isinstance(node, ast.BinOp):
        left = _eval_node(node.left, variables)
        right = _eval_node(node.right, variables)
        op_type = type(node.op)
        if op_type in ALLOWED_OPERATORS:
            if op_type in (ast.Div, ast.FloorDiv):
                if abs(right) < 1e-12:
                    return 0.0
            return ALLOWED_OPERATORS[op_type](left, right)
        raise ValueError(f"Unsupported binary operator: {op_type}")
    else:
        raise ValueError(f"Unsupported AST node expression: {type(node)}")

def evaluate_expression(expr_str: str, variables: dict) -> float:
    """Evaluates a math formula string safely using an AST."""
    if not expr_str or not expr_str.strip():
        return 0.0
    # Replace caret with power operator if used
    clean_expr = expr_str.strip().replace('^', '**')
    try:
        parsed = ast.parse(clean_expr, mode='eval')
        res = _eval_node(parsed.body, variables)
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

def load_computed_series_definitions():
    """Reads configured formulas from computed_series.csv."""
    ensure_computed_series_file()
    definitions = []
    filepath = COMPUTED_SERIES_APPDATA_PATH if os.path.exists(COMPUTED_SERIES_APPDATA_PATH) else COMPUTED_SERIES_FILENAME
    if not os.path.exists(filepath):
        return definitions

    try:
        with open(filepath, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                d_type = row.get("dataset_type", "").strip().lower()
                name = row.get("new_metric_name", "").strip()
                expr = row.get("expression", "").strip()
                if d_type and name and expr:
                    definitions.append({
                        "dataset_type": d_type,
                        "metric_name": name,
                        "expression": expr,
                        "description": row.get("description", "").strip()
                    })
    except Exception as e:
        print(f"Failed to read computed series config: {e}")
    return definitions