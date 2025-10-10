import os
import sys
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as EmTree

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
			# Connect to the PyCharm debug server
			# Make sure the port number matches the one in your debug configuration.
			pydevd_pycharm.settrace('localhost', port=DEBUG_PORT, stdout_to_server=True, stderr_to_server=True)
		except ImportError:
			print("Debug mode is on, but 'pydevd_pycharm' module not found. Please install it.", file=sys.stderr)
		except ConnectionRefusedError:
			print(f'\nYou forgot to disable debugging mode in the script\n')


def is_in_working_directory(file_path_str: str) -> bool:
	"""
	Checks if a file path is located within the current working directory
	or one of its subdirectories. This is OS-agnostic.
	"""

	# Get the current working directory as a resolved, absolute path object.
	# .resolve() makes it absolute and cleans up any '..' etc.
	working_dir = Path.cwd().resolve()

	# Get the file path as a resolved, absolute path object.
	file_path = Path(file_path_str).resolve()

	try:
		# is_relative_to() returns True if file_path is under working_dir
		return file_path.is_relative_to(working_dir)
	except AttributeError:
		# Fallback for Python versions <3.9
		# Check if the working directory is one of the file's parents.
		return working_dir in file_path.parents or file_path == working_dir


def assign_stable_ids(unstable_nodes: dict, stable_nodes: dict) -> dict:
	"""
	Calculates and assigns new stable IDs to a dictionary of unstable nodes.
	Returns the updated dictionary of unstable nodes.
	"""
	max_id = max(stable_nodes.keys()) if stable_nodes else 0

	next_id = max_id + 1
	for yed_id in unstable_nodes:
		unstable_nodes[yed_id]['id_stable'] = next_id
		next_id += 1

	return unstable_nodes


def write_updated_graphml(tree: EmTree.ElementTree, nodes_to_update: dict, id_key: str, file_path: str) -> None:
	"""
	Modifies an XML tree in memory by adding stable IDs and saves it to a file.
	"""
	root = tree.getroot()

	EmTree.register_namespace("", "http://graphml.graphdrawing.org/xmlns")
	EmTree.register_namespace("java", "http://www.yworks.com/xml/yfiles-common/1.0/java")
	EmTree.register_namespace("sys", "http://www.yworks.com/xml/yfiles-common/markup/primitives/2.0")
	EmTree.register_namespace("x", "http://www.yworks.com/xml/yfiles-common/markup/2.0")
	EmTree.register_namespace("xsi", "http://www.w3.org/2001/XMLSchema-instance")
	EmTree.register_namespace("y", "http://www.yworks.com/xml/graphml")
	EmTree.register_namespace("yed", "http://www.yworks.com/xml/yed/3")

	for yed_id, node_data in nodes_to_update.items():
		node_element = root.find(f'.//graphml:node[@id="{yed_id}"]', namespaces_graphml)
		if node_element is not None:
			new_data_element = EmTree.Element('data', {'key': id_key})
			new_data_element.text = str(node_data['id_stable'])
			node_element.insert(0, new_data_element)

	tree.write(file_path, encoding='utf-8', xml_declaration=True)


def build_yed_to_stable_id_map(stable_nodes: dict, unstable_nodes: dict) -> dict:
	"""
	Creates a comprehensive mapping from yEd IDs (e.g., "n0") to stable IDs (e.g., 1).

	This is a critical step to allow edge translation. It iterates through the original
	node data before the keys are changed.
	"""
	id_map = {}
	# The stable nodes are keyed by stable_id, but the yed_id is needed for the map.
	# We need to find the original yed_id. This requires a change in the parser.
	# Let's adjust the strategy. The map should be built in the parser.

	# --- REVISED STRATEGY ---
	# The parser is the only place that sees both IDs for every node simultaneously.
	# The map MUST be built there. The translation can be a helper function.
	pass # See revised parse.py below.


def translate_edges(original_edges: dict, yed_to_stable_id_map: dict) -> dict:
	"""
	Translates edge source/target from yEd IDs to stable IDs and generates
	a new, stable, composite key for each edge.

	The new key is a tuple: (source_stable_id, target_stable_id, occurrence_index)
	"""
	translated_edges = {}
	# Use a Counter to track how many times we've seen a specific (source, target) pair.
	# This is essential for handling parallel edges correctly.
	edge_occurrence_counter = Counter()

	for edge_data in original_edges.values():
		original_source = edge_data['source']
		original_target = edge_data['target']

		# Look up the new stable ID in the map.
		new_source = yed_to_stable_id_map.get(original_source)
		new_target = yed_to_stable_id_map.get(original_target)

		# Only process the edge if both its source and target nodes are valid.
		if new_source is not None and new_target is not None:
			# The key for our counter is the (source, target) pair.
			pair_key = (new_source, new_target)

			# Get the current occurrence index for this pair (e.g., 0 for the first time).
			occurrence_index = edge_occurrence_counter[pair_key]

			# Create the new, completely stable, and unique key for the edge.
			stable_edge_key = (new_source, new_target, occurrence_index)

			# Store the edge data using our new stable key.
			translated_edges[stable_edge_key] = {
				'source': new_source,
				'target': new_target
			}

			# Increment the counter for this pair for the next time we see it.
			edge_occurrence_counter[pair_key] += 1

	return translated_edges

def add_parent_information(nodes: dict, yed_to_stable_id_map: dict) -> dict:
	"""
	Processes a dictionary of nodes to add a 'parent' key to each one.
	The parent is determined by parsing the yEd ID hierarchy (e.g., "n9::n0").
	"""
	for node_data in nodes.values():
		yed_id = node_data['id_yed']
		parent_stable_id = None # Default parent is the root graph

		if '::' in yed_id:
			# The parent's yEd ID is everything before the last '::'
			parent_yed_id = yed_id.rsplit('::', 1)[0]

			# Find the parent's stable ID using our complete map
			parent_stable_id = yed_to_stable_id_map.get(parent_yed_id)

		node_data['parent'] = parent_stable_id

	return nodes