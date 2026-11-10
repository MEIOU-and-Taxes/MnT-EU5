from src.parsing import stores
from src.parsing.computed_series import load_computed_series_definitions
from src.parsing.ast_engine import evaluate_expression
from src.parsing.log_parser import parse_lines
from src.parsing.stores import mk_cumulative_store


def parse_data_markets(data: str = None):
	if stores._mk_cache is not None:
		return stores._mk_cache
	if not mk_cumulative_store and data:
		parse_lines(data.splitlines())

	loc_lookup = {}
	pop_lookup = {}
	for (m, reg, stat), record in mk_cumulative_store.items():
		if stat == "Locations":
			loc_lookup[(m, reg)] = record.get("value", 0.0)
		elif stat == "Population":
			pop_lookup[(m, reg)] = record.get("value", 0.0)

	for (m, reg, _), record in mk_cumulative_store.items():
		if not record.get("locations") and (m, reg) in loc_lookup:
			record["locations"] = loc_lookup[(m, reg)]
		if not record.get("population") and (m, reg) in pop_lookup:
			record["population"] = pop_lookup[(m, reg)]

	stores._mk_cache = sorted(mk_cumulative_store.values(), key=lambda x: (x["moment"], x["region"], x["statistic"]))
	return stores._mk_cache


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
			{"locations": locs, "population": pop, "total_population": pop, "moment": m, "market": mkt}
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

	# Group chronologically per market
	market_histories = {}
	for (m, mkt) in sorted(context_by_moment_market.keys(), key=lambda k: (k[1], k[0])):
		market_histories.setdefault(mkt, []).append((m, context_by_moment_market[(m, mkt)]))

	prev_values_by_market = {}  # (metric_name, mkt) -> float

	for mkt, history in market_histories.items():
		for m, ctx in history:
			locs = ctx.get("locations", 0.0)
			pop = ctx.get("population", 0.0)

			for cdef in computed_defs:
				metric_name = cdef["metric_name"]
				prev_val = prev_values_by_market.get((metric_name, mkt), 0.0)
				curr_val = ctx.get(metric_name, ctx.get('value', 0.0))
				try: curr_val = float(curr_val)
				except (ValueError, TypeError): curr_val = 0.0

				ctx['PREV'] = prev_val
				ctx['prev'] = prev_val
				ctx['CURR'] = curr_val
				ctx['curr'] = curr_val

				calc_val = evaluate_expression(
					cdef["expression"],
					ctx,
					precompiled=(cdef.get("clean_expr"), cdef.get("var_map")),
					series_history=history,
					moment=m
				)

				prev_values_by_market[(metric_name, mkt)] = calc_val
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