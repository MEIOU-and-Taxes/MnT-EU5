from src.constants import STR_ALL_REGIONS
from src.parsing.transformers.region import parse_data_regional_metrics
from src.parsing.transformers.market import parse_data_market_metrics
from src.parsing.transformers.country import parse_data_country_metrics

CM_CONFIG = {
    "parser": parse_data_country_metrics,
    "category_key": "country_metric",
    "value_key": "value",
    "category_label": "Metric:",
    "all_category_str": None,
    "value_label": "Value",
    "add_zero_start": False,
    "has_region_filter": True,
    "entity_key": "country",
    "region_label": "Country:",
    "all_region_str": "All countries",
}

MK_CONFIG = {
    "parser": parse_data_market_metrics,
    "category_key": "statistic",
    "value_key": "value",
    "category_label": "Statistic:",
    "all_category_str": None,
    "value_label": "Value",
    "add_zero_start": False,
    "has_region_filter": True,
    "entity_key": "market",
    "region_label": "Market:",
    "all_region_str": "All markets",
}

REGIONAL_CONFIG = {
    "parser": parse_data_regional_metrics,
    "category_key": "regional_metric",
    "value_key": "value",
    "category_label": "Metric:",
    "all_category_str": None,
    "value_label": "Value",
    "add_zero_start": False,
    "has_region_filter": True,
    "entity_key": "region",
    "region_label": "Region:",
    "all_region_str": STR_ALL_REGIONS,
}