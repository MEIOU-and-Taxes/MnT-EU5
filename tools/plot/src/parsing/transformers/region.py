from src.parsing import stores
from src.parsing.computed_series import load_computed_series_definitions
from src.parsing.ast_engine import evaluate_expression
from src.parsing.definitions import POPULATION_HEADERS
from src.parsing.log_parser import parse_lines
from src.parsing.stores import region_locations_store, pop_cumulative_store, rt_cumulative_store, bt_cumulative_store, \
	gp_cumulative_store, mk_cumulative_store


def parse_data_regional_metrics(data: str = None):
	"""Combines Building Types, Goods Prices, Population, Road Coverages, and Regional Computed Series."""
	if stores._reg_cache is not None:
		return stores._reg_cache

	parse_data_region_locations(data)
	parse_data_population(data)
	parse_data_road_types(data)
	buildings = parse_data_building_types(data)
	prices = parse_data_goods_prices(data)

	rloc_map = region_locations_store
	computed_defs = [
		d for d in load_computed_series_definitions()
		if d["dataset_type"] in ("region", "regional", "regional_metric", "regional_stats")
	]

	transformed = []
	context_vars_by_moment_region = {}

	def get_locs(reg):
		return float(rloc_map.get(reg, 0.0))

	pop_lookup = {
		(m, reg): float(rec.get("population", 0.0))
		for (m, reg), rec in pop_cumulative_store.items()
	}

	# 1. Population & Regional SLV Metrics
	for (m, reg), rec in pop_cumulative_store.items():
		locs = get_locs(reg)
		p_val = float(rec.get("population", 0.0))
		v = context_vars_by_moment_region.setdefault(
			(m, reg),
			{"locations": locs, "population": p_val, "total_population": p_val}
		)
		v["population"] = p_val
		v["total_population"] = p_val

		for header in POPULATION_HEADERS:
			if header in rec:
				val = float(rec[header])
				transformed.append({
					"moment": m,
					"region": reg,
					"regional_metric": header,
					"metric": header,
					"statistic": header,
					"value": val,
					"locations": locs,
					"population": p_val,
					"total_population": p_val
				})
				# Make variables available to regional computed series formulas
				v[header] = val
				v[header.lower()] = val
				v[header.lower().replace(' ', '_')] = val

	# 2. Road Coverage
	for (m, reg, road_type), rec in rt_cumulative_store.items():
		locs = float(rec.get("locations", get_locs(reg)))
		cov = float(rec.get("coverage_percentage", 0.0))
		p_val = pop_lookup.get((m, reg), 0.0)
		transformed.append({
			"moment": m,
			"region": reg,
			"regional_metric": road_type,
			"metric": road_type,
			"road_type": road_type,
			"value": cov,
			"locations": locs,
			"population": p_val,
			"total_population": p_val
		})
		v = context_vars_by_moment_region.setdefault((m, reg), {"locations": locs, "population": p_val, "total_population": p_val})
		v[road_type] = cov
		v[road_type.lower().replace(' ', '_')] = cov

	# 3. Building Types
	for item in buildings:
		m = item["moment"]
		reg = item["region"]
		bld = item["building"]
		cnt = float(item["count"])
		locs = get_locs(reg)
		p_val = pop_lookup.get((m, reg), 0.0)
		transformed.append({
			"moment": m,
			"region": reg,
			"regional_metric": bld,
			"metric": bld,
			"building": bld,
			"value": cnt,
			"locations": locs,
			"population": p_val,
			"total_population": p_val
		})
		v = context_vars_by_moment_region.setdefault((m, reg), {"locations": locs, "population": p_val, "total_population": p_val})
		v[bld] = cnt
		v[bld.lower().replace(' ', '_')] = cnt

	# 4. Goods Prices
	for item in prices:
		m = item["moment"]
		reg = item["region"]
		raw_good = item["good"]
		good = raw_good if raw_good.lower().endswith(" price") else f"{raw_good} price"
		price = float(item["price"])
		locs = get_locs(reg)
		p_val = pop_lookup.get((m, reg), 0.0)
		transformed.append({
			"moment": m,
			"region": reg,
			"regional_metric": good,
			"metric": good,
			"good": good,
			"value": price,
			"locations": locs,
			"population": p_val,
			"total_population": p_val
		})
		v = context_vars_by_moment_region.setdefault((m, reg), {"locations": locs, "population": p_val, "total_population": p_val})
		v[good] = price
		v[good.lower().replace(' ', '_')] = price
		base_name = good[:-6] if good.lower().endswith(" price") else good
		v[base_name] = price
		v[base_name.lower().replace(' ', '_')] = price
		v[f"price_{base_name.lower().replace(' ', '_')}"] = price

	# 5. Regional Computed Series
	if computed_defs:
		for (m, reg), vars_dict in context_vars_by_moment_region.items():
			locs = vars_dict.get("locations", get_locs(reg))
			p_val = vars_dict.get("total_population", pop_lookup.get((m, reg), 0.0))
			for cdef in computed_defs:
				calc_val = evaluate_expression(
					cdef["expression"],
					vars_dict,
					precompiled=(cdef.get("clean_expr"), cdef.get("var_map"))
				)

				# Feed back into context:
				metric_name = cdef["metric_name"]
				vars_dict[metric_name] = calc_val
				vars_dict[metric_name.lower()] = calc_val
				vars_dict[metric_name.replace(' ', '_')] = calc_val
				vars_dict[metric_name.lower().replace(' ', '_')] = calc_val

				transformed.append({
					"moment": m,
					"region": reg,
					"regional_metric": cdef["metric_name"],
					"metric": cdef["metric_name"],
					"value": round(calc_val, 4),
					"locations": locs,
					"population": p_val,
					"total_population": p_val
				})

	stores._reg_cache = sorted(transformed, key=lambda x: (x["moment"], x["region"], x["regional_metric"]))
	return stores._reg_cache


def parse_data_region_locations(data: str = None):
	if stores._rloc_cache is not None:
		return stores._rloc_cache
	if not region_locations_store and data:
		parse_lines(data.splitlines())
	stores._rloc_cache = region_locations_store
	return stores._rloc_cache


def parse_data_building_types(data: str = None):
	if stores._bt_cache is not None:
		return stores._bt_cache
	if not bt_cumulative_store and data:
		parse_lines(data.splitlines())
	if not bt_cumulative_store:
		stores._bt_cache = []
		return stores._bt_cache

	all_moments = sorted(set(k[0] for k in bt_cumulative_store.keys()))
	all_buildings = sorted(set(k[2] for k in bt_cumulative_store.keys()))

	# Include all known regions so regions without a building have a count of 0
	all_regions = sorted(
		set(region_locations_store.keys()) |
		set(k[1] for k in pop_cumulative_store.keys()) |
		set(k[1] for k in bt_cumulative_store.keys()) |
		set(k[1] for k in rt_cumulative_store.keys())
	)
	if not all_regions:
		all_regions = sorted(set(k[1] for k in bt_cumulative_store.keys()))

	filled_data = []
	for m in all_moments:
		for bld in all_buildings:
			for reg in all_regions:
				filled_data.append({
					"moment": m,
					"building": bld,
					"count": bt_cumulative_store.get((m, reg, bld), 0),
					"region": reg
				})

	stores._bt_cache = filled_data
	return stores._bt_cache


def parse_data_goods_prices(data: str = None):
	if stores._gp_cache is not None:
		return stores._gp_cache
	if not gp_cumulative_store and data:
		parse_lines(data.splitlines())
	stores._gp_cache = sorted(gp_cumulative_store.values(), key=lambda x: (x["moment"], x["region"], x["good"]))
	return stores._gp_cache


def parse_data_population(data: str = None):
	if stores._pop_cache is not None:
		return stores._pop_cache
	if not pop_cumulative_store and data:
		parse_lines(data.splitlines())
	stores._pop_cache = sorted(pop_cumulative_store.values(), key=lambda x: (x["moment"], x["region"]))
	return stores._pop_cache


def parse_data_road_types(data: str = None):
	if stores._rt_cache is not None:
		return stores._rt_cache
	if not rt_cumulative_store and data:
		parse_lines(data.splitlines())
	stores._rt_cache = sorted(rt_cumulative_store.values(), key=lambda x: (x["moment"], x["region"], x["road_type"]))
	return stores._rt_cache


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
