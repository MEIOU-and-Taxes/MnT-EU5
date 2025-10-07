from typing import Any
from xml.etree import ElementTree as EmTree
from xml.etree.ElementTree import Element

from auxiliary import namespaces_graphml


def parse_graphml(file_path: str) -> tuple[dict[Any, Any], dict[Any, Any]]:
	"""Parses a .graphml file and returns dictionaries for nodes & edges
	:return: nodes, edges
	:rtype: tuple[dict[Any, Any], dict[Any, Any]]
	:param file_path: .graphml file path
	"""
	try:
		tree = EmTree.parse(file_path)
		root = tree.getroot()

		nodes = find_nodes(root)
		edges = find_edges(root)

	except EmTree.ParseError:
		if file_path == 'nul':
			print(f'The revision reference is wrong or it does not have a .graphml development roadmap')
		else:
			print(f'Unable to parse .graphml file at {file_path}')
		exit(1)
	return nodes, edges


def find_edges(root: Element | Any) -> dict[Any, Any]:
	"""Find all <edge> elements"""
	edges = {}
	for edge in root.findall('.//graphml:edge', namespaces_graphml):
		edge_id = edge.get('id')
		edge_source = edge.get('source')
		edge_target = edge.get('target')

		edges[edge_id] = {'source': edge_source, 'target': edge_target}
	return edges


def find_nodes(root: Element | Any) -> dict[Any, Any]:
	"""Find all <node> elements"""
	nodes = {}
	for node in root.findall('.//graphml:node', namespaces_graphml):
		node_id = node.get('id')
		# Find the <y:NodeLabel> within this node
		label_element = node.find('.//y:NodeLabel', namespaces_graphml)
		if node_id and label_element is not None and label_element.text:
			nodes[node_id] = label_element.text.strip().replace('\n', ' ')
	return nodes
