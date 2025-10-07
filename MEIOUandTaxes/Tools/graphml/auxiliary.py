import os
import sys

IS_DEBUG = os.getenv('DEBUG_GRAPHML_DIFF') == '1'
DEBUG_PORT = 59420

# Define the XML namespaces used in the .graphml file
namespaces_graphml = {
	'graphml': 'http://graphml.graphdrawing.org/xmlns',
	'y': 'http://www.yworks.com/xml/graphml'
}


def enable_debugging():
	if IS_DEBUG:
		print(f'Debugging to be enabled')
		import pydevd_pycharm
		try:
			# Connect to the PyCharm debug server (Git Textconv Debugger)
			# Make sure the port number matches the one in your debug configuration.
			pydevd_pycharm.settrace('localhost', port=DEBUG_PORT, stdout_to_server=True, stderr_to_server=True)
		except ImportError:
			print("Debug mode is on, but 'pydevd_pycharm' module not found. Please install it.", file=sys.stderr)
		except ConnectionRefusedError:
			print(f'\nYou forgot to disable debugging mode in the script\n')
