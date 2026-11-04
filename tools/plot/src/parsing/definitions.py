"""Column and metadata definitions for log parsing."""

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
    "navy_tradition", "locations", "control_avg", "proximity_avg", "dev_avg", "prosperity_avg", "market_access_avg", "towns", "cities", "megalopolises", "winter_pow_avg", "bank_interest", "trade_income", "monthly balance", "monthly expenses", "trade_income_perc", "Loan interest"
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
    "Burgher Trade Capacity", "Stockpile capacity", "Locations"
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
