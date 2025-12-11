import configparser
import os

# Get the absolute path of the directory where this script is located.
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Define the absolute path to the config file.
# This is independent of the current working directory.
CONFIG_FILE = os.path.join(SCRIPT_DIR, "config.ini")
# -----------------------------

DEFAULT_LOG_PATH = ''

def _create_default_config():
	"""Creates a new, default configuration file if one does not exist."""
	print(f"INFO: Config file not found. Creating a default one at '{CONFIG_FILE}'...")
	try:
		# The directory is guaranteed to exist since the script is in it,
		# but os.makedirs is safe to call anyway.
		os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
		config = configparser.ConfigParser()
		config['Paths'] = {'log_directory': DEFAULT_LOG_PATH}
		with open(CONFIG_FILE, 'w') as configfile:
			config.write(configfile)
		print("INFO: Please edit the 'log_directory' path in the new config file and restart the application.")
	except Exception as e:
		print(f"ERROR: Could not create or write to the config file: {e}")


def get_log_directory_from_config():
	"""Reads the log directory path from the config file."""
	if not os.path.exists(CONFIG_FILE):
		_create_default_config()
		return DEFAULT_LOG_PATH

	config = configparser.ConfigParser()
	try:
		config.read(CONFIG_FILE)
		return config.get('Paths', 'log_directory')
	except (configparser.NoSectionError, configparser.NoOptionError):
		print(f"WARNING: Config file at '{CONFIG_FILE}' is missing the required 'Paths' section or 'log_directory' key. Using default path.")
		return DEFAULT_LOG_PATH
	except Exception as e:
		print(f"ERROR: An unexpected error occurred while reading the config file: {e}")
	return DEFAULT_LOG_PATH

def update_config_file(section, setting, value):
	"""Safely updates a setting in the correct config.ini file."""
	config = configparser.ConfigParser()
	try:
		config.read(CONFIG_FILE)
		if section not in config:
			config.add_section(section)
		config.set(section, setting, value)
		with open(CONFIG_FILE, 'w') as f:
			config.write(f)
		print(f"Successfully updated '{CONFIG_FILE}' with new setting: {setting} = {value}")
	except Exception as e:
		print(f"ERROR: Failed to write to {CONFIG_FILE}:\n{e}")