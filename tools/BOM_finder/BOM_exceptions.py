import os
from pathlib import Path
from collections import defaultdict

from tools.BOM_finder.BOM_finder import has_bom
from tools.shared.fetch_logs import get_from_config

target_directory = get_from_config('Paths', 'game_directory')
THRESHOLD_PERCENTAGE = 80
THRESHOLD_FILES = 5

def find_bom_exceptions(root_dir: str) -> list[dict]:
	"""
	Finds files that are exceptions to folders that are almost entirely
	UTF-8 with BOM.

	An exception is a file without a BOM in a folder where either:
	1. There are few files without a BOM.
	2. Over X% of the other relevant files have a BOM.

	Returns a list of dictionaries, each containing details about an exception.
	"""
	exception_files = []
	root_path = Path(root_dir)

	for dirpath, _, filenames in os.walk(root_path):
		current_dir = Path(dirpath)

		relevant_files = [
			current_dir / f for f in filenames if f.endswith(('.txt', '.yml'))
		]

		if not relevant_files:
			continue

		non_bom_files = [p for p in relevant_files if not has_bom(p)]
		bom_count = len(relevant_files) - len(non_bom_files)
		total_count = len(relevant_files)

		# We only care about folders that have at least one non-BOM file
		if not non_bom_files:
			continue

		# Calculate the percentage of files that DO have a BOM
		bom_percentage = (bom_count / total_count) * 100

		# Condition 1: no_of_files is the exception.
		is_single_exception = len(non_bom_files) <= THRESHOLD_FILES

		# Condition 2: Over X% of files have a BOM.
		is_high_percentage_exception = bom_percentage > THRESHOLD_PERCENTAGE

		if is_single_exception or is_high_percentage_exception:
			# This folder is a "near miss". Report the files causing it.
			for file_path in non_bom_files:
				exception_files.append({
					# Change these lines to make paths relative
					'file': str(file_path.relative_to(root_path)),
					'folder': str(current_dir.relative_to(root_path)),
					'reason': f"Folder has {bom_count}/{total_count} files with BOM ({bom_percentage:.1f}%)"
				})

	return exception_files


if __name__ == '__main__':
	print(f"Scanning '{os.path.abspath(target_directory)}' for BOM exceptions...")

	exceptions = find_bom_exceptions(target_directory)

	if exceptions:
		print("\nFound files preventing their folders from being fully BOM-compliant:")
		# Group exceptions by folder for cleaner output
		exceptions_by_folder = {}
		for exc in exceptions:
			if exc['folder'] not in exceptions_by_folder:
				exceptions_by_folder[exc['folder']] = {
					'reason': exc['reason'],
					'files': []
				}
			exceptions_by_folder[exc['folder']]['files'].append(exc['file'])

		for folder, data in exceptions_by_folder.items():
			print(f"\n- Folder: {folder}")
			print(f"  Reason: {data['reason']}")
			print("  Exception files (missing BOM):")
			for file in data['files']:
				print(f"	- {file}")
	else:
		print("\nNo folders with BOM exceptions were found based on the criteria.")