import re
from itertools import zip_longest
from src.parsing.definitions import HEADERS, SOCIETAL_VALUE_NAMES, STRING_COLUMNS, EXCLUDED_KEYS_COUNTRY
from src.parsing.numeric_utils import parse_dynamic_numeric_value

# Caches
_bt_cache = None
_gp_cache = None
_pop_cache = None
_mk_cache = None
_rt_cache = None
_tg_cache = None
_cm_cache = None

tg_cumulative_store = {}

def clear_all_caches():
    global _bt_cache, _gp_cache, _pop_cache, _mk_cache, _rt_cache, _tg_cache, _cm_cache
    _bt_cache = _gp_cache = _pop_cache = _mk_cache = _rt_cache = _tg_cache = _cm_cache = None

def reset_cumulative_history():
    tg_cumulative_store.clear()
    clear_all_caches()

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
            if len(values) != len(HEADERS):
                if not warning_printed:
                    warning_printed = True
                    print(f"Column count mismatch: got {len(values)}, expected {len(HEADERS)}")
                current_record = None
                lines_after_tg = 99
                continue

            lines_after_tg = -1
            current_record = dict(zip(HEADERS, values))
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
    global _bt_cache
    if _bt_cache is not None:
        return _bt_cache
    pattern = re.compile(r"::BT:(\d+):(.*?):(\d+):(.*)")
    _bt_cache = [
        {"moment": 1 + int(m.group(1)), "building": m.group(2).strip(),
         "count": int(m.group(3)), "region": m.group(4).strip()}
        for m in pattern.finditer(data)
    ]
    return _bt_cache

def parse_data_goods_prices(data: str):
    global _gp_cache
    if _gp_cache is not None:
        return _gp_cache
    pattern = re.compile(r"::GP::(\d+):(.+?):(.+?):([\d.-]+)")
    _gp_cache = [
        {"moment": 1 + int(m.group(1)), "good": m.group(2).strip(),
         "region": m.group(3).strip(), "price": float(m.group(4))}
        for m in pattern.finditer(data) if 'Ocean' not in m.group(3)
    ]
    return _gp_cache

def parse_data_population(data: str):
    global _pop_cache
    if _pop_cache is not None:
        return _pop_cache
    pattern = re.compile(r"::POP::(\d+):(.+?):([\d.,MK]+)")
    parsed = []
    for m in pattern.finditer(data):
        parsed.append({
            "moment": 1 + int(m.group(1)),
            "region": m.group(2).strip(),
            "statistic": "Total Population",
            "population": parse_dynamic_numeric_value(m.group(3))
        })
    _pop_cache = parsed
    return _pop_cache

def parse_data_road_types(data: str):
    global _rt_cache
    if _rt_cache is not None:
        return _rt_cache
    pattern = re.compile(r"::RT::(\d+):(.+?):(.+?):(\d+):(\d+)")
    parsed = []
    for m in pattern.finditer(data):
        locs = int(m.group(4))
        locs_w_road = int(m.group(5))
        parsed.append({
            "moment": 1 + int(m.group(1)),
            "region": m.group(2).strip(),
            "road_type": m.group(3).strip(),
            "locations": locs,
            "locations_with_road": locs_w_road,
            "coverage_percentage": (locs_w_road / locs * 100) if locs > 0 else 0
        })
    _rt_cache = parsed
    return _rt_cache

def parse_data_markets(data: str):
    global _mk_cache
    if _mk_cache is not None:
        return _mk_cache
    pattern = re.compile(
        r"::MK::(\d+):(.+?):([\d.-]+):([\d.-]+):([\d.-]+):([\d.-]+):([\d.-]+):([\d.-]+):([\d.-]+):([\d.-]+):([\d.-]+):([\d.-]+):([\d.-]+)"
    )
    statistic_names = [
        "Food", "Food Stockpile", "Max Food Stockpile", "Food Stockpile Percent",
        "Monthly Food", "Monthly Food Balance", "Food Price", "Burgher Food Imports",
        "Burgher Food Exports", "Total Value Traded", "Merchant Capacity"
    ]
    parsed = []
    for m in pattern.finditer(data):
        moment = int(m.group(1)) + 1
        market_name = m.group(2).strip()
        vals = [float(v) for v in m.groups()[2:]]
        for name, v in zip(statistic_names, vals):
            parsed.append({"moment": moment, "region": market_name, "statistic": name, "value": v})
    _mk_cache = parsed
    return _mk_cache

def parse_data_country_metrics(data: str):
    global _cm_cache
    if _cm_cache is not None:
        return _cm_cache
    countries = parse_data_countries(data)
    transformed = []
    for r in countries:
        if r.get("num_locations", 0) <= 0:
            continue
        year = int(r["year"]) if r.get("year") else 0
        tag = r.get("tag", "")
        name = r.get("name", "")
        label = f"{name} ({tag})" if name and name != tag else tag

        debt = r.get("total_debt", 0.0)
        income = r.get("income", 0.0)
        if isinstance(debt, (int, float)) and isinstance(income, (int, float)):
            transformed.append({
                "moment": year, "region": label,
                "metric": "total_debt_over_income",
                "value": round(debt / income if income > 0.001 else 0.0, 4)
            })

        for k, v in r.items():
            if k not in EXCLUDED_KEYS_COUNTRY and isinstance(v, (int, float)):
                transformed.append({"moment": year, "region": label, "metric": k, "value": float(v)})
    _cm_cache = transformed
    return _cm_cache