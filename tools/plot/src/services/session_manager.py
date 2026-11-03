import gzip
import os
import pickle
from datetime import datetime
from src.parsing import log_parser

def save_session(filepath, raw_data, logs, chart_filter_memory, current_chart_title) -> bool:
    if not raw_data:
        return False
    session = {
        "version": 1,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "data": raw_data,
        "logs": logs,
        "cumulative_store": {f"{int(k[0])}:{k[1]}": v for k, v in log_parser.tg_cumulative_store.items()},
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

    log_parser.tg_cumulative_store.clear()
    for k_str, val in session.get("cumulative_store", {}).items():
        parts = k_str.split(":", 1)
        if len(parts) == 2:
            log_parser.tg_cumulative_store[(int(parts[0]), parts[1])] = val

    log_parser.clear_all_caches()
    return session