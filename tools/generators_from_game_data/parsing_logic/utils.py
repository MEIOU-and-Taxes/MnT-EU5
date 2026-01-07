def find_matching_brace(text, start_pos):
	"""
	Finds the position of the matching closing brace '}' for an opening brace '{'.
	"""
	open_braces = 1
	pos = start_pos
	while pos < len(text):
		if text[pos] == '{':
			open_braces += 1
		elif text[pos] == '}':
			open_braces -= 1
			if open_braces == 0:
				return pos
		pos += 1
	return -1
