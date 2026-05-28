# Release 

### Initial test-release v0.1

Date: 21/05/2026

#### Features

- RGOs are replaced by buildings
  - More in a separate section below
- Naval levies  
  - Ship Building advance in age of traditions also unlocks Levy cog  
  - Levy cog, burgher levy appearing in locations having a wharf, scales with 0.2% of burghers  
  - Add new naval levies for later ages  
- Map modes:  
  - Market access (besides Markets map mode), where it is red at \<50% and green at 100%  
  - Missing control (difference between location control & max control)  
  - Max control  
  - Max control with location rank (can distinguish locations having towns & cities)  
  - Noble %, Burgher %, Laborer %, Peasant %  
  - Market food balance  
  - Market food stockpile
- Centers of Importance:
  - Added back the feature from older M&T version in a refactored version, 4 center tiers (local, regional, continental, world) for the 4 categories (trade, production, culture, education)
  - Each type has an associated score dependent on multiple factors and an absolute minimum threshold per tier.
  - Additionally, per geographical area only one center of each tier can exist.
  - Each location center tier gives bonuses to the location.
- Goods Domestic Production (proxy for GDP goods domestic product ), sum of goods value * amount

#### RGO Substitution
  - RGOs are fully replaced by buildings
  - Basegame RGO sizes hard-locked to zero by removing all base RGO size
  - Added new RGO replacement buildings, localized them, gave them the pictures of the previous RGOs
  - Buildings that have similar functionality as RGOs are now merged
    - E.g. clay/sand pits, Lumbermills, fruit orchards etc. got merged into the RGO-building
  - Balance changes done with calculation in excel spreadsheet, balance is still a bit rough but should mostly work fine
  - Adapted global RGO size modifiers and RGO ouput modifiers to both affect the maximum amount available of our RGO buildings in Locations
  - Avoided promoting tribal pops to fill RGO vacancies at the start

#### Bugfixes

- Fix diplomatic spending not transferring gold to nobles estate
- Stability map mode works
- Backend error fixes 

#### Balancing

- Crown power now increases percent of building upkeep paid by the state from a base of 0%: +1% CP = +1% Upkeep.
- Estates pay the share of building maintenance the crown does not, split across estates by estate power. Fortifications remain fully crown-paid.
- Estates now pay their proportional share of inflation-driven maintenance costs on shared buildings.
- Estate-assigned buildings have goods-based maintenance production methods and their full cost, including inflation, is paid entirely by the owning estate.
- Estate building tooltips now show actual computed upkeep with a full goods breakdown.
- Reduced use of masonry by granaries.
- Reduced use of tools by lumber mills.
- Higher literacy lowers stability.
- Peasant percentage improves stability.
- Buffed cabinet stability improving action.
- Stability effects prosperity negatively as well as positively.
- Reduced stability cost of destroying markets.
- Reduced stability cost of revoking privileges.
- Made hiring new characters scale somewhat less with income.
- Local population growth removed from having positive food.
- Major vassal swarm nerf, vassals will now require managing and will use their full power to consider their loyalty.
- Capital Location gives no max control or population capacity anymore.
- Remove enslavement of all non-state-religion pops from Muslim countries on game startup
- Tribes estate satisfaction now goes down proportional to average development
- Block tribal governments (tribes and steppe hordes) from settling their tribes
- Tribal strongholds privilege now improves rural control instead of making it worse
- AI now has better non-royal marriage logic so that dynasties don't die out nearly as often due to refusal to wed

##### Diplomacy

- Steal map’s antagonism bomb will not impact the robbed tag, but the discovered place  
- Sabotage reputation spy network cost: 5 → 10  
- Sow discontent & Corrupt officials diplomatic actions’ cost in gold will scale 10X slower and will be between 60-360 yearly
- Stealing maps now incurs an opinion penalty with the nation that the maps are stolen from, instead of an antagonism bomb on the place the maps are about. 
- Culture conversion cabinet action will be prevented for subjects of the same culture as the top overlord  
- Ask for money country interaction  
  - Cannot put the recipient in debt anymore  
  - Having loans will encourage AI to request help  
  - Sender receives 5 prestige, while receiver loses 10  
  - AI will only accept if the requester is poor and if the requester will not get richer than the AI

##### Economy

- Income lost due to control shortfall is given to the estates (for >0 control locations it is exact, for =0 locations it uses an approximation for potential tax base)
- Diplomatic spending gives to the noble estate 50% of it   
- 0.5 building cap levels are now given per 1K pops rather than per 100K  
- The bailiff building is also allowed in towns and cities  
- The wharf building monthly sailor output: 1 → 6
- Made rural buildings be buildable in any kind of location
- Irrigation is only buildable where there is not enough rainfall
- Control  
  - Proximity affects control at a rate of 75% → 50%  
  - Proximity cost reduced by 20-30%  
    - Proximity Cost through Maritime: 5 → 4  
    - Proximity Cost through Open Sea: 30 → 24  
    - Proximity Cost through Roads: 20 → 15  
    - Proximity Cost through Land: 40 → 30  
    - Proximity Cost through Port: 40 → 30  
    - Proximity Cost of going upstream along a River: 30 → 11
    - Proximity Cost of going downstream along a River: 10 → 11  
    - Proximity Cost on Frozen Water: 20 → 15  
  - Roads  
    - Build cost scaled & maintenance market demands scaled  
      - Gravel roads: 2X
      - Paved roads: 3X  
      - Modern roads: 10X  
      - Railroads: 50X
    - Maintenance cost is 3X higher, rebalanced ratios & non-gravel roads need wood
- Market  
  - Market access cost of rivers equalized up and downstream from 0.9 → 0.7
  - Sliders generate market demand:  
    - Cost of the Court: furniture, tools, glass, fine cloth  
    - Diplomatic expenses: paper, jewelry
  - Can destroy markets even if there are temporary demands
- RGO maximums significantly reduced in early game, with amount rising up closer to vanilla levels lategame.
- Massive rework of the food system, focused on tying up much more of the early game population in food production as peasants.
  - Farming villages  
    - Are split into common pastures & the new farming villages  
    - They are given at game start based on starting peasant population  
    - Cannot be built/generated on sparse terrain  
    - Monthly food: 15 → 10  
  - Subsistence agriculture output: 0.8 → 1.1  
  - Rebalanced food consumption:  
    - Nobles: 20 → 5  
    - Clergy: 5 → 3  
    - Burghers: 4 → 2  
    - Soldiers: 5 → 2  
  - Cities give:  
    - Local food capacity: 500 → 400  
    - Local food production: \-33% → \-25%  
  - RGOs provide less food
- Estate buildings:  
  - Toll castle:  
    - No longer give fort defense value of 25%  
    - Give local noble food consumption of 10%  
    - Give local merchant power of 10%  
  - Noble villa:  
    - Possible nobles: 10 → 20  
    - Local noble food consumption: 20% → 10%  
  - Burgher mansion:  
    - Give Possible Burghers value of 20  
    - Local burgher food consumption: 20% → 10%
- Transhumant wool pasture:
  - Building representing nomadic husbandry
  - Produces wool while also boosting tribe estate power and reducing tribe promotion
  - Restricted to only areas where these made sense (South America, Africa outside of tsetse fly areas, Europe, Asia outside of Indonesia and Japan)
- Sand added to several production methods, including masonry, weapons, and tools.
- Estate built buildings do not consume goods directly, now add pop to consume goods for them.
- Added new PMs to charcoal allowing it to be built in woods/jungles and forests without requiring lumber, and to naval supplies allowing you to build without tin (and removed the copper requirement)
- Spawn 1 more Marketplace per town/city to facilitate early-game trade
  - increase Marketplace cap by one per town/city to make sure these extra building levels are supported
- Significantly reduce Trade Maintenance base to facilitate more trade; especially given that our base prices for goods are lower than Vanilla's
- All good prices rebalanced to 50% of vanilla values, with a few exceptions.
- 'Land' good added as a base resource created by development, consumed by basic buildings that require land development.
- Halved ducat prices for army/navy and doubled their goods-demand
- price impact from trade now 0.8/0.75 from vanilla 0.25/0.75 for burgher/state trade
- Require less profit for AI trade to happen per used merchant capacity, to compensate for lower price levels
- Reworked how trade flows
	-rivers equalized in direction
- Moved 25% of the Age of Discovery Iron Output boost to Age of Renaissance Gunpowder advance
- Removed sand prerequisite from most of industries, transformed sand to silica sand for glassmaking and metallurgy
- Reduced number of glass production buildings from 6 to 1 for indian town setup profile
- Introducing new PM's for iron and bog iron RGO buildings to replace some large % output modifiers
- Scales the construction cost of mining RGO's by 110% per level
- Ups the base level of RGO possible, shift ideal multiplier to base dev scaling.
	
##### Population

- Cored locations' population growth is not restricted to those of primary culture anymore  
- Added an always active pop demotion speed modifier (200% of pop promotion speed) 
- Pops (except slaves) have all now natural growth, not only peasants
- Pop Promotion Speed:  
  - Locations will naturally give a local promotion speed of 10 → 5  
  - Universities’ local pop promotion speed: 10 → 5  
  - Control does not affect population promotion speed anymore [(issue)](https://github.com/MEIOU-and-Taxes/MnT-EU5/issues/8)  
  - Unemployed Slave Promotion: 10 → 20 (To prevent massive unused slave populations in africa)  
- Pop Assimilation Speed:  
  - Base assimilation speed is now relative instead of absolute  
    - It will require 400+ years to fully assimilate  
  - 100% Devastation leads to \-100% Pop Assimilation Speed  
  - Rural settlements get \-50% Pop Assimilation Speed  
  - Promote culture cabinet action:  
    - Pop Assimilation Speed: 40 → 12  
    - Cannot be used when the country has an overlord, has limited diplomacy (e.g. is a fiefdom) and shares the same primary culture as the top overlord  
- Pop Conversion speed  
  - Base conversion speed is now relative instead of absolute  
    - It will require 200+ years to fully convert
- Tribesmen pops now have same share of the tax base as peasants
- Stop randomly spawning Eunuch children
- Added tribes to the Steppe

##### Religion

- Religion opinion satisfaction: 0.05 → 0.02  
- Tolerance on satisfaction scale: 0.05 → 0.02  
- Orthodox religious opinions:  
  - Catholic: positive → negative  
  - Sunni: enemy → negative  
  - Shia: enemy → negative

##### Politics
- Base Estate Power split
  - Commoners (Peasants) estate power per pop: 0.025 → 0.2
  - Dhimmi estate power per pop: 0.02 → 0.1
  - Tribes estate power per pop: 0.01 → 0.2
  - Cossacks estate power per pop: 0.02 → 0.2
  - Burghers estate power per pop: 2 → 3
- Dhimmi estate privileges:  
  - ‘Abrahamic communities’
    - No longer reduce local Unrest by 0.1  
    - Tolerance of Heathen Beliefs: 1 → 2  
    - Tolerance of the True Faith: \-0.5 (New)  
    - Impact on Dhimmi estate power: +100% → +50%
  - ‘Promote tolerance’ 
    - Tolerance of Heathen Beliefs: 1 → 2  
    - Tolerance of the True Faith: \-0.5 (New)  
    - Impact on Dhimmi estate power: +50% → +25%
  - ‘Preserve Local Traditions’ 
    - Tolerance of Heathen Beliefs: 1 → 2  
    - Tolerance of the True Faith: \-0.5 (New)  
    - Impact on Dhimmi estate power: +33% → +20%
  - ‘Pact of Umar’ 
    - Impact on Dhimmi estate power: +100% → +50%
- Commoners estate privileges - reduction of impact on estate power to match increased power per pop:  
  - generic:
    - peasants_free_peasantry: +50% → +10%
    - peasants_represented_in_parliament: +50% → +25%
    - peasant_owns_their_food: +20% → +10%
    - peasants_fewer_levies: +33% → +15%
    - peasants_allowed_weapons_privilege: +50% → +25%
    - allow_hunting: +25% → +15%
    - no_labor_sunday: +33% → +15%
    - communal_lands: +20% → +10%
    - partial_yield: +33% → +15%
    - access_to_royal_and_ecclesiastical_courts: +33% → +15%
    - peasants_in_administration: +50% → +25%
    - peasants_autonomous_villages: +50% → +25%
  - unique:
    - invite_german_settlers: +20% → +5%
    - ayuntamientos: +50% → +25%
    - cas_caballeros_villanos: +20% → +10%
- Noble estate privileges - added impact on Commoners and Dhimmi estate power
  - noble_serfdom_rights: added -10% Commoners and Dhimmi estate power
  - manorial_courts: added -25% Commoners and Dhimmi estate power
  - banal_lordship: added -25% Commoners and Dhimmi estate power
- Added negative impact of Noble estate privileges targetting peasants (noble_serfdom_rights, nobles_land_rights, manorial_courts and banal_lordship) on Peasant and Dhimmi satisfaction
- Modify requirements for country rank change
  - prestige requirement changed from 25/50/70 to being positive
  - added requirement about positive stability
  - added requirement about govt. power above 60
- Scaling of lower class estate power moved to free subjects/serfdom slider, with -100% power at full serfdom slider and +50% at full free subjects
- Added impact of sefdom slider on noble estate power with +100% at full sefdom slider
- Scaling of Tribes Estate added to centralization slider, with -50% power at full centralization and +50% at full 
- Changed impact of government reforms on estate power:
  - land_inheritance_act: added +10% impact on commoner estate power
  - universal_serfdom: reduced impact on commoners estate power from -50% to -10% (as effects are moved to actual serfdom value)

##### Disasters

- ‘Decline of empires’ removed, now is ‘Time of struggle’, applies to everyone with more complex logic and less impossible to escape.
- ‘Time of Troubles’ removed, it was bad in vanilla, and needs to be fundamentally redesigned to be reimplemented

##### Warfare

- Land war exhaustion from losses: 100 → 300  
- Fishing boats’ crew is not peasants, but laborers  
- Remove effect of dismantle fort peace option on Theodosian walls
- Tribal levies for non-tribal non-steppe government: 2% → 15%
- Steppe hordes only make steppe cavalry out of tribesmen and nobles of Turkic and Mongolian cultures
- Steppe cavalry levies for steppe hordes: 2% → 50%

##### Situations

- Fixes to Colombian Exchange situation
  - adapt logic of RGO changing to new mechanics related to demand on goods absent in the market
  - remove prestige cost on changing the RGO
  - modify map mode and tooltips, so previous and new good is visible to a player
  - remove ability to plant Tobacco in Oceanic climate
  
##### GUI
- Added Goods Domestic Product UI in the Economy panel
- Added fIlter button for rgo buildings in building view
- Changed the behaviour of brgo buttons to show rgo buildings 
- Unified goods-panel RGO buttons with the Production view RGO visibility toggle and removed sticky per-good RGO force-show state.
- Reworked the goods-panel Production opener to set RGO visibility through a dedicated scripted GUI based on the selected good, and removed the unused old per-good force-show path.
- Reworked the location window RGO button to open Location Production filtered to the selected location's raw material building path.
- Updated the location window RGO value readout to show current RGO building level versus location-specific maximum level.
- Added a row in the loading screen showing MnT version
- Added M&T logo in the main menu and remove PDX marketing

##### Modding
- Added automated check for correct encodings and line endings via GitHub Actions

##### Climates
- replace all climates with the more varied koppen climates
  - references to older climates point to multiple koppen climates 

##### M&T v0.1.1

### Balance
- Make every level of RGO Building give 1 free building level in its location (so you can't effectively get less available building levels from building up rural resource extraction stuff)
- Similarly for farming villages and tribal transhumant_wool_pasture buildings, give 1 free building level per level as we sort of force the player to have these buildings
- Increased monthly disease resistance reduction for pops to the Bubonic Plague, Influenza and Smallpox

### Fixes
- Fix Fish RGO Building not fulfilling upgrade potential if Location defined as fish RGO
- Fix cost increase per level in RGO modifier (mostly increased cost for mines per level) showing extra cost in green -> make properly red
- Fix possibility of subjects declaring war on Countries experiencing Decline of Empire disaster where they should not be able to declare wars in the first place

### Localizaton
- Localize raw_material_output as Resource Size bonus
- Add rgo_building game concept

##### M&T v0.1.2

### Setup
- Not new but explain: 
  - Free all slaves at gamestart since Vanilla assumes mass enslavement, temporary bandaid until Vanilla addresses this or we fix it more elegantly
- Rebalance the distribution of Tribal pops in the world based on historically tribal cultures
  - Split pops between peasants and tribes based on development numbers
  - Ensures somewhat normal distribution of peasants/tribes globally
  - This increases the amount of tribes worldwide (no change to total pop number)

### Military
- Reduce the amount of tribal levies per tribal-population, and make it equal accross the board
- No country restrictions on tribal levies; there's no reason why calling up the more remote people of your lands who for the most part don't really care about your laws should somehow change their composition based on laws or country type
- Remove local_army_attrition from all climates where present. Army attrition blocks reinforcement and reduces morale. These 2 quirks make base attrition in some climates unfun and not feasible, despite being historically realistic. 

### Fixes
- Adds in all the goods transports costs from vanilla, as it defaults to 1. Also added them where it's 1 for clarity.
- Restored some prices to exactly half vanilla price as production chains weren't changed with it.
  - This should fix wool being too cheap and thus used too much to make cloth
- Fix some buildings not buildable in Metropolis due to us forgetting to add Megalopolis = yes line with 1.2 update

### Balance
- Reduce the base power_per_pop for Peasants by 25%
- Disable Peasants power from farming villages
- Disable Settlements in town/city
- Allow wool rgo_building where Vanilla would allow sheep_farms
