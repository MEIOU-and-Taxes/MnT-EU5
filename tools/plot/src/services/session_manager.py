import gzip
import os
import pickle
from datetime import datetime
from src.parsing import log_parser

def _safe_int(val):
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return 0

def save_session(filepath, raw_data, logs, chart_filter_memory, current_chart_title) -> bool:
    if not raw_data:
        return False
    session = {
        "version": 3,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "data": raw_data,
        "logs": logs,
        "cumulative_stores": {
            "tg": {f"{_safe_int(k[0])}:{k[1]}": v for k, v in log_parser.tg_cumulative_store.items()},
            "cr": {f"{_safe_int(k[0])}:{k[1]}": v for k, v in log_parser.cr_cumulative_store.items()},
            "bt": {f"{_safe_int(k[0])}:{k[1]}:{k[2]}": v for k, v in log_parser.bt_cumulative_store.items()},
            "gp": {f"{_safe_int(k[0])}:{k[1]}:{k[2]}": v for k, v in log_parser.gp_cumulative_store.items()},
            "pop": {f"{_safe_int(k[0])}:{k[1]}": v for k, v in log_parser.pop_cumulative_store.items()},
            "rt": {f"{_safe_int(k[0])}:{k[1]}:{k[2]}": v for k, v in log_parser.rt_cumulative_store.items()},
            "mk": {f"{_safe_int(k[0])}:{k[1]}:{k[2]}": v for k, v in log_parser.mk_cumulative_store.items()},
            "rloc": log_parser.region_locations_store,
        },
        "chart_filter_memory": chart_filter_memory,
        "current_chart": current_chart_title
    }
    with gzip.open(filepath, "wb") as f:
        pickle.dump(session, f)
    return True

def load_session(filepath) -> dict:
    if not os.path.exists(filepath):
        return None
    with gzip.open(filepath, "rb") as f:
        session = pickle.load(f)

    log_parser.reset_cumulative_history()

    stores = session.get("cumulative_stores", {})
    for k_str, val in stores.get("tg", {}).items():
        p = k_str.split(":", 1)
        if len(p) == 2:
            log_parser.tg_cumulative_store[(_safe_int(p[0]), p[1])] = val

    for k_str, val in stores.get("cr", {}).items():
        p = k_str.split(":", 1)
        if len(p) == 2:
            log_parser.cr_cumulative_store[(_safe_int(p[0]), p[1])] = val

    for k_str, val in stores.get("bt", {}).items():
        p = k_str.split(":", 2)
        if len(p) == 3:
            log_parser.bt_cumulative_store[(_safe_int(p[0]), p[1], p[2])] = val

    for k_str, val in stores.get("gp", {}).items():
        p = k_str.split(":", 2)
        if len(p) == 3:
            log_parser.gp_cumulative_store[(_safe_int(p[0]), p[1], p[2])] = val

    for k_str, val in stores.get("pop", {}).items():
        p = k_str.split(":", 1)
        if len(p) == 2:
            log_parser.pop_cumulative_store[(_safe_int(p[0]), p[1])] = val

    for k_str, val in stores.get("rt", {}).items():
        p = k_str.split(":", 2)
        if len(p) == 3:
            log_parser.rt_cumulative_store[(_safe_int(p[0]), p[1], p[2])] = val

    for k_str, val in stores.get("mk", {}).items():
        p = k_str.split(":", 2)
        if len(p) == 3:
            log_parser.mk_cumulative_store[(_safe_int(p[0]), p[1], p[2])] = val

    log_parser.region_locations_store.update(stores.get("rloc", {}))

    log_parser.clear_all_caches()
    return session