import src.parsing
from src.parsing.computed_series import load_computed_series_definitions, evaluate_expression
from src.parsing.definitions import EXCLUDED_KEYS_COUNTRY, CREDIT_HEADERS, POPULATION_HEADERS
from src.parsing.log_parser import parse_data_countries, parse_data_credit_raw, parse_data_region_locations, \
	parse_data_population, parse_data_road_types, parse_data_building_types, parse_data_goods_prices
from src.parsing.stores import cr_cumulative_store, tg_cumulative_store, region_locations_store, pop_cumulative_store, \
	rt_cumulative_store


def parse_data_country_metrics(data: str = None):
	"""Combines Country Metrics and Credit Statistics into one unified dataset with computed metrics."""
	if src.parsing.stores._cm_cache is not None:
		return src.parsing.stores._cm_cache

	countries = parse_data_countries(data)
	parse_data_credit_raw(data)

	computed_defs = [
		d for d in load_computed_series_definitions()
		if d["dataset_type"] in ("country", "country_metric", "country_stats", "credit", "credit_metric", "credit_stats")
	]

	transformed = []
	processed_combos = set()

	for r in countries:
		locs_val = r.get("locations") or r.get("num_locations") or 0
		try: country_locations = float(locs_val)
		except (ValueError, TypeError): country_locations = 0.0

		if country_locations <= 0:
			continue

		pop_val = r.get("Population", 0)
		try: country_pop = float(pop_val)
		except (ValueError, TypeError): country_pop = 0.0

		year = int(r["year"]) if r.get("year") else 0
		tag = r.get("tag", "")
		name = r.get("name", "")
		label = f"{name} ({tag})" if name and name != tag else tag
		processed_combos.add((year, tag))

		# Standard Country metrics
		for k, v in r.items():
			if k not in EXCLUDED_KEYS_COUNTRY and isinstance(v, (int, float)):
				transformed.append({
					"moment": year,
					"region": label,
					"country": label,
					"tag": tag,
					"metric": k,
					"country_metric": k,
					"value": float(v),
					"locations": country_locations,
					"population": country_pop,
					"total_population": country_pop
				})

		# Credit metrics for this country and year
		credit_rec = cr_cumulative_store.get((year, tag), {})
		for header in CREDIT_HEADERS:
			val = credit_rec.get(header)
			if isinstance(val, (int, float)):
				transformed.append({
					"moment": year,
					"region": label,
					"country": label,
					"tag": tag,
					"credit_metric": header,
					"metric": header,
					"country_metric": header,
					"value": float(val),
					"locations": country_locations,
					"population": country_pop,
					"total_population": country_pop
				})

		# Combined variables for formulas
		combined_vars = {}
		combined_vars.update(r)
		combined_vars.update(credit_rec)

		for cdef in computed_defs:
			calc_val = evaluate_expression(
				cdef["expression"],
				combined_vars,
				precompiled=(cdef.get("clean_expr"), cdef.get("var_map"))
			)

			metric_name = cdef["metric_name"]
			combined_vars[metric_name] = calc_val
			combined_vars[metric_name.lower()] = calc_val
			combined_vars[metric_name.replace(' ', '_')] = calc_val
			combined_vars[metric_name.lower().replace(' ', '_')] = calc_val

			transformed.append({
				"moment": year,
				"region": label,
				"country": label,
				"tag": tag,
				"metric": cdef["metric_name"],
				"country_metric": cdef["metric_name"],
				"credit_metric": cdef["metric_name"],
				"value": round(calc_val, 4),
				"locations": country_locations,
				"population": country_pop,
				"total_population": country_pop
			})

	# Credit records that had no corresponding country record
	for (moment, tag), record in cr_cumulative_store.items():
		if (moment, tag) in processed_combos:
			continue
		country_rec = tg_cumulative_store.get((moment, tag))
		name = country_rec.get("name", "") if country_rec else ""
		label = f"{name} ({tag})" if name and name != tag else tag

		locs = 0.0
		pop = 0.0
		if country_rec:
			loc_val = country_rec.get("locations") or country_rec.get("num_locations") or 0
			try: locs = float(loc_val)
			except (ValueError, TypeError): locs = 0.0
			p_val = country_rec.get("Population", 0)
			try: pop = float(p_val)
			except (ValueError, TypeError): pop = 0.0

		for header in CREDIT_HEADERS:
			val = record.get(header)
			if isinstance(val, (int, float)):
				transformed.append({
					"moment": moment,
					"region": label,
					"country": label,
					"tag": tag,
					"credit_metric": header,
					"metric": header,
					"country_metric": header,
					"value": float(val),
					"locations": locs,
					"population": pop,
					"total_population": pop
				})

	src.parsing.stores._cm_cache = sorted(transformed, key=lambda x: (x["moment"], x["country"], x["country_metric"]))
	return src.parsing.stores._cm_cache


def parse_data_regional_metrics(data: str = None):
	"""Combines Building Types, Goods Prices, Population, Road Coverages, and Regional Computed Series."""
	if src.parsing.stores._reg_cache is not None:
		return src.parsing.stores._reg_cache

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

	src.parsing.stores._reg_cache = sorted(transformed, key=lambda x: (x["moment"], x["region"], x["regional_metric"]))
	return src.parsing.stores._reg_cache
