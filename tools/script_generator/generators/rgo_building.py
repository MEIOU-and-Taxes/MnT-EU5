# --- Templates ---
# Each item is a tuple: (output_filename, template_string)
# This allows generating a separate file for each template.
TEMPLATES = [
	(
		"generated_rgo_max_levels.txt",
		"""rgo_$GOOD$_max_level = {
	if = {
		limit = { raw_material = goods:$GOOD$ }
		add = {
			desc = "BUILDING_LEVEL_BASE"
			value = 2
		}
		add = {
			desc = "BUILDING_LEVEL_DEVELOPMENT"
			value = development
			multiply = 0.1
		}
		add = {
			desc = "BUILDING_LEVEL_POPULATION"
			value = population
			multiply = 0.025
		}
		add = {
			desc = "LITERACY"
			value = pop_literacy
			multiply = 0.01
		}
	}
	if = {
		limit = {
			location_rank ?= location_rank:rural_settlement
		}
		multiply = {
			desc = "BUILDING_LEVEL_IS_RURAL_SETTLEMENT"
			value = 2
		}
	}
}"""
	),
]


def main():
	"""Main function to generate text files from templates."""
	print(f"1. Scanning for raw materials in '{GOODS_FOLDER}'...")
	raw_material_goods = extract_raw_materials(GOODS_FOLDER)
	if not raw_material_goods:
		print("Error: No raw materials found. Exiting.")
		return
	print(f"   Found {len(raw_material_goods)} raw materials.")

	print("\n2. Generating code from templates...")
	for output_filename, template_string in TEMPLATES:
		print(f"   - Generating {output_filename}...")
		all_generated_blocks = []
		for good in raw_material_goods:
			# Replace placeholder and strip leading/trailing whitespace from the template
			generated_block = template_string.strip().replace('$GOOD$', good)
			all_generated_blocks.append(generated_block)

		# Join all blocks with double newlines for spacing
		final_output = "\n\n".join(all_generated_blocks)

		try:
			with open(output_filename, 'w', encoding='utf-8') as f:
				f.write(final_output)
		except Exception as e:
			print(f"     Error writing to file: {e}")

	print("\nSuccess! All files generated.")


if __name__ == '__main__':
	main()