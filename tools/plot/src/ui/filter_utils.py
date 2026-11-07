LEGACY_REGIONAL_KEYS = ('good', 'building', 'road_type', 'statistic')

def resolve_filter_key(key, available):
	if key in available:
		return key
	if key in LEGACY_REGIONAL_KEYS and 'regional_metric' in available:
		return 'regional_metric'
	if key == 'credit_metric' and 'country_metric' in available:
		return 'country_metric'
	if key == 'region':
		for alt in ('country', 'market'):
			if alt in available:
				return alt
	return None

def find_matching_combo_index(combo, val):
	idx = combo.findText(val)
	if idx != -1:
		return idx
	low = val.lower()
	alt = val[:-6].strip() if low.endswith(" price") else f"{val} price"
	return combo.findText(alt)