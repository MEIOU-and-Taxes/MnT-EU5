import configparser
import os

CONFIG_PATH = r"../shared/"
CONFIG_FILE = CONFIG_PATH + r"log_reader_config.ini"
DEFAULT_LOG_PATH = ''

def get_log_directory_from_config():
	"""Reads the log directory path from the config file."""
	config = configparser.ConfigParser()
	if os.path.exists(CONFIG_FILE):
		try:
			config.read(CONFIG_FILE)
			return config.get('Paths', 'log_directory')
		except (configparser.NoSectionError, configparser.NoOptionError):
			pass

	os.makedirs(CONFIG_PATH, exist_ok=True)
	config['Paths'] = {'log_directory': DEFAULT_LOG_PATH}
	try:
		with open(CONFIG_FILE, 'w') as configfile:
			config.write(configfile)
	except Exception as e:
		print(f"ERROR: Could not write config file: {e}")
	return DEFAULT_LOG_PATH