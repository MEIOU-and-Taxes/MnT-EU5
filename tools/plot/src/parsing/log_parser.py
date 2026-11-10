import os
import re

from src.parsing.definitions import (
	COUNTRY_FIRST_HEADERS, SOCIETAL_VALUE_NAMES, STRING_COLUMNS,
	market_stats, CREDIT_HEADERS, POPULATION_HEADERS, get_series_multiplier
)
from src.parsing.diagnostics import _format_mismatch_report
from src.parsing.numeric_utils import parse_dynamic_numeric_value
from src.parsing.stores import (
	parsed_file_signatures, tg_cumulative_store, bt_cumulative_store, gp_cumulative_store,
	pop_cumulative_store, rt_cumulative_store, mk_cumulative_store, region_locations_store, cr_cumulative_store
)

# Column count mismatch callback (hooked by UI)
_column_mismatch_callback = None

def set_column_mismatch_callback(cb):
	global _column_mismatch_callback
	_column_mismatch_callback = cb

_mismatch_count = 0
_valid_tg_count = 0

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
					num = parse_dynamic_numeric_value(val)
					mult = get_series_multiplier(k)
					if mult != 1.0 and isinstance(num, (int, float)):
						num *= mult
					rec[k] = num
			yr = rec.get("year")
			tag = rec.get("tag")
			if yr and tag:
				tg_cumulative_store[(yr, tag)] = rec

	for line in line_iterable:
		if '\x00' in line:
			line = line.replace('\x00', '')

		# --- TG handling ---
		if '||TG' in line:
			values = None
			if '||TG1||' in line:
				commit_tg(current_tg_record)
				current_tg_record = None
				pending_chunks = [line.split('||TG1||', 1)[1].strip()]
				lines_after_tg = 99
				continue
			elif '||TG2||' in line and pending_chunks:
				pending_chunks.append(line.split('||TG2||', 1)[1].strip())
				lines_after_tg = 99
				continue
			elif '||TG3||' in line and len(pending_chunks) == 2:
				pending_chunks.append(line.split('||TG3||', 1)[1].strip())
				lines_after_tg = 99
				continue
			elif '||TG4||' in line and len(pending_chunks) == 3:
				pending_chunks.append(line.split('||TG4||', 1)[1].strip())
				values = "|".join(pending_chunks).split('|')
				pending_chunks = []
			elif '||TG||' in line:
				commit_tg(current_tg_record)
				current_tg_record = None
				values = line.split('||TG||', 1)[1].strip().split(':')

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
		if '||BT|' in line:
			part = line.split('||BT|', 1)[1]
			p = part.split('|')
			if len(p) >= 4:
				try:
					bt_cumulative_store[(int(p[0]), p[3].strip(), p[1].strip())] = int(p[2])
				except (ValueError, TypeError):
					pass
		elif '||GP||' in line:
			part = line.split('||GP||', 1)[1]
			p = part.split('|')
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
		elif '||POP||' in line:
			part = line.split('||POP||', 1)[1]
			p = part.split('|')
			if len(p) >= 3:
				try:
					moment = int(p[0])
					region = p[1].strip()
					record = {
						"moment": moment,
						"region": region,
						"statistic": "Total Population",
						"population": parse_dynamic_numeric_value(p[2].strip()),
					}
					# Map all population and SLV metrics from index 2 onwards
					for header, val_str in zip(POPULATION_HEADERS, p[2:]):
						val = parse_dynamic_numeric_value(val_str.strip())
						mult = get_series_multiplier(header)
						if mult != 1.0 and isinstance(val, (int, float)):
							val *= mult
						record[header] = val

					if "Total population" in record:
						record["population"] = record["Total population"]

					pop_cumulative_store[(moment, region)] = record
				except (ValueError, TypeError):
					pass

		elif '||RT||' in line:
			part = line.split('||RT||', 1)[1]
			p = part.split('|')
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
		elif '||MK||' in line:
			part = line.split('||MK||', 1)[1]
			p = part.split('|', 2)
			if len(p) >= 3:
				try:
					moment = int(p[0])
					market_name = p[1].strip()
					raw_vals = p[2].strip().split('|')
					vals = []
					for v in raw_vals:
						try: vals.append(float(v))
						except (ValueError, TypeError): pass
					stat_map = dict(zip(market_stats, vals))
					loc_count = float(stat_map.get("Locations", 0.0))
					pop_count = float(stat_map.get("Population", 0.0))
					for name, v in stat_map.items():
						mult = get_series_multiplier(name)
						if mult != 1.0:
							v *= mult
						mk_cumulative_store[(moment, market_name, name)] = {
							"moment": moment, "region": market_name, "market": market_name,
							"statistic": name, "value": v,
							"locations": loc_count,
							"population": pop_count
						}
				except (ValueError, TypeError):
					pass
		elif '||CR||' in line:
			part = line.split('||CR||', 1)[1]
			p = part.split('|', 2)
			if len(p) >= 3:
				try:
					moment = int(p[0])
					tag = p[1].strip()
					raw_vals = p[2].strip().split('|')
					record = {"moment": moment, "tag": tag, "country": tag}
					for name, val_str in zip(CREDIT_HEADERS, raw_vals):
						val = parse_dynamic_numeric_value(val_str)
						mult = get_series_multiplier(name)
						if mult != 1.0 and isinstance(val, (int, float)):
							val *= mult
						record[name] = val
					cr_cumulative_store[(moment, tag)] = record
				except (ValueError, TypeError):
					pass
		elif '||RLOC||' in line:
			part = line.split('||RLOC||', 1)[1]
			p = part.split('|')
			if len(p) >= 2:
				try:
					region_locations_store[p[0].strip()] = int(float(p[1].strip().replace(',', '')))
				except (ValueError, TypeError):
					pass

	commit_tg(current_tg_record)

def get_region_locations():
	return region_locations_store
