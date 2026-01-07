import os
import re

from tools.script_generator.generators.pm_profitability_excel import DEFAULT_AGE
from tools.script_generator.parsing_logic.utils import find_matching_brace

GOODS_RELATIVE_PATH = r'\game\in_game\common\goods'
ADVANCES_RELATIVE_PATH = r'\game\in_game\common\advances'
BUILDINGS_RELATIVE_PATH = r'\game\in_game\common\building_types'


def extract_building_unlocks(folder_path):
	"""
	Scans all files in the advances folder to find which age unlocks which building.

	Args:
		folder_path (str): The path to the folder containing advance files.

	Returns:
		dict: A dictionary mapping building names to their unlock age.
	"""
	unlocks = {}
	if not os.path.isdir(folder_path):
		print(f"Warning: Advances folder '{folder_path}' not found.")
		return unlocks

	adv_start_pattern = re.compile(r'^(\w+)\s*=\s*\{', re.MULTILINE)
	age_pattern = re.compile(r'age\s*=\s*(\w+)')
	building_pattern = re.compile(r'unlock_building\s*=\s*(\w+)')

	for filename in os.listdir(folder_path):
		filepath = os.path.join(folder_path, filename)
		if os.path.isfile(filepath):
			try:
				with open(filepath, 'r', encoding='utf-8-sig') as f:
					content = f.read()

				for match in adv_start_pattern.finditer(content):
					start_brace_pos = match.end()
					end_brace_pos = find_matching_brace(content, start_brace_pos)

					if end_brace_pos != -1:
						adv_block = content[start_brace_pos:end_brace_pos]
						age_match = age_pattern.search(adv_block)
						building_match = building_pattern.search(adv_block)

						if age_match and building_match:
							building_name = building_match.group(1)
							age_name = age_match.group(1)
							unlocks[building_name] = age_name
			except Exception as e:
				print(f"Error reading advances from file {filename}: {e}")
	return unlocks


def extract_goods_and_prices(folder_path):
	"""
	Scans all files in the goods folder to extract good names and their
	default_market_price.

	Args:
		folder_path (str): The path to the folder containing goods definition files.

	Returns:
		dict: A dictionary where keys are good names and values are their market prices.
	"""
	goods_data = {}
	if not os.path.isdir(folder_path):
		print(f"Warning: Goods folder '{folder_path}' not found.")
		return goods_data

	good_start_pattern = re.compile(r'^(\w+)\s*=\s*\{', re.MULTILINE)
	price_pattern = re.compile(r'default_market_price\s*=\s*([-\d\.]+)')

	for filename in os.listdir(folder_path):
		filepath = os.path.join(folder_path, filename)
		if os.path.isfile(filepath):
			try:
				with open(filepath, 'r', encoding='utf-8-sig') as f:
					content = f.read()

				for match in good_start_pattern.finditer(content):
					good_name = match.group(1)
					start_brace_pos = match.end()
					end_brace_pos = find_matching_brace(content, start_brace_pos)

					if end_brace_pos != -1:
						good_block = content[start_brace_pos:end_brace_pos]
						price_match = price_pattern.search(good_block)
						goods_data[good_name] = float(price_match.group(1)) if price_match else 0
			except Exception as e:
				print(f"Error reading goods from file {filename}: {e}")

	return goods_data


def parse_building_file_content(content, building_unlocks):
	"""
	Parses the content of a single building file to extract buildings and their
	production methods, including a boolean for production.
	"""
	all_pms = []

	building_start_pattern = re.compile(r'^(\w+)\s*=\s*\{', re.MULTILINE)
	upm_start_pattern = re.compile(r'unique_production_methods\s*=\s*\{')
	pm_pattern = re.compile(r'(\w+)\s*=\s*\{([\s\S]*?)\s*\}', re.MULTILINE)
	kv_pattern = re.compile(r'(\w+)\s*=\s*([-\d\.]+|\w+)')

	for building_match in building_start_pattern.finditer(content):
		building_name = building_match.group(1)

		unlock_age = building_unlocks.get(building_name, DEFAULT_AGE)

		start_brace_pos = building_match.end()
		end_brace_pos = find_matching_brace(content, start_brace_pos)

		if end_brace_pos == -1:
			continue

		building_content = content[start_brace_pos:end_brace_pos]
		upm_start_match = upm_start_pattern.search(building_content)

		if not upm_start_match:
			continue

		upm_start_brace = upm_start_match.end()
		upm_end_brace = find_matching_brace(building_content, upm_start_brace)

		if upm_end_brace == -1:
			continue

		upm_content = building_content[upm_start_brace:upm_end_brace]

		for pm_match in pm_pattern.finditer(upm_content):
			pm_name = pm_match.group(1)
			pm_content = pm_match.group(2)

			pm_data = {
				'Building': building_name,
				'Unlock Age': unlock_age,
				'Production Method': pm_name
			}
			output_good = None
			output_amount = 0.0
			produces_good = False

			for kv_match in kv_pattern.finditer(pm_content):
				key, value = kv_match.groups()

				if key == 'produced':
					output_good = value
				elif key == 'output':
					try:
						output_amount = float(value)
					except ValueError:
						pass
				else:
					try:
						pm_data[key] = -float(value)
					except ValueError: pass

			if output_good and output_amount > 0:
				pm_data[output_good] = pm_data.get(output_good, 0) + output_amount
				produces_good = True

			pm_data['Produces Good?'] = produces_good
			all_pms.append(pm_data)

	return all_pms

