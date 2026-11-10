from src.parsing import stores
from src.parsing.computed_series import load_computed_series_definitions
from src.parsing.ast_engine import evaluate_expression
from src.parsing.transformers.region import parse_data_markets


def parse_data_market_metrics(data: str = None):
	"""Combines Market Statistics with user-defined market computed series formulas."""
	if stores._mkm_cache is not None:
		return stores._mkm_cache

	raw_markets = parse_data_markets(data)

	computed_defs = [
		d for d in load_computed_series_definitions()
		if d["dataset_type"] in ("market", "markets", "market_metric", "market_stats")
	]

	if not computed_defs:
		stores._mkm_cache = raw_markets
		return stores._mkm_cache

	transformed = list(raw_markets)
	context_by_moment_market = {}

	for item in raw_markets:
		m = item["moment"]
		mkt = item["market"]
		stat = item["statistic"]
		val = float(item.get("value", 0.0))
		locs = float(item.get("locations", 0.0))
		pop = float(item.get("population", 0.0))

		ctx = context_by_moment_market.setdefault(
			(m, mkt),
			{"locations": locs, "population": pop, "total_population": pop}
		)
		if locs > 0:
			ctx["locations"] = locs
		if pop > 0:
			ctx["population"] = pop
			ctx["total_population"] = pop

		ctx[stat] = val
		ctx[stat.lower()] = val
		ctx[stat.replace(' ', '_')] = val
		ctx[stat.lower().replace(' ', '_')] = val

	for (m, mkt), ctx in context_by_moment_market.items():
		locs = ctx.get("locations", 0.0)
		pop = ctx.get("population", 0.0)
		for cdef in computed_defs:
			calc_val = evaluate_expression(
				cdef["expression"],
				ctx,
				precompiled=(cdef.get("clean_expr"), cdef.get("var_map"))
			)

			metric_name = cdef["metric_name"]
			ctx[metric_name] = calc_val
			ctx[metric_name.lower()] = calc_val
			ctx[metric_name.replace(' ', '_')] = calc_val
			ctx[metric_name.lower().replace(' ', '_')] = calc_val

			transformed.append({
				"moment": m,
				"region": mkt,
				"market": mkt,
				"statistic": metric_name,
				"metric": metric_name,
				"value": round(calc_val, 4),
				"locations": locs,
				"population": pop,
				"total_population": pop
			})

	stores._mkm_cache = sorted(transformed, key=lambda x: (x["moment"], x["region"], x["statistic"]))
	return stores._mkm_cache
