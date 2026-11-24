"""Column and metadata definitions for log parsing."""

# Multipliers for series that are logged in smaller units (e.g. population numbers logged in thousands)
SERIES_CONFIG_MULTIPLIERS = [
    {"type": "Peasants", "multiplier": 1000},
    {"type": "Burghers", "multiplier": 1000},
    {"type": "Clergy", "multiplier": 1000},
    {"type": "Laborers", "multiplier": 1000},
    {"type": "Nobles", "multiplier": 1000},
    {"type": "Slaves", "multiplier": 1000},
    {"type": "Soldiers", "multiplier": 1000},
    {"type": "Tribesmen", "multiplier": 1000},
    {"type": "Unemployed peasants", "multiplier": 1000},
    {"type": "Unemployed burghers", "multiplier": 1000},
    {"type": "Unemployed clergy", "multiplier": 1000},
    {"type": "Unemployed laborers", "multiplier": 1000},
    {"type": "Unemployed nobles", "multiplier": 1000},
    {"type": "Unemployed slaves", "multiplier": 1000},
    {"type": "Unemployed soldiers", "multiplier": 1000},
    {"type": "Unemployed tribesmen", "multiplier": 1000},
    {"type": "Army levy size", "multiplier": 1000},
    {"type": "Navy levy size", "multiplier": 1000},
    {"type": "Max population", "multiplier": 1000},
    {"type": "Unfilled jobs", "multiplier": -1},
    {"type": "Food consumption", "multiplier": -1},
]

SERIES_MULTIPLIERS = {item["type"].strip().lower(): float(item["multiplier"]) for item in SERIES_CONFIG_MULTIPLIERS}


def get_series_multiplier(metric_name: str) -> float:
    """Returns the scaling multiplier for a metric (default: 1.0)."""
    if not metric_name:
        return 1.0
    return SERIES_MULTIPLIERS.get(metric_name.strip().lower(), 1.0)


COUNTRY_FIRST_HEADERS = [
    "year", "tag", "name", "capital_area", "country_type", "government_type", "income", "current_research",
    "has_feudalism", "has_legalism", "has_meritocracy", "has_renaissance", "has_banking", "has_professional_armies",
    "has_new_world", "has_printing_press", "has_pike_and_shot", "has_confessionalism", "has_global_trade",
    "has_artillery_institution", "has_manufactories", "has_scientific_revolution", "has_military_revolution",
    "has_enlightenment", "has_industrialization", "has_levee_en_masse",
    "nobles_income_lost", "clergy_income_lost", "burghers_income_lost", "peasants_income_lost", "dhimmi_income_lost", "tribes_income_lost", "cossacks_income_lost",
    "nobles_gold", "clergy_gold", "burghers_gold", "peasants_gold", "dhimmi_gold", "tribes_gold", "cossacks_gold",
    "nobles_balance", "clergy_balance", "burghers_balance", "peasants_balance", "dhimmi_balance", "tribes_balance", "cossacks_balance",
    "nobles_income_before_tax", "clergy_income_before_tax", "burghers_income_before_tax", "peasants_income_before_tax", "dhimmi_income_before_tax", "tribes_income_before_tax", "cossacks_income_before_tax",
    "nobles_tax", "clergy_tax", "burghers_tax", "peasants_tax", "dhimmi_tax", "tribes_tax", "cossacks_tax",
    "nobles_expense", "clergy_expense", "burghers_expense", "peasants_expense", "dhimmi_expense", "tribes_expense", "cossacks_expense",
    "nobles_max_tax", "clergy_max_tax", "burghers_max_tax", "peasants_max_tax", "dhimmi_max_tax", "tribes_max_tax", "cossacks_max_tax",
    "nobles_relative_power", "clergy_relative_power", "burghers_relative_power", "peasants_relative_power", "dhimmi_relative_power", "tribes_relative_power", "cossacks_relative_power",
    "nobles_satisfaction", "clergy_satisfaction", "burghers_satisfaction", "peasants_satisfaction", "dhimmi_satisfaction", "tribes_satisfaction", "cossacks_satisfaction",
    "nobles_taxable_income", "clergy_taxable_income", "burghers_taxable_income", "peasants_taxable_income", "dhimmi_taxable_income", "tribes_taxable_income", "cossacks_taxable_income",
    "nobles_population", "clergy_population", "burghers_population", "peasants_population", "dhimmi_population", "tribes_population", "cossacks_population",
    "num_loans", "total_debt", "remaining_loan_capacity", "trade_balance", "is_bankrupt", "regency_type", "parliament_type", "parliament_debate_estate", "parliament_debate_name", "parliament_issue_support",
    "rank_level", "score", "num_artists", "great_power_rank", "great_power_score", "living_characters", "num_works_of_art",
    "num_characters", "power_projection", "num_locations", "has_active_rebels", "army_levy_potential", "army_levy_power",
    "army_size", "avg_army_experience", "avg_navy_experience", "num_forts", "expected_army_size", "expected_navy_size",
    "fort_limit", "max_manpower", "max_sailors", "military_strength", "naval_range", "navy_levy_power", "navy_size",
    "navy_strength", "raised_levy_strength", "raw_army_levy_power", "raw_navy_levy_power", "regular_army_size",
    "total_ships", "crown_power", "avg_literacy", "cultural_capacity", "cultural_unity", "primary_culture_percentage",
    "primary_religion_percentage", "total_coastal_population", "total_culture_capacity_used", "economical_base",
    "estimated_monthly_income", "estimated_monthly_income_trade_tax", "num_starving_provinces", "num_institutions_embraced",
    "overlord_tag", "num_active_cb_targets", "annexation_progress", "diplomatic_range", "liberty_desire",
    "max_diplomatic_capacity", "max_diplomats", "num_diplomats", "num_subjects", "subject_loyalty", "used_diplomatic_capacity",
    "gold", "stability", "government_power", "prestige", "war_exhaustion", "manpower", "sailors", "inflation", "army_tradition",
    "navy_tradition", "locations", "control_avg", "proximity_avg", "dev_avg", "prosperity_avg", "market_access_avg", "towns", "cities", "megalopolises", "winter_pow_avg", "bank_interest", "trade_income", "monthly balance", "monthly expenses", "trade_income_perc", "Loan interest", "Population"
]

SOCIETAL_VALUE_NAMES = [
    "centralization_vs_decentralization", "traditionalist_vs_innovative", "spiritualist_vs_humanist",
    "aristocracy_vs_plutocracy", "serfdom_vs_free_subjects", "mercantilism_vs_free_trade",
    "belligerent_vs_conciliatory", "quality_vs_quantity", "offensive_vs_defensive", "land_vs_naval",
    "capital_economy_vs_traditional_economy", "individualism_vs_communalism", "outward_vs_inward",
    "sinicized_vs_unsinicized", "absolutism_vs_liberalism", "mysticism_vs_jurisprudence"
]

STRING_COLUMNS = {
    "tag", "name", "capital_area", "country_type", "government_type", "current_research",
    "regency_type", "parliament_name", "parliament_type", "parliament_debate_estate",
    "parliament_debate_name", "overlord_tag"
}

EXCLUDED_KEYS_COUNTRY = {
    "year", "tag", "name", "capital_area", "country_type", "government_type",
    "current_research", "regency_type", "parliament_name", "parliament_type",
    "parliament_debate_estate", "parliament_debate_name", "overlord_tag"
}

market_stats = [
    "Food", "Food Stockpile", "Max Food Stockpile", "Food Stockpile Perc",
    "Monthly Food", "Food Price", "Total Value Traded", "Merchant Capacity",
    "Burgher Trade Capacity", "Stockpile capacity", "Locations", "Population"
]

CREDIT_HEADERS = [
    "Credit balance",
    "Credit supply",
    "Credit supply - goods",
    "Credit supply - modifiers",
    "Credit demand",
    "Lending quote",
    "Interest adjustment",
]

POPULATION_HEADERS = [
    # Locations - float
    "Total population",
    "Average literacy",
    "Average satisfaction",
    "Average prosperity",
    "Average development",
    "Food consumption",
    "Food production",
    "Garrison strength",
    "Average garrison percentage",
    "Max population", # send sorted
    "Net building profit",
    "Num works of art",
    "Population vs population capacity",
    "Tax base",
    "Works of art star rating",
    "Average market access",
    "Average max control",
    "Max garrison strength",
    "Average migration attraction",
    "Monthly conversion",
    "Num army constructions",
    "Num navy constructions",
    "Average peasant enfranchisement",
    "Average proximity",
    "Average winter power",
    "Average control",
    "Average cultural unity",
    "Average political power fraction",
    "Average religious unity",
    
    "Tribes power",
    "Peasants power",
    "Clergy power",
    "Cossacks power",
    "Dhimmi power",
    "Burghers power",
    "Nobles power",
    "Crown power", # only trivial values
    "Tribes relative power",
    "Peasants relative power",
    "Clergy relative power",
    "Cossacks relative power",
    "Dhimmi relative power",
    "Burghers relative power",
    "Nobles relative power",
    "Crown relative power", # only trivial values
    
    # Locations - bool
    "Forts",
    "Volcanoes", # constant
    "Earthquakes", # constant
    "Combat",
    "Cities",
    "Frozen locations",
    "Holdings of any religious order",
    "Locations in promoted industry area",
    "Locations looted",
    "Ports",
    
    # Provinces - floats
    "Army levy percentage",
    "Army levy size",
    "Average integration",
    "Food",
    "Food percentage",
    "Wealth (Potential tax base)",
    "Max food",
    "Monthly food production",
    "Navy levy percentage",
    "Navy levy size",
    "Peasants",
    "Burghers",
    "Clergy",
    "Laborers",
    "Nobles",
    "Slaves",
    "Soldiers",
    "Tribesmen",
    # some are both positive and negative
    "Unemployed peasants",
    "Unemployed burghers",
    "Unemployed clergy",
    "Unemployed laborers",
    "Unemployed nobles",
    "Unemployed slaves",
    "Unemployed soldiers",
    "Unemployed tribesmen",

    "Rebel progress",
    "Unfilled jobs",
    "Unfilled jobs percentage",
    # Provinces - bool
    "Immigration destinations (provinces)",
    "Provinces having promotable institution spawns",
    "Provinces starving",
    # Provinces - special
    "Immigration destinations (locations)",
    "Locations starving",
]


