import configparser
import os

CONFIG_PATH = r"../shared/"
CONFIG_FILE = CONFIG_PATH + r"config.ini"
DEFAULT_LOG_PATH = ''

def _create_default_config():
	"""
	Creates a new, default configuration file if one does not exist.
	"""
	print(f"INFO: Config file not found. Creating a default one at '{CONFIG_FILE}'...")
	try:
		os.makedirs(CONFIG_PATH, exist_ok=True)
		config = configparser.ConfigParser()
		config['Paths'] = {'log_directory': DEFAULT_LOG_PATH}
		with open(CONFIG_FILE, 'w') as configfile:
			config.write(configfile)
		print("INFO: Please edit the 'log_directory' path in the new config file and restart the application.")
	except Exception as e:
		print(f"ERROR: Could not create or write to the config file: {e}")


def get_log_directory_from_config():
	"""
	Reads the log directory path from the config file.
	If the config file does not exist, it will be created with a default value.
	"""
	if not os.path.exists(CONFIG_FILE):
		_create_default_config()
		# After creation, we know the value is the default, so we can return it directly.
		return DEFAULT_LOG_PATH

	config = configparser.ConfigParser()
	try:
		config.read(CONFIG_FILE)
		return config.get('Paths', 'log_directory')
	except (configparser.NoSectionError, configparser.NoOptionError):
		# This handles cases where the file exists but is empty or malformed.
		print(f"WARNING: Config file at '{CONFIG_FILE}' is missing the required 'Paths' section or 'log_directory' key. Using default path.")
		return DEFAULT_LOG_PATH
	except Exception as e:
		print(f"ERROR: An unexpected error occurred while reading the config file: {e}")
	return DEFAULT_LOG_PATH