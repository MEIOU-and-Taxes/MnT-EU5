from typing import Any, List, Dict

from auxiliary import IS_DEBUG


def _get_debug_info(text: str) -> str:
	"""Returns the debug info string if IS_DEBUG is True, otherwise an empty string."""
	return f" ({text})" if IS_DEBUG else ""


def _print_section_header(title: str):
	"""Prints a formatted section header."""
	print(f"\n{title}:")


def _print_nodes(node_ids: List[Any], nodes: Dict[Any, Any], prefix: str):
	"""Prints a list of nodes with a given prefix."""
	for node_id in node_ids:
		debug_info = _get_debug_info(f"{node_id}")
		print(f"{prefix} {nodes[node_id]}{debug_info}")


def _print_edges(edge_ids: List[Any], edges: Dict[Any, Any], nodes: Dict[Any, Any], prefix: str):
	"""Prints a list of edges with a given prefix."""
	for edge_id in edge_ids:
		edge = edges[edge_id]
		source_id = edge['source']
		target_id = edge['target']
		debug_info = _get_debug_info(f"{source_id} -> {target_id}")
		print(f"{prefix} {nodes[source_id]} -> {nodes[target_id]}{debug_info}")


def print_elements(added_edge_ids: List[Any],
				   added_node_ids: List[Any],
				   common_edge_ids: List[Any],
				   common_node_ids: List[Any],
				   edges_second: Dict[Any, Any], edges_first: Dict[Any, Any],
				   nodes_second: Dict[Any, Any], nodes_first: Dict[Any, Any],
				   removed_edge_ids: List[Any],
				   removed_node_ids: List[Any]):
	"""
	Generate the diff output for the added/removed/common nodes/edges
	"""

	found_differences = False
	if removed_node_ids:
		_print_section_header("Removed nodes")
		_print_nodes(removed_node_ids, nodes_first, "-")
		found_differences = True

	if added_node_ids:
		_print_section_header("Added nodes")
		_print_nodes(added_node_ids, nodes_second, "+")
		found_differences = True

	if removed_edge_ids:
		_print_section_header("Removed edges")
		_print_edges(removed_edge_ids, edges_first, nodes_first, "-")
		found_differences = True

	if added_edge_ids:
		_print_section_header("Added edges")
		_print_edges(added_edge_ids, edges_second, nodes_second, "+")
		found_differences = True

	if any(nodes_first[node_id] != nodes_second[node_id] for node_id in common_node_ids):
		_print_section_header("Changed nodes")
		for node_id in common_node_ids:
			if nodes_first[node_id] != nodes_second[node_id]:
				_print_nodes([node_id], nodes_first, "-")
				_print_nodes([node_id], nodes_second, "+")
				found_differences = True
				print()

	if any(edges_first[edge_id] != edges_second[edge_id] for edge_id in common_edge_ids):
		_print_section_header("Changed edges")
		for edge_id in common_edge_ids:
			if edges_first[edge_id] != edges_second[edge_id]:
				_print_edges([edge_id], edges_first, nodes_first, "-")
				_print_edges([edge_id], edges_second, nodes_second, "+")
				found_differences = True
				print()

	if not found_differences:
		print ('The files are identical')
