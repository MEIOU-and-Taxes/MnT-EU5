# Not to be run directly
# Meant to be triggered by:
#   git diff -- "MEIOUandTaxes/Documentation/Development roadmap.graphml"
# Can be configured to be used just by calling:
#   git diff-roadmap
# To debug, set the environment variable:
#   $env:DEBUG_GRAPHML_DIFF = "1"
# And run the PyCharm debugger on the specified port.

import sys

from diff import get_graph_diff_ids
from auxiliary import enable_debugging
from parse import process_graphml_file


def main():
	enable_debugging()
	# Git provides several arguments; the old and new file paths are reliable ones
	file_path_first = sys.argv[2]
	file_path_second = sys.argv[1]

	# Parse both files to get their node & edge structures
	nodes_first, edges_first, can_compare_first_file = process_graphml_file(file_path_first)
	nodes_second, edges_second, can_compare_second_file = process_graphml_file(file_path_second)

	if not can_compare_first_file:
		print("Can't compare because the first file has no ID custom parameter - cannot use this revision")
		return
	if not can_compare_second_file:
		print("Can't compare because the second file has no ID custom parameter - cannot use this revision")
		return

	diff_ids_set  = get_graph_diff_ids(
		edges_second, edges_first, nodes_second, nodes_first)

	from render import print_diff_report
	print_diff_report(nodes_first, nodes_second, edges_first, edges_second, diff_ids_set)


if __name__ == "__main__":
	main()
