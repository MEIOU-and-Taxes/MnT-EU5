# It is mandatory to provide in the config file the modding_digests_directory
# It will select the last version automatically
# If you want it to check against another version, you can mention it in the config at modding_digests_version_target (e.g. 1.0.2)

import os
import re

from tools.shared.manage_config import get_from_config


def get_latest_version_folder(base_path):
	"""
	Finds the latest version folder in a given base path.
	Assumes version folders are named in the format 'x.y.z'
	"""
	try:
		# Get all entries in the base path that are directories, in the format A.B.C
		version_folders = [d for d in os.listdir(base_path) if os.path.isdir(os.path.join(base_path, d)) and d.count('.') == 2]
		# Sort the folders based on version number
		# This key splits the version string by '.' and converts each part to an integer
		version_folders.sort(key=lambda v: [int(i) for i in v.split('.')], reverse=True)

		if version_folders:
			return version_folders[0]
		else:
			return None
	except FileNotFoundError:
		return None

def get_modified_files(folder_path):
	"""
	Reads the changes_files.md file from the given folder path
	and extracts the list of modified files.
	"""
	changes_file_path = os.path.join(folder_path, 'changes_files.md')
	modified_files = []

	try:
		with open(changes_file_path, 'r', encoding='utf-8') as f:
			for line in f:
				# Use a regular expression to find lines that start with '- **M**'
				# and capture the file path that follows.
				match = re.match(r'^- \*\*M\*\* (.*)', line)
				if match:
					# The matched file path is in the first capture group
					file = match.group(1)
					if file.startswith('game/'):
						file = file[len('game/'):]
						modified_files.append(file.strip())
	except FileNotFoundError:
		print(f"Error: 'changes_files.md' not found in {folder_path}")
		return []

	return modified_files

def filter_existing_files(repo_root, file_list):
    """
    Filters a list of relative file paths, returning only those that
    actually exist within the repository.
    """
    existing_files = []
    for file_path in file_list:
        # The file paths from the markdown might use forward slashes.
        # It is needed to split the path to apply prefixes/suffixes to the filename only
        dir_part, filename = os.path.split(file_path)
        name_part, ext_part = os.path.splitext(filename)

        # Create a list of possible filenames to check for in the repository
        possible_filenames = [
            filename,                      # Original: FILENAME.txt
            f"M&T_{filename}",             # Prefix: M&T_FILENAME.txt
            f"MnT_{filename}",             # Prefix: MnT_FILENAME.txt
            f"{name_part}_MnT{ext_part}"   # Suffix: FILENAME_MnT.txt
        ]

        # Check if any of the possible file variations exist
        for possible_name in possible_filenames:
            # Construct the full path using the OS-specific separator
            full_path = os.path.join(repo_root, dir_part.replace('/', os.sep), possible_name)

            if os.path.isfile(full_path):
                # If a match is found, add the ORIGINAL file_path to our list
                # and stop checking other variations for this file.
                existing_files.append(file_path)
                break  # Move to the next file_path in the outer loop

    return existing_files


if __name__ == '__main__':
	# --- 1. Determine the repository's root directory ---
	# The script is assumed to be at 'repo/tools/new_file_checker/main.py'.
	# The repository root is therefore three directories up from this script's location.
	try:
		script_path = os.path.abspath(__file__)
		# Go up three levels: main.py -> new_file_checker -> tools -> repo
		repo_root = os.path.abspath(os.path.join(os.path.dirname(script_path), '..', '..'))
		print(f"Repository root identified as: {repo_root}")
	except NameError:
		# Fallback for environments where __file__ is not defined (e.g., some interactive shells)
		repo_root = os.path.abspath('.')
		print(f"Warning: __file__ not defined. Assuming repository root is the current directory: {repo_root}")


	# --- 2. Get the latest version and the list of modified files ---
	dir_modding_digests = get_from_config('Paths', 'modding_digests_directory')
	if not os.path.exists(dir_modding_digests):
		raise FileNotFoundError("Path to modding_digests, according to config file, is not found")

	version_target = get_from_config('Other', 'modding_digests_version_target')
	if version_target:
		if not os.path.exists(os.path.join(dir_modding_digests, version_target)):
			raise FileNotFoundError(f"Version '{version_target}' not found in {dir_modding_digests}")
		latest_version_folder_name = version_target
		print(f"Using specified version folder: {latest_version_folder_name}")
	else:
		latest_version_folder_name = get_latest_version_folder(dir_modding_digests)
		print(f"Found latest version folder: {latest_version_folder_name}")

	if latest_version_folder_name:
		latest_version_folder_path = os.path.join(dir_modding_digests, latest_version_folder_name)
		modified_file_list = get_modified_files(latest_version_folder_path)

		if modified_file_list:
			print(f"\nFound {len(modified_file_list)} modified files in game/ folder, according to changes_files.md")

			# --- 3. Filter the list to get only files that exist in the repo ---
			existing_files_in_repo = filter_existing_files(repo_root, modified_file_list)

			if existing_files_in_repo:
				print(f"\nThere are {len(existing_files_in_repo)} modified files that exist in the repository:")
				for file_path in existing_files_in_repo:
					print(file_path)
			else:
				print("None of the files listed as modified in changes_files.md were found in the repository.")
		else:
			print("No modified files found in the latest version.")
	else:
		print(f"No version folders found in '{dir_modding_digests}' or the path is incorrect.")