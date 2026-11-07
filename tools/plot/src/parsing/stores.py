import os

# Caches
_bt_cache = None
_gp_cache = None
_pop_cache = None
_mk_cache = None
_mkm_cache = None
_rt_cache = None
_tg_cache = None
_cm_cache = None
_rloc_cache = None
_cr_cache = None
_crm_cache = None
_reg_cache = None

# Cache signatures of files: filepath -> (mtime, size)
parsed_file_signatures = {}

# Cumulative stores across log overwrites / reloads
tg_cumulative_store = {}
bt_cumulative_store = {}
gp_cumulative_store = {}
pop_cumulative_store = {}
rt_cumulative_store = {}
mk_cumulative_store = {}
region_locations_store = {}
cr_cumulative_store = {}


def clear_all_caches():
	global _bt_cache, _gp_cache, _pop_cache, _mk_cache, _mkm_cache, _rt_cache, _tg_cache, _cm_cache, _rloc_cache, _cr_cache, _crm_cache, _reg_cache
	_bt_cache = _gp_cache = _pop_cache = _mk_cache = _mkm_cache = _rt_cache = _tg_cache = _cm_cache = _rloc_cache = _cr_cache = _crm_cache = _reg_cache = None


def reset_cumulative_history():
	parsed_file_signatures.clear()
	tg_cumulative_store.clear()
	bt_cumulative_store.clear()
	gp_cumulative_store.clear()
	pop_cumulative_store.clear()
	rt_cumulative_store.clear()
	mk_cumulative_store.clear()
	region_locations_store.clear()
	cr_cumulative_store.clear()
	clear_all_caches()


def should_parse_file(filepath: str) -> bool:
	if not os.path.exists(filepath):
		return False
	try:
		s = os.stat(filepath)
		sig = (s.st_mtime, s.st_size)
		return parsed_file_signatures.get(filepath) != sig
	except OSError:
		return False