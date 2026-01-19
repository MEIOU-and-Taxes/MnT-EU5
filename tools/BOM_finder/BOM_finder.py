import os
from pathlib import Path
from tools.shared.fetch_logs import get_from_config

target_directory = get_from_config('Paths', 'game_directory')

def has_bom(file_path):
	"""Checks if a file starts with the UTF-8 BOM."""
	try:
		with open(file_path, 'rb') as f:
			return f.read(3) == b'\xef\xbb\xbf'
	except IOError:
		return False


def find_bom_required_paths(root_dir):
	"""
	Finds all .txt and .yml files that must have a BOM, consolidating
	folders where all relevant files and subfolders have a BOM.
	"""
	bom_required = {}  # Tracks directories and their BOM status
	files_to_check = []

	# First pass: find all relevant files and assume directories require BOM
	for dirpath, _, filenames in os.walk(root_dir):
		dir_path = Path(dirpath)
		has_relevant_files = False
		for filename in filenames:
			if filename.endswith(('.txt', '.yml')):
				has_relevant_files = True
				files_to_check.append(dir_path / filename)

		if has_relevant_files:
			bom_required[dir_path] = True

	# Second pass: check files and update BOM requirement for directories
	for file_path in files_to_check:
		if not has_bom(file_path):
			# If a file doesn't have a BOM, mark its directory and all parents as not fully BOM-compliant
			current_path = file_path.parent
			while current_path != Path(root_dir).parent:
				if current_path in bom_required:
					bom_required[current_path] = False
				current_path = current_path.parent

	# Prepare the final list of paths
	final_paths = set()
	bom_true_dirs = {path for path, required in bom_required.items() if required}

	# Add individual files that have BOM from mixed-content directories
	for file_path in files_to_check:
		if has_bom(file_path) and not bom_required.get(file_path.parent, False):
			final_paths.add(str(file_path))

	# Consolidate directories
	for path in sorted(bom_true_dirs):
		# Check if any parent is already in the set of fully BOM-compliant directories
		is_subpath = any(path != p and path.is_relative_to(p) for p in bom_true_dirs)
		if not is_subpath:
			final_paths.add(str(path))

	return sorted(list(final_paths))


if __name__ == '__main__':
	required_bom_paths = find_bom_required_paths(target_directory)

	if required_bom_paths:
		print("The following files and folders are required to have UTF-8 BOM:")
		for path in required_bom_paths:
			print(f"- {path}")
	else:
		print("No .txt or .yml files found that require a BOM.")