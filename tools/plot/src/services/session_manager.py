import gzip
import os
import pickle
from datetime import datetime

import src.parsing.stores


def _safe_int(val):
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return 0

def save_session(filepath, raw_data, logs, chart_filter_memory, current_chart_title, session_name="") -> bool:
    if not raw_data:
        return False
    session = {
        "version": 3,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "session_name": session_name,
        "data": raw_data,
        "logs": logs,
        "cumulative_stores": {
            "tg": {f"{_safe_int(k[0])}:{k[1]}": v for k, v in src.parsing.stores.tg_cumulative_store.items()},
            "cr": {f"{_safe_int(k[0])}:{k[1]}": v for k, v in src.parsing.stores.cr_cumulative_store.items()},
            "bt": {f"{_safe_int(k[0])}:{k[1]}:{k[2]}": v for k, v in src.parsing.stores.bt_cumulative_store.items()},
            "gp": {f"{_safe_int(k[0])}:{k[1]}:{k[2]}": v for k, v in src.parsing.stores.gp_cumulative_store.items()},
            "pop": {f"{_safe_int(k[0])}:{k[1]}": v for k, v in src.parsing.stores.pop_cumulative_store.items()},
            "rt": {f"{_safe_int(k[0])}:{k[1]}:{k[2]}": v for k, v in src.parsing.stores.rt_cumulative_store.items()},
            "mk": {f"{_safe_int(k[0])}:{k[1]}:{k[2]}": v for k, v in src.parsing.stores.mk_cumulative_store.items()},
            "rloc": src.parsing.stores.region_locations_store,
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

    src.parsing.stores.reset_cumulative_history()

    stores = session.get("cumulative_stores", {})
    for k_str, val in stores.get("tg", {}).items():
        p = k_str.split(":", 1)
        if len(p) == 2:
            src.parsing.stores.tg_cumulative_store[(_safe_int(p[0]), p[1])] = val

    for k_str, val in stores.get("cr", {}).items():
        p = k_str.split(":", 1)
        if len(p) == 2:
            src.parsing.stores.cr_cumulative_store[(_safe_int(p[0]), p[1])] = val

    for k_str, val in stores.get("bt", {}).items():
        p = k_str.split(":", 2)
        if len(p) == 3:
            src.parsing.stores.bt_cumulative_store[(_safe_int(p[0]), p[1], p[2])] = val

    for k_str, val in stores.get("gp", {}).items():
        p = k_str.split(":", 2)
        if len(p) == 3:
            src.parsing.stores.gp_cumulative_store[(_safe_int(p[0]), p[1], p[2])] = val

    for k_str, val in stores.get("pop", {}).items():
        p = k_str.split(":", 1)
        if len(p) == 2:
            src.parsing.stores.pop_cumulative_store[(_safe_int(p[0]), p[1])] = val

    for k_str, val in stores.get("rt", {}).items():
        p = k_str.split(":", 2)
        if len(p) == 3:
            src.parsing.stores.rt_cumulative_store[(_safe_int(p[0]), p[1], p[2])] = val

    for k_str, val in stores.get("mk", {}).items():
        p = k_str.split(":", 2)
        if len(p) == 3:
            src.parsing.stores.mk_cumulative_store[(_safe_int(p[0]), p[1], p[2])] = val

    src.parsing.stores.region_locations_store.update(stores.get("rloc", {}))

    src.parsing.stores.clear_all_caches()
    return session