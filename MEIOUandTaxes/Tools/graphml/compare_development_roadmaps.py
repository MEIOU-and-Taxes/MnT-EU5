# Not to be run directly
# Meant to be triggered by:
#   git diff -- "MEIOUandTaxes/Documentation/Development roadmap.graphml"
# Can be configured to be used just by calling:
#   git diff-roadmap
# To debug, set the environment variable:
#   $env:DEBUG_GRAPHML_DIFF = "1"
# And run the PyCharm debugger on the specified port.

import sys
from typing import Any

from parse import parse_graphml
from auxiliary import enable_debugging


def get_graph_diff_ids(edges_new: dict[Any, Any], edges_old: dict[Any, Any], nodes_new: dict[Any, Any],
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

	enable_debugging()
	# Git provides several arguments; the old and new file paths are reliable ones
	file_path_first = sys.argv[2]
	file_path_second = sys.argv[1]

	# Parse both files to get their node & edge structures
	nodes_first, edges_first = parse_graphml(file_path_first)
	nodes_second, edges_second = parse_graphml(file_path_second)

	added_edge_ids, added_node_ids, common_edge_ids, common_node_ids, removed_edge_ids, removed_node_ids = get_graph_diff_ids(
		edges_second, edges_first, nodes_second, nodes_first)

	from render import print_elements
	print_elements(added_edge_ids, added_node_ids, common_edge_ids, common_node_ids, edges_second, edges_first,
				   nodes_second,
				   nodes_first, removed_edge_ids, removed_node_ids)


if __name__ == "__main__":
	main()
