import re

from src.parsing.definitions import COUNTRY_FIRST_HEADERS, SOCIETAL_VALUE_NAMES, STRING_COLUMNS, EXCLUDED_KEYS_COUNTRY, \
    market_stats
from src.parsing.numeric_utils import parse_dynamic_numeric_value

pattern_mk = re.compile(r"::MK::(\d+):([^:\r\n]+):([^\r\n]+)")
pattern_cr = re.compile(r"::CR::(\d+):([A-Za-z0-9_]+):([^\r\n]+)")

CREDIT_HEADERS = [
    "Balance",
    "Supply",
    "Supply - goods",
    "Supply - modifiers",
    "Lending quote",
    "Interest adjustment",
]

# Column count mismatch callback (hooked by UI)
_column_mismatch_callback = None

def set_column_mismatch_callback(cb):
    global _column_mismatch_callback
    _column_mismatch_callback = cb

# Caches
_bt_cache = None
_gp_cache = None
_pop_cache = None
_mk_cache = None
_rt_cache = None
_tg_cache = None
_cm_cache = None
_rloc_cache = None
_cr_cache = None
_crm_cache = None

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
    global _bt_cache, _gp_cache, _pop_cache, _mk_cache, _rt_cache, _tg_cache, _cm_cache, _rloc_cache, _cr_cache, _crm_cache
    _bt_cache = _gp_cache = _pop_cache = _mk_cache = _rt_cache = _tg_cache = _cm_cache = _rloc_cache = _cr_cache = _crm_cache = None

def reset_cumulative_history():
    tg_cumulative_store.clear()
    bt_cumulative_store.clear()
    gp_cumulative_store.clear()
    pop_cumulative_store.clear()
    rt_cumulative_store.clear()
    mk_cumulative_store.clear()
    region_locations_store.clear()
    cr_cumulative_store.clear()
    clear_all_caches()

def parse_data_region_locations(data: str):
    global _rloc_cache, region_locations_store
    if _rloc_cache is not None:
        return _rloc_cache
    pattern_loc = re.compile(r"::RLOC::(.*?):([\d.,]+)")
    for m in pattern_loc.finditer(data):
        region = m.group(1).strip()
        count = int(float(m.group(2).replace(',', '')))
        region_locations_store[region] = count
    _rloc_cache = region_locations_store
    return _rloc_cache

def get_region_locations():
    return region_locations_store

def parse_data_countries(data: str):
    global _tg_cache, tg_cumulative_store
    if _tg_cache is not None:
        return _tg_cache

    parsed_data = []
    current_record = None
    lines_after_tg = 16
    pending_chunks = []
    warning_printed = False

    def commit(rec):
        if rec is not None:
            for k, val in rec.items():
                if k not in STRING_COLUMNS:
                    rec[k] = parse_dynamic_numeric_value(val)
            parsed_data.append(rec)

    for line in data.splitlines():
        if '\x00' in line:
            line = line.replace('\x00', '')

        values = None
        if '::TG1::' in line:
            commit(current_record)
            current_record = None
            m = re.search(r'::TG1::(.*)', line)
            pending_chunks = [m.group(1).strip()] if m else []
            lines_after_tg = 99
            continue
        elif '::TG2::' in line and pending_chunks:
            m = re.search(r'::TG2::(.*)', line)
            if m: pending_chunks.append(m.group(1).strip())
            lines_after_tg = 99
            continue
        elif '::TG3::' in line and len(pending_chunks) == 2:
            m = re.search(r'::TG3::(.*)', line)
            if m: pending_chunks.append(m.group(1).strip())
            lines_after_tg = 99
            continue
        elif '::TG4::' in line and len(pending_chunks) == 3:
            m = re.search(r'::TG4::(.*)', line)
            if m:
                pending_chunks.append(m.group(1).strip())
                values = ":".join(pending_chunks).split(':')
            pending_chunks = []
        elif '::TG::' in line:
            commit(current_record)
            current_record = None
            m = re.search(r'::TG::(.*)', line)
            if m: values = m.group(1).strip().split(':')

        if values is not None:
            if len(values) != len(COUNTRY_FIRST_HEADERS):
                if not warning_printed:
                    warning_printed = True
                    print(f"Column count mismatch: got {len(values)}, expected {len(COUNTRY_FIRST_HEADERS)}")
                    if _column_mismatch_callback:
                        _column_mismatch_callback(len(values), len(COUNTRY_FIRST_HEADERS))
                current_record = None
                lines_after_tg = 99
                continue

            lines_after_tg = -1
            current_record = dict(zip(COUNTRY_FIRST_HEADERS, values))
        elif lines_after_tg <= 15:
            if current_record is None:
                lines_after_tg += 1
                continue
            m = re.search(r"(-?\d+(?:\.\d+)?)$", line)
            if m:
                current_record[SOCIETAL_VALUE_NAMES[lines_after_tg]] = float(m.group(1))
                if lines_after_tg == 15:
                    commit(current_record)
                    current_record = None
        lines_after_tg += 1

    commit(current_record)

    for record in parsed_data:
        yr = record.get("year")
        tag = record.get("tag")
        if yr and tag:
            tg_cumulative_store[(yr, tag)] = record

    all_records = sorted(tg_cumulative_store.values(), key=lambda r: int(r.get("year", 0)))
    _tg_cache = all_records
    return _tg_cache

def parse_data_building_types(data: str):
    global _bt_cache, bt_cumulative_store
    if _bt_cache is not None:
        return _bt_cache
    pattern_bt = re.compile(r"::BT:(\d+):(.*?):(\d+):(.*)")
    for m in pattern_bt.finditer(data):
        moment = int(m.group(1))
        building = m.group(2).strip()
        count = int(m.group(3))
        region = m.group(4).strip()
        bt_cumulative_store[(moment, region, building)] = count

    if not bt_cumulative_store:
        _bt_cache = []
        return _bt_cache

    all_moments = sorted(set(k[0] for k in bt_cumulative_store.keys()))
    all_regions = sorted(set(k[1] for k in bt_cumulative_store.keys()))
    all_buildings = sorted(set(k[2] for k in bt_cumulative_store.keys()))

    filled_data = []
    for m in all_moments:
        for reg in all_regions:
            for bld in all_buildings:
                cnt = bt_cumulative_store.get((m, reg, bld), 0)
                filled_data.append({
                    "moment": m,
                    "building": bld,
                    "count": cnt,
                    "region": reg
                })

    _bt_cache = filled_data
    return _bt_cache

def parse_data_goods_prices(data: str):
    global _gp_cache, gp_cumulative_store
    if _gp_cache is not None:
        return _gp_cache
    pattern_gp = re.compile(r"::GP::(\d+):(.+?):(.+?):([\d.-]+)")
    for m in pattern_gp.finditer(data):
        if 'Ocean' in m.group(3):
            continue
        moment = int(m.group(1))
        good = m.group(2).strip()
        region = m.group(3).strip()
        price = float(m.group(4))
        gp_cumulative_store[(moment, region, good)] = {
            "moment": moment, "good": good, "region": region, "price": price
        }
    _gp_cache = sorted(gp_cumulative_store.values(), key=lambda x: (x["moment"], x["region"], x["good"]))
    return _gp_cache

def parse_data_population(data: str):
    global _pop_cache, pop_cumulative_store
    if _pop_cache is not None:
        return _pop_cache
    pattern_pop = re.compile(r"::POP::(\d+):(.+?):([\d.,MK]+)")
    for m in pattern_pop.finditer(data):
        moment = int(m.group(1))
        region = m.group(2).strip()
        pop = parse_dynamic_numeric_value(m.group(3))
        pop_cumulative_store[(moment, region)] = {
            "moment": moment,
            "region": region,
            "statistic": "Total Population",
            "population": pop
        }
    _pop_cache = sorted(pop_cumulative_store.values(), key=lambda x: (x["moment"], x["region"]))
    return _pop_cache

def parse_data_road_types(data: str):
    global _rt_cache, rt_cumulative_store
    if _rt_cache is not None:
        return _rt_cache
    pattern_rt = re.compile(r"::RT::(\d+):(.+?):(.+?):(\d+):(\d+)")
    for m in pattern_rt.finditer(data):
        moment = int(m.group(1))
        region = m.group(2).strip()
        road_type = m.group(3).strip()
        locs = int(m.group(4))
        locs_w_road = int(m.group(5))
        rt_cumulative_store[(moment, region, road_type)] = {
            "moment": moment,
            "region": region,
            "road_type": road_type,
            "locations": locs,
            "locations_with_road": locs_w_road,
            "coverage_percentage": (locs_w_road / locs * 100) if locs > 0 else 0
        }
    _rt_cache = sorted(rt_cumulative_store.values(), key=lambda x: (x["moment"], x["region"], x["road_type"]))
    return _rt_cache

def parse_data_markets(data: str):
    global _mk_cache, mk_cumulative_store
    if _mk_cache is not None:
        return _mk_cache

    for m in pattern_mk.finditer(data):
        moment = int(m.group(1))
        market_name = m.group(2).strip()
        raw_vals = m.group(3).strip().split(':')
        vals = []
        for v in raw_vals:
            try:
                vals.append(float(v))
            except (ValueError, TypeError):
                pass

        stat_map = dict(zip(market_stats, vals))
        loc_count = float(stat_map.get("Locations", 0.0))

        for name, v in stat_map.items():
            mk_cumulative_store[(moment, market_name, name)] = {
                "moment": moment,
                "region": market_name,
                "market": market_name,
                "statistic": name,
                "value": v,
                "locations": loc_count
            }

    # Ensure all entries in cumulative store have their location counts filled
    loc_lookup = {}
    for (m, reg, stat), record in mk_cumulative_store.items():
        if stat == "Locations":
            loc_lookup[(m, reg)] = record.get("value", 0.0)

    for (m, reg, _), record in mk_cumulative_store.items():
        if not record.get("locations") and (m, reg) in loc_lookup:
            record["locations"] = loc_lookup[(m, reg)]

    _mk_cache = sorted(mk_cumulative_store.values(), key=lambda x: (x["moment"], x["region"], x["statistic"]))
    return _mk_cache

def parse_data_country_metrics(data: str):
    global _cm_cache
    if _cm_cache is not None:
        return _cm_cache
    countries = parse_data_countries(data)
    transformed = []
    for r in countries:
        locs_val = r.get("locations") or r.get("num_locations") or 0
        try:
            country_locations = float(locs_val)
        except (ValueError, TypeError):
            country_locations = 0.0

        if country_locations <= 0:
            continue

        year = int(r["year"]) if r.get("year") else 0
        tag = r.get("tag", "")
        name = r.get("name", "")
        label = f"{name} ({tag})" if name and name != tag else tag

        debt = r.get("total_debt", 0.0)
        income = r.get("income", 0.0)
        if isinstance(debt, (int, float)) and isinstance(income, (int, float)):
            transformed.append({
                "moment": year,
                "region": label,
                "country": label,
                "metric": "total_debt_over_income",
                "country_metric": "total_debt_over_income",
                "value": round(debt / income if income > 0.001 else 0.0, 4),
                "locations": country_locations
            })

        for k, v in r.items():
            if k not in EXCLUDED_KEYS_COUNTRY and isinstance(v, (int, float)):
                transformed.append({
                    "moment": year,
                    "region": label,
                    "country": label,
                    "metric": k,
                    "country_metric": k,
                    "value": float(v),
                    "locations": country_locations
                })
    _cm_cache = transformed
    return _cm_cache

def parse_data_credit_raw(data: str):
    """Parses raw credit logs into records suitable for CSV export and storage."""
    global _cr_cache, cr_cumulative_store
    if _cr_cache is not None:
        return _cr_cache

    for m in pattern_cr.finditer(data):
        moment = int(m.group(1))
        tag = m.group(2).strip()
        raw_vals = m.group(3).strip().split(':')

        record = {"moment": moment, "tag": tag, "country": tag}
        for name, val_str in zip(CREDIT_HEADERS, raw_vals):
            record[name] = parse_dynamic_numeric_value(val_str)

        cr_cumulative_store[(moment, tag)] = record

    _cr_cache = sorted(cr_cumulative_store.values(), key=lambda x: (x["moment"], x["tag"]))
    return _cr_cache

# Alias for backwards compatibility
parse_data_credit = parse_data_credit_raw

def parse_data_credit_metrics(data: str):
    """Transforms parsed credit logs into generic country metrics for plotting."""
    global _crm_cache
    if _crm_cache is not None:
        return _crm_cache

    parse_data_credit_raw(data)
    parse_data_countries(data)

    transformed = []
    for (moment, tag), record in cr_cumulative_store.items():
        country_rec = tg_cumulative_store.get((moment, tag))
        name = country_rec.get("name", "") if country_rec else ""
        label = f"{name} ({tag})" if name and name != tag else tag

        locs = 0.0
        if country_rec:
            loc_val = country_rec.get("locations") or country_rec.get("num_locations") or 0
            try:
                locs = float(loc_val)
            except (ValueError, TypeError):
                locs = 0.0

        for header in CREDIT_HEADERS:
            val = record.get(header)
            if isinstance(val, (int, float)):
                transformed.append({
                    "moment": moment,
                    "region": label,
                    "country": label,
                    "tag": tag,
                    "credit_metric": header,
                    "metric": header,
                    "value": float(val),
                    "locations": locs
                })

    _crm_cache = sorted(transformed, key=lambda x: (x["moment"], x["country"], x["credit_metric"]))
    return _crm_cache

def parse_all_logs(data: str):
    """Parses incoming log data into ALL cumulative stores simultaneously."""
    if not data:
        return
    parse_data_region_locations(data)
    parse_data_countries(data)
    parse_data_country_metrics(data)
    parse_data_credit_raw(data)
    parse_data_credit_metrics(data)
    parse_data_building_types(data)
    parse_data_goods_prices(data)
    parse_data_markets(data)
    parse_data_population(data)
    parse_data_road_types(data)