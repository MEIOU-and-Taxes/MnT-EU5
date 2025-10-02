# Not to be run directly
# Meant to be triggered by:
#	git diff -- "MEIOUandTaxes/Documentation/Development roadmap.graphml"

import sys
import xml.etree.ElementTree as EmTree
from typing import Any

import pydevd_pycharm

DEBUG = False

# Define the XML namespaces used in the .graphml file
namespaces = {
	'graphml': 'http://graphml.graphdrawing.org/xmlns',
	'y': 'http://www.yworks.com/xml/graphml'
}


def idless(element_id: str) -> str:
	"""
	Remove id from node & string; e.g. n21 -> 21
	"""
	return element_id.replace('n', '')


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

	# Find the <y:EdgeLabel> within this edge
	# if edge_id and edge_element is not None and edge_element.text:
	# edges[edge_id] = edge_id.text.strip()
	# edges[edge_target] = edge_source.text.strip()

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
	added_node_ids = new_node_ids - old_node_ids
	removed_node_ids = old_node_ids - new_node_ids
	common_node_ids = old_node_ids & new_node_ids

	added_edge_ids = new_edge_ids - old_edge_ids
	removed_edge_ids = old_edge_ids - new_edge_ids
	common_edge_ids = old_edge_ids & new_edge_ids

	added_node_ids = sorted(added_node_ids)
	removed_node_ids = sorted(removed_node_ids)
	common_node_ids = sorted(common_node_ids)

	added_edge_ids = sorted(added_edge_ids)
	removed_edge_ids = sorted(removed_edge_ids)
	common_edge_ids = sorted(common_edge_ids)
	return added_edge_ids, added_node_ids, common_edge_ids, common_node_ids, removed_edge_ids, removed_node_ids


def print_elements(added_edge_ids: list[Any],
				   added_node_ids: list[Any],
				   common_edge_ids: list[Any],
				   common_node_ids: list[Any],
				   edges_new: dict[Any, Any], edges_old: dict[Any, Any], nodes_new: dict[Any, Any],
				   nodes_old: dict[Any, Any],
				   removed_edge_ids: list[Any],
				   removed_node_ids: list[Any]):
	"""
	Generate the diff output
	"""
	debug_info = ''
	print()
	if removed_node_ids:
		print('Removed nodes:')
		for node_id in removed_node_ids:
			if DEBUG:
				debug_info = f' ({node_id})'
			print(f'- {nodes_old[node_id]}{debug_info}')
		print()

	if added_node_ids:
		print('Added nodes:')
		for node_id in added_node_ids:
			if DEBUG:
				debug_info = f' ({node_id})'
			print(f'+ {nodes_new[node_id]}{debug_info}')
		print()

	if removed_edge_ids:
		print('Removed edges:')
		for edge_id in removed_edge_ids:
			edge = edges_old[edge_id]
			edge_source = edge['source']
			edge_target = edge['target']
			if DEBUG:
				debug_info = f' ({edge_source} -> {edge_target})'
			print(f'- {nodes_old[edge_source]} -> {nodes_old[edge_target]}{debug_info}')
		print()

	if added_edge_ids:
		print('Added edges:')
		for edge_id in added_edge_ids:
			edge = edges_new[edge_id]
			edge_source = edge['source']
			edge_target = edge['target']
			if DEBUG:
				debug_info = f' ({edge_source} -> {edge_target})'
			print(f'+ {nodes_new[edge['source']]} -> {nodes_new[edge['target']]}{debug_info}')
		print()

	if common_node_ids:
		print('Changed nodes:')
		for node_id in common_node_ids:
			if nodes_old[node_id] != nodes_new[node_id]:
				if DEBUG:
					debug_info = f' ({node_id})'
				print(f'- {nodes_old[node_id]}{debug_info}')
				if DEBUG:
					debug_info = f' ({node_id})'
				print(f'+ {nodes_new[node_id]}{debug_info}')
				print()
		print()

	if common_edge_ids:
		print('Changed edges:')
		for edge_id in common_edge_ids:
			if edges_old[edge_id] != edges_new[edge_id]:
				edge_old = edges_old[edge_id]
				edge_source = edge_old['source']
				edge_target = edge_old['target']

				if DEBUG:
					debug_info = f' ({edge_source} -> {edge_target})'
				print(f'- {nodes_old[edge_source]} -> {nodes_old[edge_target]}{debug_info}')

				edge_new = edges_new[edge_id]
				edge_source = edge_new['source']
				edge_target = edge_new['target']
				if DEBUG:
					debug_info = f' ({edge_source} -> {edge_target})'
				print(f'+ {nodes_new[edge['source']]} -> {nodes_new[edge['target']]}{debug_info}')
				print()
		print()


def main():
	# Connect to the PyCharm debug server (Git Textconv Debugger)
	# Make sure the port number matches the one in your debug configuration.
	if DEBUG:
		try:
			pydevd_pycharm.settrace('localhost', port=51234, stdout_to_server=True, stderr_to_server=True)
		except ConnectionRefusedError:
			print(f'\nYou forgot to disable debugging mode in the script\n')

	# Git provides several arguments; the old and new file paths are reliable ones
	old_file_path = sys.argv[2]
	new_file_path = sys.argv[1]

	# Parse both files to get their node & edge structures
	nodes_old, edges_old = parse_graphml(old_file_path)
	nodes_new, edges_new = parse_graphml(new_file_path)

	added_edge_ids, added_node_ids, common_edge_ids, common_node_ids, removed_edge_ids, removed_node_ids = process_elements(
		edges_new, edges_old, nodes_new, nodes_old)

	print_elements(added_edge_ids, added_node_ids, common_edge_ids, common_node_ids, edges_new, edges_old, nodes_new,
				   nodes_old, removed_edge_ids, removed_node_ids)


if __name__ == "__main__":
	main()

# def print_graph_elements(element_population: dict[Any, Any],
# 						 element_subset: list[Any],
# 						 header: str,
# 						 f_string_id_to_print: str):
# 	if element_subset:
# 		print(header)
# 		for element_id in element_subset:
# 			element_idless = idless(element_id)
# 			if not DEBUG:
# 				f_string_id_to_print = ''
# 			print(f'- {element_population[element_id]}{f_string_id_to_print}')
