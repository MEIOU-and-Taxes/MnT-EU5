import re
import os
from collections import defaultdict

from tools.shared.manage_config import get_from_config

def process_log(p_file_error, p_file_error_cleaned, p_file_error_cleaned_old, p_file_error_cleaned_oldest):
	# Handle log file rotation
	if os.path.exists(p_file_error_cleaned_oldest):
		os.remove(p_file_error_cleaned_oldest)  # Overwrite the oldest file
	if os.path.exists(p_file_error_cleaned_old):
		os.rename(p_file_error_cleaned_old, p_file_error_cleaned_oldest)
	if os.path.exists(p_file_error_cleaned):
		os.rename(p_file_error_cleaned, p_file_error_cleaned_old)

	# Read the previous cleaned_error_old.log for comparison
	old_entries = set()
	if os.path.exists(p_file_error_cleaned_old):
		with open(p_file_error_cleaned_old, 'r', encoding='utf-8') as old_log_file:
			old_log_content = old_log_file.read()
			# Extract the actual log content (without COUNT)
			old_entries = {entry.strip() for entry in re.split(r'COUNT:\d+.*?\n\n', old_log_content)}

	try:
		with open(p_file_error, 'r', encoding='utf-8') as file:
			log_entries = file.readlines()
	except UnicodeDecodeError:
		# Try a different encoding if utf-8 fails
		with open(p_file_error, 'r', encoding='latin-1') as file:
			log_entries = file.readlines()

	# Regular expression to remove timestamps and identify file references at the start of each entry
	timestamp_pattern = re.compile(r'\[\d{2}:\d{2}:\d{2}\]')
	file_ref_pattern = re.compile(r'^\[.*\.cpp:\d+\]')  # Match file_name.cpp:number pattern

	cleaned_log = []
	current_entry = []
	entries_count = defaultdict(int)

	for line in log_entries:
		# Remove timestamps
		line_without_timestamp = timestamp_pattern.sub('', line).strip()

		# Check if this is a new log entry (based on [file_name.cpp:number] pattern)
		if file_ref_pattern.match(line_without_timestamp):
			# If we have accumulated a previous entry, add it to the cleaned log
			if current_entry:
				entry_str = '\n'.join(current_entry).strip()
				entries_count[entry_str] += 1
				current_entry = []

		current_entry.append(line_without_timestamp)

	# Don't forget the last entry
	if current_entry:
		entry_str = '\n'.join(current_entry).strip()
		entries_count[entry_str] += 1

	# Sort entries by count in descending order
	sorted_entries = sorted(entries_count.items(), key=lambda x: x[1], reverse=True)

	# Now merge repeated entries, place "COUNT:x" in front, and limit to 3 lines if needed
	for entry, count in sorted_entries:
		lines = entry.split('\n')

		# Check if entry has more than 3 lines
		if len(lines) > 3:
			entry_truncated = '\n'.join(lines[:3])
			shortened = True
		else:
			entry_truncated = entry
			shortened = False

		# Add COUNT at the beginning
		count_line = f"COUNT:{count}"

		# Check if the truncated entry is new by comparing with old log entries
		if entry_truncated not in old_entries:
			count_line += "	 !! NEW !!"

		if shortened:
			count_line += "		  (entry shortened)"

		cleaned_log.append(f"{count_line}\n\n{entry_truncated}\n\n")

	# Output the cleaned log
	output_file = p_file_error_cleaned
	with open(output_file, 'w', encoding='utf-8') as output:
		output.writelines(cleaned_log)

	print(f"Processed log saved to {output_file}")

if __name__ == '__main__':
	log_path = get_from_config('Paths', 'log_directory')

	file_error = log_path + 'error.log'
	file_error_cleaned = log_path + 'cleaned_error.log'
	file_error_cleaned_old = log_path + 'cleaned_error_old.log'
	file_error_cleaned_oldest = log_path + 'cleaned_error_oldest.log'

	# Call the function with the path to your error.log
	process_log(file_error, file_error_cleaned, file_error_cleaned_old, file_error_cleaned_oldest)
