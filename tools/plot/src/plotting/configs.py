from src.constants import STR_ALL_BUILDINGS, STR_ALL_GOODS, STR_ALL_ROAD_TYPES, STR_ALL_REGIONS
from src.parsing.log_parser import (
    parse_data_building_types, parse_data_goods_prices, parse_data_markets,
    parse_data_population, parse_data_road_types, parse_data_country_metrics
)

BT_CONFIG = {
    "parser": parse_data_building_types,
    "category_key": "building",
    "value_key": "count",
    "category_label": "Building Type:",
    "all_category_str": STR_ALL_BUILDINGS,
    "value_label": "Count",
    "add_zero_start": True,
    "has_region_filter": True,
    "entity_key": "region",
    "region_label": "Region:",
    "all_region_str": STR_ALL_REGIONS,
}

GP_CONFIG = {
    "parser": parse_data_goods_prices,
    "category_key": "good",
    "value_key": "price",
    "category_label": "Good:",
    "all_category_str": STR_ALL_GOODS,
    "value_label": "Price",
    "add_zero_start": False,
    "ignore_zeros": True,
    "has_region_filter": True,
    "entity_key": "region",
    "region_label": "Region:",
    "all_region_str": STR_ALL_REGIONS,
}

MK_CONFIG = {
    "parser": parse_data_markets,
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

POP_CONFIG = {
    "parser": parse_data_population,
    "category_key": "statistic",
    "value_key": "population",
    "category_label": "Statistic:",
    "all_category_str": None,
    "value_label": "Population",
    "add_zero_start": False,
    "ignore_zeros": True,
    "has_region_filter": True,
    "entity_key": "region",
    "region_label": "Region:",
    "all_region_str": STR_ALL_REGIONS,
}

RT_CONFIG = {
    "parser": parse_data_road_types,
    "category_key": "road_type",
    "value_key": "coverage_percentage",
    "category_label": "Road Type:",
    "all_category_str": STR_ALL_ROAD_TYPES,
    "value_label": "Coverage Percentage",
    "add_zero_start": True,
    "y_axis_limits": (0, 100),
    "has_region_filter": True,
    "entity_key": "region",
    "region_label": "Region:",
    "all_region_str": STR_ALL_REGIONS,
}

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