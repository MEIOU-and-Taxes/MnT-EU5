import configparser
import os

CONFIG_PATH = r"../shared/"
CONFIG_FILE = CONFIG_PATH + r"config.ini"
DEFAULT_LOG_PATH = ''

def get_from_config(section, key):
	"""Reads from the config file."""
	config = configparser.ConfigParser()
	if os.path.exists(CONFIG_FILE):
		try:
			config.read(CONFIG_FILE)
			return config.get(section, key)
		except configparser.NoOptionError:
			raise Exception(f'{section}:{key} does not exist in the config file')

	create_config_file(config)
	raise Exception(f'The config file {CONFIG_FILE} does not exist. It has been generated. Now you can complete entries as requested.')

def create_config_file(config: configparser.ConfigParser):
	os.makedirs(CONFIG_PATH, exist_ok=True)
	config['Paths'] = {
		'log_directory': DEFAULT_LOG_PATH,
		'modding_digests_directory': ''
	}
	config['Other'] = {
		'modding_digests_version_target' : ''
	}
	try:
		with open(CONFIG_FILE, 'w') as configfile:
			config.write(configfile)
	except Exception as e:
		print(f"ERROR: Could not write config file: {e}")