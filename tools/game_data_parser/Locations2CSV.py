import csv
import fileinput
import re
import os

input_filename = "C:\Games\Europa Universalis V\game\in_game\map_data\definitions.txt"
output_filename = "locations_output.csv"

all_levels = ["continent", "subcontinent", "region", "area", "province", "location"]

def generate_location_csv(input_file_path, output_file_path, stop_level='location'):
	"""
	Parses a file with a hierarchical structure and creates a CSV file,
	stopping at the specified hierarchical level.

	Args:
		input_file_path (str): The path to the input file.
		output_file_path (str): The path for the output CSV file.
		stop_level (str): The level at which to stop ('continent', 'subcontinent',
						  'region', 'area', 'province', or 'location').
						  Defaults to 'location'.
	"""
	# Define the complete order of the hierarchy.

	# Validate the stop_level and determine the CSV header.
	try:
		stop_index = all_levels.index(stop_level)
		header = all_levels[:stop_index + 1]
	except ValueError:
		print(f"Error: Invalid stop_level '{stop_level}'.")
		print(f"Please choose from: {', '.join(all_levels)}")
		return

	# Use a set to store unique rows as tuples to prevent duplicates.
	unique_rows = set()
	path_stack = []

	try:
		# Use 'utf-8-sig' to automatically handle the Byte Order Mark (BOM).
		with open(input_file_path, 'r', encoding='utf-8-sig') as f:
			for line in f:
				line = line.strip()

				if not line or line.startswith('#'):
					continue

				# This block processes the deepest level (province with locations).
				# It's the point where we have the most complete path information.
				if '=' in line and '{' in line and '}' in line:
					parts = line.split('=', 1)
					province_name = parts[0].strip()

					# The full path to the current province.
					province_path = path_stack + [province_name]

					if stop_level == 'location':
						locations_str = parts[1].strip().lstrip('{').rstrip('}').strip()
						locations = locations_str.split()
						for loc in locations:
							if loc:
								location_path = province_path + [loc]
								# Add the full path as a tuple to the set.
								unique_rows.add(tuple(location_path))
					elif stop_level == 'province':
						# Add the path up to the province level.
						unique_rows.add(tuple(province_path))
					else:
						# For higher levels (area, region, etc.), add the relevant part of the path stack.
						# The stop_index ensures we only take the parent path up to the desired level.
						parent_path = path_stack[:stop_index + 1]
						if parent_path:
							unique_rows.add(tuple(parent_path))

				# This block handles entering a new, higher-level block.
				elif '=' in line and '{' in line:
					key = line.split('=')[0].strip()
					path_stack.append(key)

					# If the current level is the stop_level, add it to the set.
					current_level_name = all_levels[len(path_stack) - 1]
					if current_level_name == stop_level:
						unique_rows.add(tuple(path_stack))

				# This block handles exiting a block.
				elif '}' in line:
					if path_stack:
						path_stack.pop()

	except FileNotFoundError:
		print(f"Error: The file '{input_file_path}' was not found.")
		return
	except Exception as e:
		print(f"An error occurred while reading the file: {e}")
		return

	# Convert the set of tuples into a list of dictionaries for the CSV writer.
	# Sorting the list of tuples first ensures a consistent and logical order in the CSV.
	sorted_rows = sorted(list(unique_rows))
	csv_rows = [dict(zip(header, row)) for row in sorted_rows]

	# Write the data to the CSV file.
	try:
		with open(output_file_path, 'w', newline='', encoding='utf-8') as csvfile:
			writer = csv.DictWriter(csvfile, fieldnames=header)
			writer.writeheader()
			writer.writerows(csv_rows)
		print(f"Successfully created CSV file at: {output_file_path}")
		print(f"Data was processed up to the '{stop_level}' level.")
	except IOError as e:
		print(f"Error writing to CSV file: {e}")


if __name__ == '__main__':
	# Stop level is any from ["continent", "subcontinent", "region", "area", "province", "location"]
	generate_location_csv(input_filename, output_filename, stop_level='area')