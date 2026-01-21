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
	root_path = Path(root_dir)

	# First pass: find all relevant files and assume directories require BOM
	for dirpath, _, filenames in os.walk(root_dir):
		dir_path = Path(dirpath)
		has_relevant_files = False
		for filename in filenames:
			if filename.endswith(('.txt', '.yml')):
				file_path = dir_path / filename
				files_to_check.append(file_path)
				# Mark this directory and all its parents up to the root
				p = file_path.parent
				while p.is_relative_to(root_path) or p == root_path:
					bom_required[p] = True
					if p == root_path:
						break
					p = p.parent

	# Second pass: Invalidate directories that contain non-BOM files.
	for file_path in files_to_check:
		if not has_bom(file_path):
			# If a file lacks a BOM, mark its directory and all parents as non-compliant.
			p = file_path.parent
			while p.is_relative_to(root_path) or p == root_path:
				if p in bom_required:
					bom_required[p] = False
				if p == root_path:
					break
				p = p.parent

	# Prepare the final list of paths
	final_paths = set()
	bom_true_dirs = {path for path, required in bom_required.items() if required}

	# Add individual files that have a BOM from mixed-content subdirectories
	for file_path in files_to_check:
		if has_bom(file_path) and not bom_required.get(file_path.parent, False):
			if file_path.parent != root_path: # Exclude files in the root
				final_paths.add(str(file_path.relative_to(root_path)))

	# Consolidate fully BOM-compliant directories
	for path in sorted(bom_true_dirs):
		if path == root_path: # Exclude the root directory itself
			continue

		# A path is a top-level consolidated path if none of its parents are also in the list.
		is_subpath = any(path != p and path.is_relative_to(p) for p in bom_true_dirs)
		if not is_subpath:
			# Make the path relative before adding
			final_paths.add(str(path.relative_to(root_path)))

	return sorted(list(final_paths))


if __name__ == '__main__':
	required_bom_paths = find_bom_required_paths(target_directory)

	if required_bom_paths:
		print("The following files and folders are required to have UTF-8 BOM:")
		for path in required_bom_paths:
			print(f"\"{path}\",")
	else:
		print("No .txt or .yml files found that require a BOM.")