from src.parsing import stores
from src.parsing.computed_series import load_computed_series_definitions
from src.parsing.ast_engine import evaluate_expression
from src.parsing.definitions import EXCLUDED_KEYS_COUNTRY, CREDIT_HEADERS
from src.parsing.log_parser import parse_lines
from src.parsing.stores import tg_cumulative_store, cr_cumulative_store
from src.parsing.transformers import _check_and_notify_duplicate_names


def parse_data_countries(data: str = None):
	if stores._tg_cache is not None:
		return stores._tg_cache
	if not tg_cumulative_store and data:
		parse_lines(data.splitlines())
	stores._tg_cache = sorted(tg_cumulative_store.values(), key=lambda r: int(r.get("year", 0)))
	return stores._tg_cache


def parse_data_credit_raw(data: str = None):
	if stores._cr_cache is not None:
		return stores._cr_cache
	if not cr_cumulative_store and data:
		parse_lines(data.splitlines())
	stores._cr_cache = sorted(cr_cumulative_store.values(), key=lambda x: (x["moment"], x["tag"]))
	return stores._cr_cache


def parse_data_country_metrics(data: str = None):
	"""Combines Country Metrics and Credit Statistics into one unified dataset with computed metrics."""
	if stores._cm_cache is not None:
		return stores._cm_cache

	countries = parse_data_countries(data)
	parse_data_credit_raw(data)

	# Check for countries sharing the exact same name with different tags
	name_to_tags = {}
	for r in countries:
		tag = r.get("tag", "")
		name = r.get("name", "")
		if name and tag:
			name_to_tags.setdefault(name, set()).add(tag)
	_check_and_notify_duplicate_names("country", name_to_tags)

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
		# Distinct naming if identical names or name != tag
		label = f"{name} ({tag})" if name and name != tag else (name or tag)
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
		label = f"{name} ({tag})" if name and name != tag else (name or tag)

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

	stores._cm_cache = sorted(transformed, key=lambda x: (x["moment"], x["country"], x["country_metric"]))
	return stores._cm_cache
