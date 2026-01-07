import os
import sys

import pandas as pd

from tools.script_generator.parsing_logic.file_parser import extract_building_unlocks, extract_goods_and_prices, \
	parse_building_file_content, GOODS_RELATIVE_PATH, ADVANCES_RELATIVE_PATH, BUILDINGS_RELATIVE_PATH
from tools.shared.fetch_logs import get_from_config

DEFAULT_AGE = 'age_1_traditions'
OUTPUT_FILENAME = 'production_methods.xlsx'

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