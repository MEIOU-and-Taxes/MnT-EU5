from typing import Any, Optional
from xml.etree import ElementTree as EmTree
from xml.etree.ElementTree import Element

from auxiliary import namespaces_graphml, is_in_working_directory, assign_stable_ids, write_updated_graphml, \
	translate_edges, add_parent_information


def process_graphml_file(file_path: str) -> tuple[dict, dict, bool]:
	"""
	Main processing function for .graphml file.
	Reads, checks, updates (if necessary), and returns the graph data.
	"""

	# Get data from the parsing module
	try:
		tree, data = read_graphml_file(file_path)
	except Exception as e:
		print(f'Unable to parse .graphml file at {file_path}: {e}')
		return {}, {}, False

	# Unpack all data from the parser
	stable_nodes = data["stable_nodes"]
	unstable_nodes = data["unstable_nodes"]
	original_edges = data["original_edges"]
	yed_to_stable_id_map = data["yed_to_stable_id_map"]
	id_key = data["id_key"]
	can_file_be_compared = True

	# Check if an update is needed and possible
	if unstable_nodes:
		is_writable = is_in_working_directory(file_path)

		if is_writable and id_key:
			print(f'File "{file_path}" has unstable IDs. Updating file...')
			unstable_nodes = assign_stable_ids(unstable_nodes, stable_nodes)
			write_updated_graphml(tree, unstable_nodes, id_key, file_path)

			# Update the main nodes dictionary and the ID map
			for yed_id, node_data in unstable_nodes.items():
				stable_id = node_data['id_stable']
				stable_nodes[stable_id] = node_data
				yed_to_stable_id_map[yed_id] = stable_id # Add new nodes to the map

		elif not is_writable:
			print(
				f'Warning: File "{file_path}" has unstable IDs but is not in the working directory. Cannot use this revision to compare against.')
			can_file_be_compared = False
		else:  # No id_key
			print(
				f'Warning: File "{file_path}" has no "ID" custom property. Cannot use this revision to compare against.')
			can_file_be_compared = False

	# Now that all nodes have stable IDs & the map is complete, it can be determined the stable parent for every node
	all_nodes = stable_nodes.copy()
	all_nodes.update({node['id_stable']: node for node in unstable_nodes.values() if 'id_stable' in node})

	final_nodes = add_parent_information(all_nodes, yed_to_stable_id_map)

	# Translate Edges - The map is complete
	final_edges = translate_edges(original_edges, yed_to_stable_id_map)

	# The 'stable_nodes' and 'final_edges' dictionaries now use a consistent ID system
	# and can be safely passed to other functions.
	return final_nodes, final_edges, can_file_be_compared


def extract_edges_from_root(root: Element | Any) -> dict[Any, Any]:
	"""Find all <edge> elements"""
	edges = {}
	for edge in root.findall('.//graphml:edge', namespaces_graphml):
		edge_id = edge.get('id')
		edge_source = edge.get('source')
		edge_target = edge.get('target')

		edges[edge_id] = {'source': edge_source, 'target': edge_target}
	return edges


def find_nodes(root: Element | Any, file_path) -> tuple[dict[Any, Any], dict[Any, Any]]:
	"""Find all <node> elements"""

	has_identity_custom_property = root.find('.//graphml:key[@attr.name="ID"]', namespaces_graphml)
	id_key = ''
	if not has_identity_custom_property:
		print(f'Graph at {file_path} has no node ID custom property')
	else:
		id_key = has_identity_custom_property.attrib['id']

	nodes, nodes_unstable = {}, {}
	graphml_nodes = root.findall('.//graphml:node', namespaces_graphml)
	id_max = -1
	for graph_node in graphml_nodes:
		id_stable = -1
		id_yed = graph_node.get('id')

		children = list(graph_node)
		for i, child in enumerate(children):
			if child.attrib.get('key') == id_key:
				id_stable = int(child.text)
				id_max = id_stable
				break

		# Find the <y:NodeLabel> within this node
		label_element = graph_node.find('.//y:NodeLabel', namespaces_graphml)
		label_text = ''
		if id_yed and label_element is not None and label_element.text:
			label_text = label_element.text.strip().replace('\n', ' ')

		node = {'label': label_text, 'id_stable': id_stable}

		if id_stable >= 0:
			nodes[id_stable] = node
		else:
			nodes_unstable[id_yed] = node

	id_next = id_max
	for graph_node in nodes_unstable:
		id_next += 1
		nodes_unstable[graph_node]['id_stable'] = id_next
		# nodes[id_next] = nodes_unstable[graph_node]
		pass

	return nodes, nodes_unstable


def get_id_key(root: EmTree.Element) -> Optional[str]:
	"""Finds the 'id' of the key attribute for the custom property 'ID'."""
	id_key_element = root.find('.//graphml:key[@attr.name="ID"]', namespaces_graphml)
	if id_key_element is not None:
		return id_key_element.attrib['id']
	return None


def extract_nodes_from_root(root: EmTree.Element, id_key: Optional[str]) -> tuple[
	dict[Any, Any], dict[Any, Any], dict[Any, Any]]:
	"""Iterates through the XML tree, extracting all nodes into stable and unstable dicts.
	Unstable nodes are those that do not have a custom property `id_key`, meant to represent stable ID"""
	stable_nodes, unstable_nodes = {}, {}

	yed_to_stable_id_map = {}  # The mapping dictionary
	# Find ALL <graph> elements, whether at the top level or nested inside a group node.
	all_graph_elements = root.findall('.//graphml:graph', namespaces_graphml)

	for graph_element in all_graph_elements:
		# For each <graph>, find only its DIRECT <node> children.
		# The '.' is crucial, it prevents us from re-processing deeper nodes.
		for node_element in graph_element.findall('./graphml:node', namespaces_graphml):
			id_yed = node_element.get('id')
			stable_id = -1

			if id_key:
				id_element = node_element.find(f'./graphml:data[@key="{id_key}"]', namespaces_graphml)
				if id_element is not None and id_element.text:
					stable_id = int(id_element.text)

			# --- Build the map ---
			# Map the yed_id to the node's stored stable_id IF it has one
			# Unstable nodes will be added to the map later, after they get an ID.
			if stable_id > 0:
				yed_to_stable_id_map[id_yed] = stable_id

				# ... (rest of the node data extraction logic is the same) ...
			label_element = node_element.find('.//y:NodeLabel', namespaces_graphml)
			label = "N/A"
			if label_element is not None and label_element.text:
				# For groups, the label can be deeply nested, so .// is correct here.
				label = label_element.text.strip().replace('\n', ' ')

			node_data = {'label': label, 'id_stable': stable_id, 'id_yed': id_yed}

			if stable_id > 0:
				stable_nodes[stable_id] = node_data
			else:
				unstable_nodes[id_yed] = node_data

	return stable_nodes, unstable_nodes, yed_to_stable_id_map


def read_graphml_file(file_path: str) -> tuple[EmTree.ElementTree, dict]:
	"""
	Parses a .graphml file and returns the raw data.
	This function is the public interface for this module.
	"""
	try:
		tree = EmTree.parse(file_path)
		root = tree.getroot()

		id_key = get_id_key(root)
		stable_nodes, unstable_nodes, yed_to_stable_id_map = extract_nodes_from_root(root, id_key)

		# Edges are extracted with their original yEd IDs
		original_edges = extract_edges_from_root(root)

		return tree, {
			"id_key": id_key,
			"stable_nodes": stable_nodes,
			"unstable_nodes": unstable_nodes,
			"original_edges": original_edges,  # Return original edges
			"yed_to_stable_id_map": yed_to_stable_id_map  # Return the partial map
		}

	except EmTree.ParseError:
		raise # TODO: Improve error handling
