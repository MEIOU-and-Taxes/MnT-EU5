import re
import csv

FILEPATH_CSV_SOURCE = 'climates.csv'
FILEPATH_LOCATION_TEMPLATES = "location_templates_source.txt"
FILEPATH_OUTPUT = "location_templates.txt"

def update_climate_data(target_file, reference_file, output_file):
    """
    Updates the climate values in a target text file based on a reference CSV file.

    Args:
        target_file (str): The path to the target text file to be updated.
        reference_file (str): The path to the CSV file with the new climate data.
        output_file (str): The path to write the updated data to.
    """
    # Step 1: Read the climate reference data into a dictionary
    climate_updates = {}
    try:
        with open(reference_file, mode='r', newline='', encoding='utf-8') as ref_file:
            reader = csv.reader(ref_file)
            next(reader)  # Skip the header row
            for row in reader:
                if row:
                    location, climate = row
                    climate_updates[location] = climate.lower()
    except FileNotFoundError:
        print(f"Error: The reference file '{reference_file}' was not found.")
        return
    except Exception as e:
        print(f"An error occurred while reading the reference file: {e}")
        return

    # Step 2: Read the target file and update the climate values
    updated_lines = []
    try:
        with open(target_file, mode='r', encoding='utf-8') as tgt_file:
            for line in tgt_file:
                # Extract the location name from the beginning of the line
                match = re.match(r'^\s*(\w+)\s*=', line)
                if match:
                    location_name = match.group(1)
                    # Check if this location has a climate update
                    if location_name in climate_updates:
                        new_climate = climate_updates[location_name]
                        # Use regex to replace the old climate value with the new one
                        # This pattern looks for "climate = " followed by a word
                        line = re.sub(r'(climate\s*=\s*)(\w+)', r'\g<1>' + new_climate, line)
                updated_lines.append(line)
    except FileNotFoundError:
        print(f"Error: The target file '{target_file}' was not found.")
        return
    except Exception as e:
        print(f"An error occurred while processing the target file: {e}")
        return

    # Step 3: Write the updated content to the output file
    try:
        with open(output_file, mode='w', encoding='utf-8') as out_file:
            out_file.writelines(updated_lines)
        print(f"Successfully updated climate data and saved to '{output_file}'.")
    except Exception as e:
        print(f"An error occurred while writing to the output file: {e}")

if __name__ == "__main__":
	update_climate_data(FILEPATH_LOCATION_TEMPLATES, FILEPATH_CSV_SOURCE, FILEPATH_OUTPUT)