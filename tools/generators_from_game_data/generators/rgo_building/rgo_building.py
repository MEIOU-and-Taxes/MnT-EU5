import re
import sys
from pathlib import Path

from tools.generators_from_game_data.parsing_logic.utils import find_matching_brace

# The generator reads the mod itself, so it finds its paths from this file, not from the working directory.
MOD_ROOT = Path(__file__).resolve().parents[4]
MAX_LEVELS_TEMPLATES = Path(__file__).resolve().parent / 'input_templates' / 'max_levels'
MAX_LEVELS_OUTPUT = Path(__file__).resolve().parent / 'output' / 'max_levels'
RGO_BUILDINGS_FILE = MOD_ROOT / 'in_game' / 'common' / 'building_types' / 'RGO_buildings.txt'
MOD_GOODS_FOLDER = MOD_ROOT / 'in_game' / 'common' / 'goods'
# Goods methods in output order. Each method gets one category base size modifier.
METHODS = ['farming', 'mining', 'gathering', 'hunting', 'forestry']


def read_template(name):
	return (MAX_LEVELS_TEMPLATES / name).read_text(encoding='utf-8-sig')


def fill(template, **values):
	for key, value in values.items():
		template = template.replace(f'${key}$', value)
	return template


def rgo_goods():
	"""Goods that have an RGO building, read from the max_levels lines in RGO_buildings.txt."""
	content = RGO_BUILDINGS_FILE.read_text(encoding='utf-8-sig')
	return sorted(set(re.findall(r'^\s*max_levels\s*=\s*rgo_(\w+)_max_level', content, re.MULTILINE)))


def goods_methods():
	"""Method of every good in the mod goods files. Mod goods are REPLACE overrides of vanilla."""
	methods = {}
	start = re.compile(r'^(?:\w+:)?(\w+)\s*=\s*\{', re.MULTILINE)
	method = re.compile(r'^\s*method\s*=\s*(\w+)', re.MULTILINE)
	for path in sorted(MOD_GOODS_FOLDER.glob('*.txt')):
		content = path.read_text(encoding='utf-8-sig')
		for match in start.finditer(content):
			end = find_matching_brace(content, match.end())
			if end == -1:
				continue
			found = method.search(content[match.end():end])
			if found:
				methods[match.group(1)] = found.group(1)
	return methods


def generate_max_levels():
	"""
	Writes the rgo_<good>_max_level script values, the category and per-good size modifiers,
	their icons and their loc into output/max_levels. Paste each file over the matching section in the mod.
	"""
	goods = rgo_goods()
	methods = goods_methods()
	missing = [good for good in goods if methods.get(good) not in METHODS]
	if missing:
		print(f"Error: no known goods method for {missing}. Add method to the mod goods override.")
		sys.exit(1)

	permissive = {line.strip() for line in read_template('permissive_goods.txt').splitlines()
				  if line.strip() and not line.startswith('#')}
	strict_template = read_template('max_level_strict.txt')
	permissive_template = read_template('max_level_permissive.txt')
	extra_folder = MAX_LEVELS_TEMPLATES / 'else_extra'

	values, types, icons, modifier_loc, row_loc = [], [], [], [], []
	for method in METHODS:
		method_fill = dict(METHOD=method, METHOD_UPPER=method.upper(), METHOD_TITLE=method.title(), KEY=method)
		types.append(fill(read_template('modifier_type.txt'), **method_fill))
		icons.append(fill(read_template('modifier_icon.txt'), **method_fill))
		modifier_loc.append(fill(read_template('modifier_loc_method.txt'), **method_fill))
		row_loc.append(fill(read_template('level_rows_loc_method.txt'), **method_fill))

	for method in METHODS:
		method_goods = [good for good in goods if methods[good] == method]
		values.append(f'# {method.title()} goods\n')
		for good in method_goods:
			extra_file = extra_folder / f'{good}.txt'
			extra = extra_file.read_text(encoding='utf-8-sig') if extra_file.exists() else ''
			if extra and good not in permissive:
				print(f"Error: else_extra/{good}.txt exists but {good} is not in permissive_goods.txt.")
				sys.exit(1)
			good_fill = dict(GOOD_UPPER=good.upper(), GOOD=good, METHOD_UPPER=method.upper(), METHOD=method,
							 KEY=good, ELSE_EXTRA=extra)
			template = permissive_template if good in permissive else strict_template
			values.append(fill(template, **good_fill))
			types.append(fill(read_template('modifier_type.txt'), **good_fill))
			icons.append(fill(read_template('modifier_icon.txt'), **good_fill))
			modifier_loc.append(fill(read_template('modifier_loc_good.txt'), **good_fill))
			row_loc.append(fill(read_template('level_rows_loc_good.txt'), **good_fill))

	MAX_LEVELS_OUTPUT.mkdir(parents=True, exist_ok=True)
	outputs = {
		'MnT_RGO_removal.txt': '\n'.join(values),
		'mnt_modifier_types.txt': '\n'.join(types),
		'MnT_modifier_icons.txt': '\n'.join(icons),
		'MnT_modifier_types_l_english.yml': ''.join(modifier_loc),
		'MnT_rgo_level_rows_l_english.yml': ''.join(row_loc),
	}
	for name, text in outputs.items():
		(MAX_LEVELS_OUTPUT / name).write_text(text, encoding='utf-8')
	print(f"Max levels: {len(goods)} goods written to '{MAX_LEVELS_OUTPUT}'.")


if __name__ == '__main__':
	generate_max_levels()
