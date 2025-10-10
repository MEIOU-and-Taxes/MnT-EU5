from typing import Any, List, Dict, Optional
from xml.etree import ElementTree as EmTree

from auxiliary import IS_DEBUG
from auxiliary import namespaces_graphml
from diff import are_edges_different, get_node_differences


def _get_debug_info(text: str) -> str:
	"""Returns the debug info string if IS_DEBUG is True, otherwise an empty string."""
	return f" ({text})" if IS_DEBUG else ""


def _print_section_header(title: str):
	"""Prints a formatted section header."""
	print(f"\n{title}:")


def print_nodes(node_ids: List[Any], nodes: Dict[Any, Any], prefix: str):
	"""Prints a list of nodes with a given prefix."""
	for node_id in node_ids:
		node_label = nodes.get(node_id, {}).get('label', 'Unknown Node')
		debug_info = _get_debug_info(f"ID: {node_id}")
		print(f"{prefix} {node_label}{debug_info}")


def print_changed_node(node_id: int, nodes_first: Dict, nodes_second: Dict, changed_keys: List[str]):
	"""
	Prints a detailed report for a single node that has changed.
	"""
	node_label = nodes_second.get(node_id, {}).get('label', 'Unknown Node')
	debug_info = _get_debug_info(f"ID: {node_id}")
	print(f"* {node_label}{debug_info}:")

	for key in changed_keys:
		old_value = nodes_first.get(node_id, {}).get(key)
		new_value = nodes_second.get(node_id, {}).get(key)

		if key == 'label':
			print(f"    Renamed: '{old_value}' -> '{new_value}'")
		elif key == 'parent':
			old_parent_label = _get_parent_label(old_value, nodes_first)
			new_parent_label = _get_parent_label(new_value, nodes_second)
			if old_parent_label and new_parent_label:
				print(f"    Moved: '{old_parent_label}' -> '{new_parent_label}'")
			elif new_parent_label:
				print(f"    Moved inside: '{new_parent_label}'")
			else:
				print(f"    Moved outside: '{old_parent_label}'")


def _print_edges(edge_ids: List[Any], edges: Dict[Any, Any], nodes: Dict[Any, Any], prefix: str):
	"""Prints a list of edges with a given prefix."""
	for edge_id in edge_ids:
		edge = edges.get(edge_id, {})
		source_id = edge.get('source')
		target_id = edge.get('target')

		source_label = nodes.get(source_id, {}).get('label', 'Unknown Source')
		target_label = nodes.get(target_id, {}).get('label', 'Unknown Target')

		debug_info = _get_debug_info(f"{source_id} -> {target_id}")
		print(f"{prefix} {source_label} -> {target_label}{debug_info}")


def print_diff_report(
		nodes_first: Dict, nodes_second: Dict,
		edges_first: Dict, edges_second: Dict,
		diff_ids: tuple):
	"""
    Generates the full diff report for the console.
	"""

	added_edge_ids, added_node_ids, common_edge_ids, \
		common_node_ids, removed_edge_ids, removed_node_ids = diff_ids

	found_differences = False

	if removed_node_ids:
		found_differences = True
		_print_section_header("Removed nodes")
		print_nodes(removed_node_ids, nodes_first, "-")

	if added_node_ids:
		found_differences = True
		_print_section_header("Added nodes")
		print_nodes(added_node_ids, nodes_second, "+")

	if removed_edge_ids:
		found_differences = True
		_print_section_header("Removed edges")
		_print_edges(removed_edge_ids, edges_first, nodes_first, "-")

	if added_edge_ids:
		found_differences = True
		_print_section_header("Added edges")
		_print_edges(added_edge_ids, edges_second, nodes_second, "+")

	# Find all nodes that have changed and WHAT has changed.
	# This creates a dictionary like {node_id: ['parent', 'label'], ...}
	node_changes = {
		node_id: get_node_differences(nodes_first[node_id], nodes_second[node_id])
		for node_id in common_node_ids
	}
	# Filter out the nodes that didn't actually change
	changed_node_ids_with_details = {k: v for k, v in node_changes.items() if v}

	if changed_node_ids_with_details:
		found_differences = True
		_print_section_header("Changed nodes")
		for node_id, changed_keys in changed_node_ids_with_details.items():
			print_changed_node(node_id, nodes_first, nodes_second, changed_keys)
			print()

	# Find all edges that have changed content
	changed_edge_ids = [
		edge_id for edge_id in common_edge_ids
		if are_edges_different(edges_first[edge_id], edges_second[edge_id])
	]
	if changed_edge_ids:
		found_differences = True
		_print_section_header("Changed edges")
		for edge_id in changed_edge_ids:
			_print_edges([edge_id], edges_first, nodes_first, "-")
			_print_edges([edge_id], edges_second, nodes_second, "+")
			print()

	if not found_differences:
		print('The files are identical')


def update_file_with_stable_ids(
		tree: EmTree.ElementTree,
		nodes_to_update: dict[str, dict],
		id_key: str,
		file_path: str
) -> None:
	"""
	Adds the stable ID <data> element to the specified nodes in the XML tree
	and writes the changes back to the file.
	"""
	root = tree.getroot()

	# Register namespaces to keep the output file clean (e.g., "y:ShapeNode" instead of "ns0:ShapeNode")
	for uri, prefix in namespaces_graphml.items():
		EmTree.register_namespace(prefix, uri)

	for id_yed, node_data in nodes_to_update.items():
		# Find the specific <node> element in the tree using its yEd ID
		node_element = root.find(f'.//graphml:node[@id="{id_yed}"]', namespaces_graphml)

		if node_element is not None:
			new_stable_id = node_data['id_stable']

			# Create the new <data> element to insert (e.g. <data key="d4">123</data>)
			new_data_element = EmTree.Element('data', {'key': id_key})
			new_data_element.text = str(new_stable_id)

			# Insert the new element as the first child of the <node>
			node_element.insert(0, new_data_element)
			print(f"  -> Updated node '{id_yed}' with new stable ID: {new_stable_id}")

	# Write the entire modified tree back to the original file
	tree.write(file_path, encoding='utf-8', xml_declaration=True)
	print(f"Successfully updated file with stable IDs: {file_path}")


def _get_parent_label(parent_id: Optional[int], all_nodes: Dict[int, Any]) -> str:
	"""
	Helper function to get a descriptive label for a parent node.
	"""
	if parent_id is None:
		return None

	parent_node = all_nodes.get(parent_id)
	if parent_node:
		parent_label = parent_node.get('label', 'Unknown Group')
		return f"{parent_label}{_get_debug_info(f' (ID: {parent_id})')}"

	return f"Unknown Group (ID: {parent_id})"
