from typing import Any, List, Dict, Set, Tuple

# Define the list of keys that represent a meaningful change.
MEANINGFUL_NODE_KEYS = ['label', 'parent']


def get_graph_diff_ids(
		edges_new: Dict[Any, Any], edges_old: Dict[Any, Any],
		nodes_new: Dict[Any, Any], nodes_old: Dict[Any, Any]
) -> Tuple[List[Any], List[Any], List[Any], List[Any], List[Any], List[Any]]:
	"""
	Calculates the set differences for node and edge IDs between two graph versions.
	"""
	old_node_ids: Set[Any] = set(nodes_old.keys())
	new_node_ids: Set[Any] = set(nodes_new.keys())
	old_edge_ids: Set[Any] = set(edges_old.keys())
	new_edge_ids: Set[Any] = set(edges_new.keys())

	# Find added, removed, and common nodes
	added_node_ids = sorted(list(new_node_ids - old_node_ids))
	removed_node_ids = sorted(list(old_node_ids - new_node_ids))
	common_node_ids = sorted(list(old_node_ids & new_node_ids))

	# Find added, removed, and common edges
	added_edge_ids = sorted(list(new_edge_ids - old_edge_ids))
	removed_edge_ids = sorted(list(old_edge_ids - new_edge_ids))
	common_edge_ids = sorted(list(old_edge_ids & new_edge_ids))

	return added_edge_ids, added_node_ids, common_edge_ids, common_node_ids, removed_edge_ids, removed_node_ids


def are_nodes_different(node1: dict, node2: dict) -> bool:
	"""
	Compares two node dictionaries based on their meaningful properties.
	Ignores unstable properties like the internal yEd ID.
	"""

	for key in MEANINGFUL_NODE_KEYS:
		if node1.get(key) != node2.get(key):
			return True  # Found a meaningful difference

	return False  # No meaningful differences found


def are_edges_different(edge1: dict, edge2: dict) -> bool:
	"""
	Compares two edge dictionaries.
	"""

	# Since source and target are already stable IDs, a direct comparison is fine.
	return edge1 != edge2


def get_node_differences(node1: Dict[Any, Any], node2: Dict[Any, Any]) -> List[str]:
	"""
	Compares two node dictionaries and returns a list of keys that have changed.
	Returns an empty list if there are no meaningful differences.
	"""
	differences = []
	for key in MEANINGFUL_NODE_KEYS:
		if node1.get(key) != node2.get(key):
			differences.append(key)
	return differences
