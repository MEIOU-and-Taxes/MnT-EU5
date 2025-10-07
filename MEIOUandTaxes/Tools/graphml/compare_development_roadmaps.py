# Not to be run directly
# Meant to be triggered by:
#   git diff -- "MEIOUandTaxes/Documentation/Development roadmap.graphml"
# Can be configured to be used just by calling:
#   git diff-roadmap
# To debug, set the environment variable:
#   $env:DEBUG_GRAPHML_DIFF = "1"
# And run the PyCharm debugger on the specified port.

import os
import sys
import xml.etree.ElementTree as EmTree
from typing import Any

IS_DEBUG = os.getenv('DEBUG_GRAPHML_DIFF') == '1'
DEBUG_PORT = 59420

# Define the XML namespaces used in the .graphml file
namespaces = {
	'graphml': 'http://graphml.graphdrawing.org/xmlns',
	'y': 'http://www.yworks.com/xml/graphml'
}


def parse_graphml(file_path: str) -> tuple[dict[Any, Any], dict[Any, Any]]:
	"""Parses a .graphml file and returns dictionaries for nodes & edges
	:return: nodes, edges
	:rtype: tuple[dict[Any, Any], dict[Any, Any]]
	:param file_path: .graphml file path
	"""
	edges = {}
	nodes = {}
	try:
		tree = EmTree.parse(file_path)
		root = tree.getroot()

		# Find all <node> elements
		for node in root.findall('.//graphml:node', namespaces):
			node_id = node.get('id')
			# Find the <y:NodeLabel> within this node
			label_element = node.find('.//y:NodeLabel', namespaces)
			if node_id and label_element is not None and label_element.text:
				nodes[node_id] = label_element.text.strip().replace('\n', ' ')

		# Find all <edge> elements
		for edge in root.findall('.//graphml:edge', namespaces):
			edge_id = edge.get('id')
			edge_source = edge.get('source')
			edge_target = edge.get('target')

			edges[edge_id] = {'source': edge_source, 'target': edge_target}

	except EmTree.ParseError:
		if file_path == 'nul':
			print(f'The revision reference is wrong or it does not have a .graphml development roadmap')
		else:
			print(f'Unable to parse .graphml file at {file_path}')
		exit(1)
	return nodes, edges


def process_elements(edges_new: dict[Any, Any], edges_old: dict[Any, Any], nodes_new: dict[Any, Any],
					 nodes_old: dict[Any, Any]) -> tuple[
	list[Any], list[Any], list[Any], list[Any], list[Any], list[Any]]:
	# Get the sets of IDs
	old_node_ids = set(nodes_old.keys())
	new_node_ids = set(nodes_new.keys())
	old_edge_ids = set(edges_old.keys())
	new_edge_ids = set(edges_new.keys())

	# Find added, removed, and common nodes
	added_node_ids = sorted(new_node_ids - old_node_ids)
	removed_node_ids = sorted(old_node_ids - new_node_ids)
	common_node_ids = sorted(old_node_ids & new_node_ids)

	added_edge_ids = sorted(new_edge_ids - old_edge_ids)
	removed_edge_ids = sorted(old_edge_ids - new_edge_ids)
	common_edge_ids = sorted(old_edge_ids & new_edge_ids)

	return added_edge_ids, added_node_ids, common_edge_ids, common_node_ids, removed_edge_ids, removed_node_ids


def main():

	if IS_DEBUG:
		import pydevd_pycharm
		try:
			# Connect to the PyCharm debug server (Git Textconv Debugger)
			# Make sure the port number matches the one in your debug configuration.
			pydevd_pycharm.settrace('localhost', port=DEBUG_PORT, stdout_to_server=True, stderr_to_server=True)
		except ImportError:
			print("Debug mode is on, but 'pydevd_pycharm' module not found. Please install it.", file=sys.stderr)
		except ConnectionRefusedError:
			print(f'\nYou forgot to disable debugging mode in the script\n')

	# Git provides several arguments; the old and new file paths are reliable ones
	file_path_first = sys.argv[2]
	file_path_second = sys.argv[1]

	# Parse both files to get their node & edge structures
	nodes_first, edges_first = parse_graphml(file_path_first)
	nodes_second, edges_second = parse_graphml(file_path_second)

	added_edge_ids, added_node_ids, common_edge_ids, common_node_ids, removed_edge_ids, removed_node_ids = process_elements(
		edges_second, edges_first, nodes_second, nodes_first)

	from render import print_elements
	print_elements(added_edge_ids, added_node_ids, common_edge_ids, common_node_ids, edges_second, edges_first,
				   nodes_second,
				   nodes_first, removed_edge_ids, removed_node_ids)


if __name__ == "__main__":
	main()
