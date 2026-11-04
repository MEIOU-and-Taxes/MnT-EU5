import os
import re

from src.parsing.computed_series import load_computed_series_definitions, evaluate_expression
from src.parsing.definitions import COUNTRY_FIRST_HEADERS, SOCIETAL_VALUE_NAMES, STRING_COLUMNS, EXCLUDED_KEYS_COUNTRY, \
	market_stats, CREDIT_HEADERS
from src.parsing.numeric_utils import parse_dynamic_numeric_value

# Column count mismatch callback (hooked by UI)
_column_mismatch_callback = None

def set_column_mismatch_callback(cb):
	global _column_mismatch_callback
	_column_mismatch_callback = cb

# Caches
_bt_cache = None
_gp_cache = None
_pop_cache = None
_mk_cache = None
_rt_cache = None
_tg_cache = None
_cm_cache = None
_rloc_cache = None
_cr_cache = None
_crm_cache = None
_reg_cache = None

# Cache signatures of files: filepath -> (mtime, size)
parsed_file_signatures = {}

# Cumulative stores across log overwrites / reloads
tg_cumulative_store = {}
bt_cumulative_store = {}
gp_cumulative_store = {}
pop_cumulative_store = {}
rt_cumulative_store = {}
mk_cumulative_store = {}
region_locations_store = {}
cr_cumulative_store = {}

_mismatch_count = 0
_valid_tg_count = 0

def clear_all_caches():
	global _bt_cache, _gp_cache, _pop_cache, _mk_cache, _rt_cache, _tg_cache, _cm_cache, _rloc_cache, _cr_cache, _crm_cache, _reg_cache
	_bt_cache = _gp_cache = _pop_cache = _mk_cache = _rt_cache = _tg_cache = _cm_cache = _rloc_cache = _cr_cache = _crm_cache = _reg_cache = None

def reset_cumulative_history():
	global _mismatch_count, _valid_tg_count
	parsed_file_signatures.clear()
	tg_cumulative_store.clear()
	bt_cumulative_store.clear()
	gp_cumulative_store.clear()
	pop_cumulative_store.clear()
	rt_cumulative_store.clear()
	mk_cumulative_store.clear()
	region_locations_store.clear()
	cr_cumulative_store.clear()
	clear_all_caches()


def should_parse_file(filepath: str) -> bool:
	if not os.path.exists(filepath):
		return False
	try:
		s = os.stat(filepath)
		sig = (s.st_mtime, s.st_size)
		return parsed_file_signatures.get(filepath) != sig
	except OSError:
		return False

def parse_log_file(filepath: str):
	"""Streams a log file line by line without holding entire multi-hundred MBs in memory."""
	if not os.path.exists(filepath):
		return
	try:
		s = os.stat(filepath)
		with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
			parse_lines(f)
		parsed_file_signatures[filepath] = (s.st_mtime, s.st_size)
	except (IOError, PermissionError) as e:
		print(f"Log read warning for {filepath}: {e}")

def parse_lines(line_iterable):
	"""Unified single-pass parser across stream lines."""
	current_tg_record = None
	lines_after_tg = 99
	pending_chunks = []
	warning_printed = False

	def commit_tg(rec):
		if rec is not None:
			for k, val in rec.items():
				if k not in STRING_COLUMNS:
					rec[k] = parse_dynamic_numeric_value(val)
			yr = rec.get("year")
			tag = rec.get("tag")
			if yr and tag:
				tg_cumulative_store[(yr, tag)] = rec

	for line in line_iterable:
		if '\x00' in line:
			line = line.replace('\x00', '')

		# --- TG handling ---
		if '::TG' in line:
			values = None
			if '::TG1::' in line:
				commit_tg(current_tg_record)
				current_tg_record = None
				pending_chunks = [line.split('::TG1::', 1)[1].strip()]
				lines_after_tg = 99
				continue
			elif '::TG2::' in line and pending_chunks:
				pending_chunks.append(line.split('::TG2::', 1)[1].strip())
				lines_after_tg = 99
				continue
			elif '::TG3::' in line and len(pending_chunks) == 2:
				pending_chunks.append(line.split('::TG3::', 1)[1].strip())
				lines_after_tg = 99
				continue
			elif '::TG4::' in line and len(pending_chunks) == 3:
				pending_chunks.append(line.split('::TG4::', 1)[1].strip())
				values = ":".join(pending_chunks).split(':')
				pending_chunks = []
			elif '::TG::' in line:
				commit_tg(current_tg_record)
				current_tg_record = None
				values = line.split('::TG::', 1)[1].strip().split(':')

			if values is not None:
				global _mismatch_count, _valid_tg_count
				if len(values) != len(COUNTRY_FIRST_HEADERS):
					_mismatch_count += 1
					report = _format_mismatch_report(values, COUNTRY_FIRST_HEADERS)
					print(report)

					# Only notify UI to prompt for log deletion if systematic format change
					# (e.g. >5 consecutive mismatches without valid records, or >15 total)
					if (_valid_tg_count == 0 and _mismatch_count >= 5) or _mismatch_count > 15:
						if _column_mismatch_callback and not warning_printed:
							warning_printed = True
							_column_mismatch_callback(len(values), len(COUNTRY_FIRST_HEADERS))
					
					current_tg_record = None
					lines_after_tg = 99
					continue

				_valid_tg_count += 1
				lines_after_tg = 0
				current_tg_record = dict(zip(COUNTRY_FIRST_HEADERS, values))
			continue

		if lines_after_tg <= 15:
			if current_tg_record is not None:
				m = re.search(r"(-?\d+(?:\.\d+)?)$", line.strip())
				if m:
					current_tg_record[SOCIETAL_VALUE_NAMES[lines_after_tg]] = float(m.group(1))
					if lines_after_tg == 15:
						commit_tg(current_tg_record)
						current_tg_record = None
			lines_after_tg += 1
			continue

		# --- Other tags ---
		if '::BT:' in line:
			part = line.split('::BT:', 1)[1]
			p = part.split(':')
			if len(p) >= 4:
				try:
					bt_cumulative_store[(int(p[0]), p[3].strip(), p[1].strip())] = int(p[2])
				except (ValueError, TypeError):
					pass
		elif '::GP::' in line:
			part = line.split('::GP::', 1)[1]
			p = part.split(':')
			if len(p) >= 4 and 'Ocean' not in p[2]:
				try:
					moment = int(p[0])
					raw_good = p[1].strip()
					good_name = raw_good if raw_good.lower().endswith(" price") else f"{raw_good} price"
					gp_cumulative_store[(moment, p[2].strip(), good_name)] = {
						"moment": moment, "good": good_name, "region": p[2].strip(), "price": float(p[3].strip())
					}
				except (ValueError, TypeError):
					pass
		elif '::POP::' in line:
			part = line.split('::POP::', 1)[1]
			p = part.split(':')
			if len(p) >= 3:
				try:
					moment = int(p[0])
					pop_cumulative_store[(moment, p[1].strip())] = {
						"moment": moment, "region": p[1].strip(),
						"statistic": "Total Population",
						"population": parse_dynamic_numeric_value(p[2].strip())
					}
				except (ValueError, TypeError):
					pass
		elif '::RT::' in line:
			part = line.split('::RT::', 1)[1]
			p = part.split(':')
			if len(p) >= 5:
				try:
					moment = int(p[0])
					locs = int(p[3])
					locs_w_road = int(p[4])
					rt_cumulative_store[(moment, p[1].strip(), p[2].strip())] = {
						"moment": moment, "region": p[1].strip(), "road_type": p[2].strip(),
						"locations": locs, "locations_with_road": locs_w_road,
						"coverage_percentage": (locs_w_road / locs * 100) if locs > 0 else 0
					}
				except (ValueError, TypeError):
					pass
		elif '::MK::' in line:
			part = line.split('::MK::', 1)[1]
			p = part.split(':', 2)
			if len(p) >= 3:
				try:
					moment = int(p[0])
					market_name = p[1].strip()
					raw_vals = p[2].strip().split(':')
					vals = []
					for v in raw_vals:
						try: vals.append(float(v))
						except (ValueError, TypeError): pass
					stat_map = dict(zip(market_stats, vals))
					loc_count = float(stat_map.get("Locations", 0.0))
					pop_count = float(stat_map.get("Population", 0.0))
					for name, v in stat_map.items():
						mk_cumulative_store[(moment, market_name, name)] = {
							"moment": moment, "region": market_name, "market": market_name,
							"statistic": name, "value": v, 
							"locations": loc_count,
							"population": pop_count 
						}
				except (ValueError, TypeError):
					pass
		elif '::CR::' in line:
			part = line.split('::CR::', 1)[1]
			p = part.split(':', 2)
			if len(p) >= 3:
				try:
					moment = int(p[0])
					tag = p[1].strip()
					raw_vals = p[2].strip().split(':')
					record = {"moment": moment, "tag": tag, "country": tag}
					for name, val_str in zip(CREDIT_HEADERS, raw_vals):
						record[name] = parse_dynamic_numeric_value(val_str)
					cr_cumulative_store[(moment, tag)] = record
				except (ValueError, TypeError):
					pass
		elif '::RLOC::' in line:
			part = line.split('::RLOC::', 1)[1]
			p = part.split(':')
			if len(p) >= 2:
				try:
					region_locations_store[p[0].strip()] = int(float(p[1].strip().replace(',', '')))
				except (ValueError, TypeError):
					pass

	commit_tg(current_tg_record)

def parse_data_region_locations(data: str = None):
	global _rloc_cache
	if _rloc_cache is not None:
		return _rloc_cache
	if not region_locations_store and data:
		parse_lines(data.splitlines())
	_rloc_cache = region_locations_store
	return _rloc_cache

def get_region_locations():
	return region_locations_store

def parse_data_countries(data: str = None):
	global _tg_cache
	if _tg_cache is not None:
		return _tg_cache
	if not tg_cumulative_store and data:
		parse_lines(data.splitlines())
	_tg_cache = sorted(tg_cumulative_store.values(), key=lambda r: int(r.get("year", 0)))
	return _tg_cache

def parse_data_building_types(data: str = None):
	global _bt_cache
	if _bt_cache is not None:
		return _bt_cache
	if not bt_cumulative_store and data:
		parse_lines(data.splitlines())
	if not bt_cumulative_store:
		_bt_cache = []
		return _bt_cache

	all_moments = sorted(set(k[0] for k in bt_cumulative_store.keys()))
	# Limit to active (region, building) pairs that actually exist in the game
	active_pairs = sorted(set((k[1], k[2]) for k in bt_cumulative_store.keys()))

	filled_data = []
	for m in all_moments:
		for reg, bld in active_pairs:
			filled_data.append({
				"moment": m,
				"building": bld,
				"count": bt_cumulative_store.get((m, reg, bld), 0),
				"region": reg
			})

	_bt_cache = filled_data
	return _bt_cache

def parse_data_goods_prices(data: str = None):
	global _gp_cache
	if _gp_cache is not None:
		return _gp_cache
	if not gp_cumulative_store and data:
		parse_lines(data.splitlines())
	_gp_cache = sorted(gp_cumulative_store.values(), key=lambda x: (x["moment"], x["region"], x["good"]))
	return _gp_cache

def parse_data_population(data: str = None):
	global _pop_cache
	if _pop_cache is not None:
		return _pop_cache
	if not pop_cumulative_store and data:
		parse_lines(data.splitlines())
	_pop_cache = sorted(pop_cumulative_store.values(), key=lambda x: (x["moment"], x["region"]))
	return _pop_cache

def parse_data_road_types(data: str = None):
	global _rt_cache
	if _rt_cache is not None:
		return _rt_cache
	if not rt_cumulative_store and data:
		parse_lines(data.splitlines())
	_rt_cache = sorted(rt_cumulative_store.values(), key=lambda x: (x["moment"], x["region"], x["road_type"]))
	return _rt_cache

def parse_data_markets(data: str = None):
	global _mk_cache
	if _mk_cache is not None:
		return _mk_cache
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

	_mk_cache = sorted(mk_cumulative_store.values(), key=lambda x: (x["moment"], x["region"], x["statistic"]))
	return _mk_cache

def parse_data_credit_raw(data: str = None):
	global _cr_cache
	if _cr_cache is not None:
		return _cr_cache
	if not cr_cumulative_store and data:
		parse_lines(data.splitlines())
	_cr_cache = sorted(cr_cumulative_store.values(), key=lambda x: (x["moment"], x["tag"]))
	return _cr_cache

def parse_data_country_metrics(data: str = None):
	"""Combines Country Metrics and Credit Statistics into one unified dataset with computed metrics."""
	global _cm_cache
	if _cm_cache is not None:
		return _cm_cache

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

	_cm_cache = sorted(transformed, key=lambda x: (x["moment"], x["country"], x["country_metric"]))
	return _cm_cache

def parse_data_regional_metrics(data: str = None):
	"""Combines Building Types, Goods Prices, Population, Road Coverages, and Regional Computed Series."""
	global _reg_cache
	if _reg_cache is not None:
		return _reg_cache

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

	# 1. Total Population
	for (m, reg), rec in pop_cumulative_store.items():
		locs = get_locs(reg)
		p_val = float(rec.get("population", 0.0))
		transformed.append({
			"moment": m,
			"region": reg,
			"regional_metric": "Total Population",
			"metric": "Total Population",
			"statistic": "Total Population",
			"value": p_val,
			"locations": locs,
			"population": p_val,
			"total_population": p_val
		})
		v = context_vars_by_moment_region.setdefault((m, reg), {"locations": locs, "population": p_val, "total_population": p_val})
		v["population"] = p_val
		v["total_population"] = p_val

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

	_reg_cache = sorted(transformed, key=lambda x: (x["moment"], x["region"], x["regional_metric"]))
	return _reg_cache

def _format_mismatch_report(values, expected_headers):
	"""Generates a detailed diagnostic report when a column count mismatch occurs."""
	got = len(values)
	exp = len(expected_headers)
	yr = values[0] if got > 0 else "Unknown"
	tag = values[1] if got > 1 else "Unknown"
	country_name = values[2] if got > 2 else "Unknown"

	lines = [
		"=" * 85,
		f"[LOG PARSER WARNING] Country Record Column Mismatch!",
		f"  Received: {got} columns | Expected: {exp} columns",
		f"  Context:  Year = '{yr}', Tag = '{tag}', Name = '{country_name}'",
		"-" * 85
	]

	if got < exp:
		cutoff_header = expected_headers[got] if got < exp else "N/A"
		lines.append(f"  Reason: Line was truncated or torn by concurrent thread logging.")
		lines.append(f"  First missing column: index {got} ('{cutoff_header}')")
		lines.append(f"  Last 5 received values: {values[-5:]}")
		lines.append(f"\n  Columns around cutoff (index {max(0, got - 3)} to {min(exp - 1, got + 3)}):")
		for i in range(max(0, got - 3), min(exp, got + 4)):
			status = "--> [MISSING]" if i >= got else "	[OK]"
			val_preview = f"'{values[i]}'" if i < got else "<not present>"
			lines.append(f"	{status} index {i:<3} | {expected_headers[i]:<32} = {val_preview}")
	else:
		lines.append(f"  Reason: Line had {got - exp} unexpected extra values.")
		lines.append(f"  Extra values: {values[exp:]}")

	lines.append("=" * 85)
	return "\n".join(lines)