"""Column and metadata definitions for log parsing."""

COUNTRY_FIRST_HEADERS = [
    "Year", "Tag", "Name", "Capital area", "Country type", "Government type", "Income", "Current research",
    "Has feudalism", "Has legalism", "Has meritocracy", "Has renaissance", "Has banking", "Has professional armies",
    "Has new world", "Has printing press", "Has pike and shot", "Has confessionalism", "Has global trade",
    "Has artillery institution", "Has manufactories", "Has scientific revolution", "Has military revolution",
    "Has enlightenment", "Has industrialization", "Has levee en masse",
    "Nobles income lost", "Clergy income lost", "Burghers income lost", "Peasants income lost", "Dhimmi income lost", "Tribes income lost", "Cossacks income lost",
    "Nobles gold", "Clergy gold", "Burghers gold", "Peasants gold", "Dhimmi gold", "Tribes gold", "Cossacks gold",
    "Nobles balance", "Clergy balance", "Burghers balance", "Peasants balance", "Dhimmi balance", "Tribes balance", "Cossacks balance",
    "Nobles income before tax", "Clergy income before tax", "Burghers income before tax", "Peasants income before tax", "Dhimmi income before tax", "Tribes income before tax", "Cossacks income before tax",
    "Nobles tax", "Clergy tax", "Burghers tax", "Peasants tax", "Dhimmi tax", "Tribes tax", "Cossacks tax",
    "Nobles expense", "Clergy expense", "Burghers expense", "Peasants expense", "Dhimmi expense", "Tribes expense", "Cossacks expense",
    "Nobles max tax", "Clergy max tax", "Burghers max tax", "Peasants max tax", "Dhimmi max tax", "Tribes max tax", "Cossacks max tax",
    "Nobles relative power", "Clergy relative power", "Burghers relative power", "Peasants relative power", "Dhimmi relative power", "Tribes relative power", "Cossacks relative power",
    "Nobles satisfaction", "Clergy satisfaction", "Burghers satisfaction", "Peasants satisfaction", "Dhimmi satisfaction", "Tribes satisfaction", "Cossacks satisfaction",
    "Nobles taxable income", "Clergy taxable income", "Burghers taxable income", "Peasants taxable income", "Dhimmi taxable income", "Tribes taxable income", "Cossacks taxable income",
    "Nobles population", "Clergy population", "Burghers population", "Peasants population", "Dhimmi population", "Tribes population", "Cossacks population",
    "Num loans", "Total debt", "Remaining loan capacity", "Trade balance", "Is bankrupt", "Regency type", "Parliament type", "Parliament debate estate", "Parliament debate name", "Parliament issue support",
    "Rank level", "Score", "Num artists", "Great power rank", "Great power score", "Living characters", "Num works of art",
    "Num characters", "Power projection", "Num locations", "Has active rebels", "Army levy potential", "Army levy power",
    "Army size", "Avg army experience", "Avg navy experience", "Num forts", "Expected army size", "Expected navy size",
    "Fort limit", "Max manpower", "Max sailors", "Military strength", "Naval range", "Navy levy power", "Navy size",
    "Navy strength", "Raised levy strength", "Raw army levy power", "Raw navy levy power", "Regular army size",
    "Total ships", "Crown power", "Avg literacy", "Cultural capacity", "Cultural unity", "Primary culture percentage",
    "Primary religion percentage", "Total coastal population", "Total culture capacity used", "Economical base",
    "Estimated monthly income", "Estimated monthly income trade tax", "Num starving provinces", "Num institutions embraced",
    "Overlord tag", "Num active cb targets", "Annexation progress", "Diplomatic range", "Liberty desire",
    "Max diplomatic capacity", "Max diplomats", "Num diplomats", "Num subjects", "Subject loyalty", "Used diplomatic capacity",
    "Gold", "Stability", "Government power", "Prestige", "War exhaustion", "Manpower", "Sailors", "Inflation", "Army tradition",
    "Navy tradition", "Locations", "Control avg", "Proximity avg", "Dev avg", "Prosperity avg", "Market access avg", "Towns", "Cities", "Megalopolises", "Winter pow avg", "Bank interest", "Trade income", "Monthly balance", "Monthly expenses", "Trade income perc", "Loan interest", "Population"
]

SOCIETAL_VALUE_NAMES = [
    "Centralization vs decentralization", "Traditionalist vs innovative", "Spiritualist vs humanist",
    "Aristocracy vs plutocracy", "Serfdom vs free subjects", "Mercantilism vs free trade",
    "Belligerent vs conciliatory", "Quality vs quantity", "Offensive vs defensive", "Land vs naval",
    "Capital economy vs traditional economy", "Individualism vs communalism", "Outward vs inward",
    "Sinicized vs unsinicized", "Absolutism vs liberalism", "Mysticism vs jurisprudence"
]

STRING_COLUMNS = {
    "Tag", "Name", "Capital area", "Country type", "Government type", "Current research",
    "Regency type", "Parliament name", "Parliament type", "Parliament debate estate",
    "Parliament debate name", "Overlord tag"
}

EXCLUDED_KEYS_COUNTRY = {
    "Year", "Tag", "Name", "Capital area", "Country type", "Government type",
    "Current research", "Regency type", "Parliament name", "Parliament type",
    "Parliament debate estate", "Parliament debate name", "Overlord tag"
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
    "Average population percentage",
    "Wealth (Potential tax base)",
    "Tax base",
    "Works of art star rating",
    "Average market access",
    "Average control", # empty
    "Average max control",
    "Max garrison strength",
    "Average migration attraction",
    "Monthly conversion",
    "Num army constructions",
    "Num navy constructions",
    "Average peasant enfranchisement",
    "Average proximity",
    "Average winter power",
    "Average local control",
    "Average local cultural unity",
    "Average local political power fraction",
    "Average local religious unity",
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
]