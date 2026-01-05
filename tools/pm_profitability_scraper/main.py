import os
import re
import sys

import pandas as pd
from collections import defaultdict

from tools.shared.fetch_logs import get_from_config

# --- Configuration ---
# Define the names of the folders where your files are located.
# These folders should be in the same directory as this script.

GOODS_RELATIVE_PATH = r'\game\in_game\common\goods'
ADVANCES_RELATIVE_PATH = r'\game\in_game\common\advances'
BUILDINGS_RELATIVE_PATH = r'\game\in_game\common\building_types'
OUTPUT_FILENAME = 'production_methods.xlsx'

DEFAULT_AGE = 'age_1_traditions'

def find_matching_brace(text, start_pos):
	"""
	Finds the position of the matching closing brace '}' for an opening brace '{'.
	"""
	open_braces = 1
	pos = start_pos
	while pos < len(text):
		if text[pos] == '{':
			open_braces += 1
		elif text[pos] == '}':
			open_braces -= 1
			if open_braces == 0:
				return pos
		pos += 1
	return -1


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

if __name__ == '__main__':
	"""
	Main function to orchestrate the parsing and Excel generation.
		"""
	game_dir = get_from_config('Paths', 'game_directory')
	goods_folder = game_dir + GOODS_RELATIVE_PATH
	advances_folder = game_dir + ADVANCES_RELATIVE_PATH
	buildings_folder = game_dir + BUILDINGS_RELATIVE_PATH

	print(f"Scanning for goods and prices in '{goods_folder}'...")
	goods_with_prices = extract_goods_and_prices(goods_folder)
	if not goods_with_prices:
		print("Could not find any goods. Please ensure the 'goods' folder is set up correctly.")
		sys.exit(1)
	print(f"Found {len(goods_with_prices)} unique goods.")

	print(f"\nScanning for building unlocks in '{advances_folder}'...")
	building_unlocks = extract_building_unlocks(advances_folder)
	print(f"Found {len(building_unlocks)} building unlock definitions.")

	print(f"\nProcessing building files in '{buildings_folder}'...")
	all_pms = []
	if not os.path.isdir(buildings_folder):
		print(f"Error: Buildings folder '{buildings_folder}' not found. Aborting.")
		sys.exit(1)

	for filename in os.listdir(buildings_folder):
		filepath = os.path.join(buildings_folder, filename)
		if os.path.isfile(filepath):
			print(f"  - Processing: {filename}")
			try:
				with open(filepath, 'r', encoding='utf-8-sig') as f:
					content = f.read()
				# Pass the unlock data to the parser
				pms = parse_building_file_content(content, building_unlocks)
				all_pms.extend(pms)
			except Exception as e:
				print(f"Error processing file {filename}: {e}")

	if not all_pms:
		print("\nNo production methods found. Exiting.")
		sys.exit(1)
	print(f"Found a total of {len(all_pms)} production methods.")

	print("\nGenerating data tables for Excel...")
	
	# --- Production Methods sheet ---
	sorted_goods = sorted(list(goods_with_prices.keys()))
	pm_columns = ['Building', 'Unlock Age', 'Production Method', 'Produces Good?'] + sorted_goods

	df_pm = pd.DataFrame(all_pms)
	df_pm = df_pm.reindex(columns=pm_columns).fillna(0)

	price_row_data = {
		'Building': 'Market Price', 'Unlock Age': '', 
		'Production Method': '', 'Produces Good?': ''
	}
	price_row_data.update(goods_with_prices)
	price_df = pd.DataFrame([price_row_data]).reindex(columns=pm_columns)
	
	df_pm_final = pd.concat([price_df, df_pm], ignore_index=True)

	# --- Goods sheet ---
	goods_list = sorted(goods_with_prices.items())
	df_goods = pd.DataFrame(goods_list, columns=['Good', 'Market Price'])

	# --- Write to Excel file ---
	try:
		with pd.ExcelWriter(OUTPUT_FILENAME, engine='xlsxwriter') as writer:
			df_pm_final.to_excel(writer, sheet_name='Production Methods', index=False)
			df_goods.to_excel(writer, sheet_name='Goods Prices', index=False)
		
		print(f"\nSuccessfully created Excel file: {OUTPUT_FILENAME} with two sheets.")
	except Exception as e:
		print(f"\nError writing to Excel file: {e}")