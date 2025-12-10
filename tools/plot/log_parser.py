import re

# --- Cache Globals ---
bt_data_cache = None
gp_data_cache = None
pop_data_cache = None
mk_data_cache = None
rt_data_cache = None
tg_data_cache = None

def clear_all_caches():
	"""Resets all data caches to force reparsing on the next call."""
	global bt_data_cache, gp_data_cache, pop_data_cache, mk_data_cache, rt_data_cache, tg_data_cache
	bt_data_cache = None
	gp_data_cache = None
	pop_data_cache = None
	mk_data_cache = None
	rt_data_cache = None
	tg_data_cache = None
	print("All data caches have been cleared.")


def _parse_dynamic_numeric_value(value_str):
	"""
	Converts a string that could be a number, empty, or have K/M/B suffixes into a float or returns the original string.
	Handles commas and whitespace. Returns 0 for empty strings.
	"""
	if not isinstance(value_str, str):
		return value_str # Return as-is if not a string

	cleaned_str = value_str.strip().replace(',', '')
	if not cleaned_str:
		return 0.0

	upper_str = cleaned_str.upper()
	multiplier = 1.0

	if upper_str.endswith('K'):
		multiplier = 1_000.0
		cleaned_str = cleaned_str[:-1]
	elif upper_str.endswith('M'):
		multiplier = 1_000_000.0
		cleaned_str = cleaned_str[:-1]
	elif upper_str.endswith('B'):
		multiplier = 1_000_000_000.0
		cleaned_str = cleaned_str[:-1]

	try:
		return float(cleaned_str) * multiplier
	except (ValueError, TypeError):
		return value_str # Return original string if it's not a number (e.g., a tag 'KBO')


def parse_data_countries(data):
	"""
	Parses all country data (::TG::) lines from the log data.
	This is a very wide dataset with over 160 columns.
	"""
	global tg_data_cache
	if tg_data_cache is not None:
		return tg_data_cache

	print("Parsing country data for the first time...")
	# Define the headers in the exact order they appear in the log
	headers = [
		"year", "tag", "name", "capital_area", "country_type", "government_type", "income", "current_research",
		"has_feudalism", "has_legalism", "has_meritocracy", "has_renaissance", "has_banking", "has_professional_armies",
		"has_new_world", "has_printing_press", "has_pike_and_shot", "has_confessionalism", "has_global_trade",
		"has_artillery_institution", "has_manufactories", "has_scientific_revolution", "has_military_revolution",
		"has_enlightenment", "has_industrialization", "has_levee_en_masse", "estate_nobles_income_lost",
		"estate_clergy_income_lost", "estate_burghers_income_lost", "estate_peasants_income_lost",
		"estate_dhimmi_income_lost", "estate_tribes_income_lost", "estate_cossacks_income_lost",
		"nobles_gold", "clergy_gold", "burghers_gold", "peasants_gold", "dhimmi_gold", "tribes_gold", "cossacks_gold",
		"nobles_balance", "clergy_balance", "burghers_balance", "peasants_balance", "dhimmi_balance", "tribes_balance", "cossacks_balance",
		"nobles_food_income", "clergy_food_income", "burghers_food_income", "peasants_food_income", "dhimmi_food_income", "tribes_food_income", "cossacks_food_income",
		"nobles_trade_income", "clergy_trade_income", "burghers_trade_income", "peasants_trade_income", "dhimmi_trade_income", "tribes_trade_income", "cossacks_trade_income",
		"nobles_income_count", "clergy_income_count", "burghers_income_count", "peasants_income_count", "dhimmi_income_count", "tribes_income_count", "cossacks_income_count",
		"nobles_income_before_tax", "clergy_income_before_tax", "burghers_income_before_tax", "peasants_income_before_tax", "dhimmi_income_before_tax", "tribes_income_before_tax", "cossacks_income_before_tax",
		"nobles_tax", "clergy_tax", "burghers_tax", "peasants_tax", "dhimmi_tax", "tribes_tax", "cossacks_tax",
		"nobles_expense", "clergy_expense", "burghers_expense", "peasants_expense", "dhimmi_expense", "tribes_expense", "cossacks_expense",
		"nobles_max_tax", "clergy_max_tax", "burghers_max_tax", "peasants_max_tax", "dhimmi_max_tax", "tribes_max_tax", "cossacks_max_tax",
		"nobles_relative_power", "clergy_relative_power", "burghers_relative_power", "peasants_relative_power", "dhimmi_relative_power", "tribes_relative_power", "cossacks_relative_power",
		"nobles_satisfaction", "clergy_satisfaction", "burghers_satisfaction", "peasants_satisfaction", "dhimmi_satisfaction", "tribes_satisfaction", "cossacks_satisfaction",
		"nobles_taxable_income", "clergy_taxable_income", "burghers_taxable_income", "peasants_taxable_income", "dhimmi_taxable_income", "tribes_taxable_income", "cossacks_taxable_income",
		"nobles_population", "clergy_population", "burghers_population", "peasants_population", "dhimmi_population", "tribes_population", "cossacks_population",
		"num_loans", "total_debt", "remaining_loan_capacity", "trade_balance", "is_bankrupt", "regency_type", "parliament_type", "parliament_debate_estate", "parliament_debate_name", "parliament_issue_support",
		"rank_level", "score", "num_artists", "great_power_rank", "great_power_score", "living_characters", "num_works_of_art",
		"num_characters", "power_projection", "num_locations", "has_active_rebels", "army_levy_potential", "army_levy_power",
		"army_size", "avg_army_experience", "avg_navy_experience", "num_forts", "expected_army_size", "expected_navy_size",
		"fort_limit", "max_manpower", "max_sailors", "military_strength", "naval_range", "navy_levy_power", "navy_size",
		"navy_strength", "raised_levy_strength", "raw_army_levy_power", "raw_navy_levy_power", "regular_army_size",
		"total_ships", "crown_power", "avg_literacy", "cultural_capacity", "cultural_unity", "primary_culture_percentage",
		"primary_religion_percentage", "total_coastal_population", "total_culture_capacity_used", "economical_base",
		"estimated_monthly_income", "estimated_monthly_income_trade_tax", "num_starving_provinces", "num_institutions_embraced",
		"overlord_tag", "num_active_cb_targets", "annexation_progress", "diplomatic_range", "liberty_desire",
		"max_diplomatic_capacity", "max_diplomats", "num_diplomats", "num_subjects", "subject_loyalty", "used_diplomatic_capacity",
		"gold", "stability", "government_power", "prestige", "war_exhaustion", "manpower", "sailors", "inflation", "army_tradition",
		"navy_tradition", "control_avg", "dev_avg", "prosperity_avg", "market_access_avg", "towns", "cities", "winter_pow_avg"
	]
	societal_value_names = [
		"centralization_vs_decentralization", "traditionalist_vs_innovative", "spiritualist_vs_humanist",
		"aristocracy_vs_plutocracy", "serfdom_vs_free_subjects", "mercantilism_vs_free_trade",
		"belligerent_vs_conciliatory", "quality_vs_quantity", "offensive_vs_defensive", "land_vs_naval",
		"capital_economy_vs_traditional_economy", "individualism_vs_communalism", "outward_vs_inward",
		"sinicized_vs_unsinicized", "absolutism_vs_liberalism", "mysticism_vs_jurisprudence"
	]
	string_columns = {
		"tag", "name", "capital_area", "country_type", "government_type", "current_research",
		"regency_type", "parliament_name", "parliament_type", "parliament_debate_estate",
		"parliament_debate_name", "overlord_tag"
	}

	pattern = re.compile(r"::TG::(.*?)\n")
	parsed_data = []
	current_record = None
	lines_after_TG = 16

	for line in data.splitlines():
		if '::TG::' in line:
			# If a new country record starts, finalize and store the previous one
			# if current_record:
			# 	parsed_data.append(current_record)

			# Start a new record
			match = re.search(r'::TG::(.*)', line)
			if not match: continue

			values = match.group(1).strip().split(':')
			if len(values) != len(headers):
				print(f"Warning: Skipping malformed country data line. Expected {len(headers)} columns, found {len(values)}.")
			lines_after_TG = -1

			current_record = dict(zip(headers, values))

		elif lines_after_TG <= 15:
			# This is a societal value line for the current country
			match = re.search(r"(-?\d+(?:\.\d+)?)$", line)
			if match:
				value = float(match.group(1))
				current_record[societal_value_names[lines_after_TG]] = value
				if lines_after_TG == 15:
					# Convert appropriate values to numeric types
					for key, value in current_record.items():
						if key not in string_columns:
							current_record[key] = _parse_dynamic_numeric_value(value)
					parsed_data.append(current_record)
		lines_after_TG += 1

	tg_data_cache = parsed_data
	print(f"Found and cached {len(tg_data_cache)} country data entries.")
	return parsed_data


def parse_data_building_types(data):
	"""
	Parses all building type lines from the log data.
	Uses a cache to avoid reparsing the same data.
	"""
	global bt_data_cache
	if bt_data_cache is not None:
		return bt_data_cache

	print("Parsing building data for the first time...")
	pattern = re.compile(r"::BT:(\d+):(.*?):(\d+):(.*)")
	parsed_data = [
		{"moment": 1 + int(m.group(1)),
		 "building": m.group(2).strip(),
		 "count": int(m.group(3)),
		 "region": m.group(4).strip()}
		for m in pattern.finditer(data)
	]
	bt_data_cache = parsed_data
	print(f"Found and cached {len(bt_data_cache)} building entries.")
	return parsed_data


def parse_data_goods_prices(data):
	"""
	Parses all goods price (::GP::) lines from the log data.
	Uses a cache to avoid reparsing the same data.
	"""
	global gp_data_cache
	if gp_data_cache is not None:
		return gp_data_cache

	print("Parsing goods price data for the first time...")
	# Regex to capture: 1:Moment, 2:Good, 3:Region, 4:Price
	pattern = re.compile(r"::GP::(\d+):(.+?):(.+?):([\d.-]+)")

	parsed_data = []
	for m in pattern.finditer(data):
		region_name = m.group(3).strip()

		if 'Ocean' in region_name:
			continue

		parsed_data.append({
			"moment": 1 + int(m.group(1)),
			"good": m.group(2).strip(),
			"region": region_name,
			"price": float(m.group(4))
		})

	gp_data_cache = parsed_data
	print(f"Found and cached {len(gp_data_cache)} goods price entries (oceans excluded).")
	return parsed_data


def parse_data_population(data):
	"""
	Parses all population (::POP::) lines from the log data.
	Uses a cache to avoid reparsing the same data.
	"""
	global pop_data_cache
	if pop_data_cache is not None:
		return pop_data_cache

	print("Parsing population data for the first time...")
	# Regex to capture: 1:Moment, 2:Region, 3:Population String
	pattern = re.compile(r"::POP::(\d+):(.+?):([\d.,MK]+)")

	parsed_data = []
	for m in pattern.finditer(data):
		try:
			population_value = _parse_dynamic_numeric_value(m.group(3))
			parsed_data.append({
				"moment": 1 + int(m.group(1)),
				"region": m.group(2).strip(),
				"statistic": "Total Population", #TODO: Add estates
				"population": population_value
			})
		except (ValueError, IndexError) as e:
			print(f"Warning: Could not parse population line: '{m.group(0)}'. Error: {e}")

	pop_data_cache = parsed_data
	print(f"Found and cached {len(pop_data_cache)} population entries.")
	return parsed_data


def parse_data_road_types(data):
	global rt_data_cache
	if rt_data_cache is not None:
		return rt_data_cache

	print("Parsing road type data for the first time...")
	pattern = re.compile(r"::RT::(\d+):(.+?):(.+?):(\d+):(\d+)")
	parsed_data = []
	for m in pattern.finditer(data):
		locations = int(m.group(4))
		locations_with_road = int(m.group(5))
		coverage = (locations_with_road / locations) * 100 if locations > 0 else 0
		parsed_data.append({
			"moment": 1 + int(m.group(1)),
			"region": m.group(2).strip(),
			"road_type": m.group(3).strip(),
			"locations": locations,
			"locations_with_road": locations_with_road,
			"coverage_percentage": coverage
		})
	rt_data_cache = parsed_data
	print(f"Found and cached {len(rt_data_cache)} road type entries.")
	return parsed_data


def parse_data_markets(data):
	"""
	Parses all market data (::MK::) lines from the log data.
	Transforms the data so each statistic becomes a separate entry,
	suitable for the generic graphing function.
	Uses a cache to avoid reparsing the same data.
	"""
	global mk_data_cache
	if mk_data_cache is not None:
		return mk_data_cache

	print("Parsing market data for the first time...")
	# Regex to capture: 1:Year, 2:Market Name, followed by 11 numeric values
	pattern = re.compile(
		r"::MK::(\d+):"          # 1: Year
		r"(.+?):"               # 2: Market Name
		r"([\d.-]+):"           # 3: Food
		r"([\d.-]+):"           # 4: Food Stockpile
		r"([\d.-]+):"           # 5: Max Food Stockpile
		r"([\d.-]+):"           # 6: Food Stockpile Percent
		r"([\d.-]+):"           # 7: Monthly Food
		r"([\d.-]+):"           # 8: Monthly Food Balance
		r"([\d.-]+):"           # 9: Food Price
		r"([\d.-]+):"           # 10: Burgher Food Imports
		r"([\d.-]+):"           # 11: Burgher Food Exports
		r"([\d.-]+):"           # 12: Total Value Traded
		r"([\d.-]+)"            # 13: Merchant Capacity
	)

	# User-friendly names for each statistic, in the order they appear in the log
	statistic_names = [
		"Food", "Food Stockpile", "Max Food Stockpile", "Food Stockpile Percent",
		"Monthly Food", "Monthly Food Balance", "Food Price", "Burgher Food Imports",
		"Burgher Food Exports", "Total Value Traded", "Merchant Capacity"
	]

	transformed_data = []
	for m in pattern.finditer(data):
		moment = int(m.group(1)) + 1
		market_name = m.group(2).strip()

		# Groups 3 through 13 are the numeric values
		values = [float(v) for v in m.groups()[2:]]

		for i, stat_name in enumerate(statistic_names):
			transformed_data.append({
				"moment": moment,
				"region": market_name,  # Using 'region' key to match generic grapher
				"statistic": stat_name, # This will be the filterable category
				"value": values[i]      # This is the value to be plotted
			})

	mk_data_cache = transformed_data
	print(f"Found and cached {len(mk_data_cache)} market statistic entries.")
	return transformed_data
