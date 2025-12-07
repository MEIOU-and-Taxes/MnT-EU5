import re

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


def _parse_population_value(value_str):
	"""Converts a population string (e.g., '2.2M', '75K', '1,234') to an integer."""
	value_str = value_str.strip().replace(',', '')
	if 'K' in value_str:
		return int(float(value_str.replace('K', '')) * 1_000)
	if 'M' in value_str:
		return int(float(value_str.replace('M', '')) * 1_000_000)
	if 'B' in value_str:
		return int(float(value_str.replace('B', '')) * 1_000_000_000)
	return int(value_str)

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
			population_value = _parse_population_value(m.group(3))
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

def parse_data_countries(data):
	"""
	Parses all country data (::TG::) lines from the log data.
	Transforms the data so each statistic becomes a separate entry,
	suitable for the generic graphing function.
	Uses a cache to avoid reparsing the same data.
	"""
	global tg_data_cache
	if tg_data_cache is not None:
		return tg_data_cache

	print("Parsing country data for the first time...")

	INSTITUTION_NAMES = [
		'feudalism', 'legalism', 'meritocracy', 'renaissance', 'banking',
		'professional_armies', 'new_world', 'printing_press', 'pike_and_shot',
		'confessionalism', 'global_trade', 'artillery_Instution', 'manufactories',
		'scientific_revolution', 'military_revolution', 'enlightenment',
		'industrialization', 'levee_en_masse'
	]
	ESTATE_FLAVOURS = [
		"Nobles", "Burghers", "Clergy", "Peasants", "Elites", "Tribes", "Gentry", "Commoners"
	]
	ESTATE_STATS = [
		"Gold", "Balance", "Food Income", "Trade Income", "Last Month Income Count",
		"Last Months Income Before Tax", "Last Months Tax", "Last Months Expense",
		"Max Tax Value", "Relative Power", "Satisfaction", "Taxable Income", "Total Population"
	]

	transformed_data = []
	pattern = re.compile(r".*::TG::(.*)")
	for line in data.splitlines():
		match = pattern.match(line)
		if not match:
				continue

		line_content = match.group(1)

		try:
			parts = line_content.split('::')
			if len(parts) != 14:
				continue

			main_data_str = parts[0]
			main_data_fields = main_data_str.split(':')
			if len(main_data_fields) != 7 + 18:
				continue

			moment = int(main_data_fields[0]) + 1
			country_name = main_data_fields[2].strip()
			if not country_name or '_REVOLT' in main_data_fields[1]:
				continue

			transformed_data.append({
				"moment": moment,
				"region": country_name,
				"statistic": "Total Income",
				"value": float(main_data_fields[5])
			})

			inst_values = main_data_fields[7:]
			for i, inst_name in enumerate(INSTITUTION_NAMES):
				transformed_data.append({
					"moment": moment,
					"region": country_name,
					"statistic": f"Institution - {inst_name.replace('_', ' ').title()}",
					"value": int(inst_values[i])
				})

			estate_blocks = parts[1:]
			for i, stat_name in enumerate(ESTATE_STATS):
				values_str = estate_blocks[i].split(':')
				if len(values_str) != 8:
					continue

				for j, flavour_name in enumerate(ESTATE_FLAVOURS):
					try:
						value = float(values_str[j])
						transformed_data.append({
							"moment": moment,
							"region": country_name,
							"statistic": f"{flavour_name} {stat_name}",
							"value": value
						})
					except ValueError:
						pass

		except (ValueError, IndexError):
			pass

	tg_data_cache = transformed_data
	print(f"Found and cached {len(tg_data_cache)} country statistic entries.")
	return transformed_data