import ast
import re

from src.parsing.computed_series import ALLOWED_UNARYOPS, ALLOWED_OPERATORS, ALLOWED_COMPARATORS, ALLOWED_BOOLOPS, \
	BUILTIN_FUNCS


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

    # Convert single '=' to '==' when not already part of '==', '!=', '<=', or '>='
    clean = re.sub(r'(?<![<>=!])=(?!=)', '==', clean)

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
