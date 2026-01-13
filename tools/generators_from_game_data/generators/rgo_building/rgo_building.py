import os
import sys

from tools.generators_from_game_data.parsing_logic.file_parser import GOODS_RELATIVE_PATH, extract_raw_materials
from tools.shared.fetch_logs import get_from_config

BASE_PATH = f'generators/rgo_building/'
INPUT_TEMPLATES_FOLDER = BASE_PATH + 'input_templates'
OUTPUT_GENERATED_FOLDER = BASE_PATH + 'output'
PLACEHOLDER = '$GOOD$'

if __name__ == '__main__':
	"""
	Main function to read templates from an input folder, process them,
	and write the results to an output folder.
	"""
	# 1. Get the list of raw material goods to iterate over
	game_dir = get_from_config('Paths', 'game_directory')
	goods_folder = game_dir + GOODS_RELATIVE_PATH

	print(f"1. Scanning for raw materials in '{goods_folder}'...")
	raw_material_goods = extract_raw_materials(goods_folder)
	if not raw_material_goods:
		print("Error: No raw materials found. Please check the 'goods' folder. Exiting.")
		sys.exit(1)
	print(f"   Found {len(raw_material_goods)} raw materials.")

	# 2. Check for input folder and create output folder if it doesn't exist
	print(f"\n2. Preparing input/output folders...")
	if not os.path.isdir(INPUT_TEMPLATES_FOLDER):
		print(f"Error: Input folder '{INPUT_TEMPLATES_FOLDER}' not found. Please create it and add template files.")
		sys.exit(1)

	if not os.path.isdir(OUTPUT_GENERATED_FOLDER):
		print(f"   Output folder '{OUTPUT_GENERATED_FOLDER}' not found. Creating it.")
		os.makedirs(OUTPUT_GENERATED_FOLDER)

	# 3. Iterate through each file in the input templates folder
	print(f"\n3. Processing templates from '{INPUT_TEMPLATES_FOLDER}'...")

	template_files = [f for f in os.listdir(INPUT_TEMPLATES_FOLDER) if
					  os.path.isfile(os.path.join(INPUT_TEMPLATES_FOLDER, f))]

	if not template_files:
		print("   No template files found in the input folder.")
		sys.exit(1)

	for template_filename in template_files:
		input_filepath = os.path.join(INPUT_TEMPLATES_FOLDER, template_filename)
		output_filepath = os.path.join(OUTPUT_GENERATED_FOLDER, template_filename)

		print(f"   - Processing '{template_filename}'...")

		try:
			# Read the entire content of the template file
			with open(input_filepath, 'r', encoding='utf-8') as f:
				template_string = f.read()
		except Exception as e:
			print(f"     Error reading template file: {e}")
			continue  # Skip to the next template

		# Generate all text blocks by replacing the placeholder for each good
		all_generated_blocks = []
		for good in raw_material_goods:
			generated_block = template_string.replace(PLACEHOLDER, good)
			all_generated_blocks.append(generated_block)

		# Join all blocks with double newlines for spacing
		final_output = "\n".join(all_generated_blocks)

		# Write the final concatenated string to the corresponding output file
		try:
			with open(output_filepath, 'w', encoding='utf-8') as f:
				f.write(final_output)
		except Exception as e:
			print(f"     Error writing to output file '{output_filepath}': {e}")

	print(f"\nSuccess! All templates processed. Check the '{OUTPUT_GENERATED_FOLDER}' folder for results.")