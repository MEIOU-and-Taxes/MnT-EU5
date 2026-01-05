# Release

### 0.0.1

Date: 2025-11-30

#### Features

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
  - Each type has an associated score dependent on multiple factors and a absolute minimum threshold per tier.
  - Additionally per geographical area only one center of each tier can exist.
  - Each location center tier gives bonuses to the location.
- Goods Domestic Production (proxy for GDP goods domestic product ), sum of goods value * amount
#### Bugfixes

- Stability map mode works, where it is red at \<25 and green at \>50 stability
- Backend error fixes

#### Balancing

-Crown power now increase percent of building upkeep paid by the state, low crown power reduces it.
-Reduced use of masonry by granaries.
-Reduced use of tools by lumber mills.
-Higher literacy lowers stability.
-Peasant percentage improves stability.
-Buffed cabinet stability improving action.
-Stability effects prosperity negatively as well as positively.
-Reduced stability cost of destroying markets.
-Reduced stability cost of revoking privileges.
-Made hiring new characters scale somewhat less with income.
-Local population growth removed from having positive food.


##### Diplomacy

- Steal map’s antagonism bomb will not impact the robbed tag, but the discovered place  
- Sabotage reputation spy network cost: 5 → 10  
- Sow discontent & Corrupt officials diplomatic actions’ cost in gold will scale 10X slower and will be between 60-360 yearly  
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
    - Proximity Cost of going upstream along a River: 30 → 22  
    - Proximity Cost of going downstream along a River: 10 → 7  
    - Proximity Cost on Frozen Water: 20 → 15  
  - Roads  
    - Build cost scaled & maintenance market demands scaled  
      - Gravel roads: 2X
      - Paved roads: 3X  
      - Modern roads: 10X  
      - Railroads: 50X
    - Maintenance cost is 3X higher, rebalanced ratios & non-gravel roads need wood
- Market  
  - Market access cost reduction doubled for roads:  
    - Gravel: \-10% → \-20%  
    - Paved road: \-15% → \-30%  
    - Modern road: \-20% → \-40%  
    - Railroad: \-25% → \-50%  
  - Sliders generate market demand:  
    - Cost of the Court: furniture, tools, glass, fine cloth  
    - Diplomatic expenses: paper, jewelry  
- Food  
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
  - RGOs give less food:  
    - Wool: 5 → 2  
    - Wild game: 3.5 → 2  
    - Fur: 2 → 1  
    - Fish: 5 → 3  
    - Wheat: 8 → 5  
    - Maize: 8 → 5  
    - Rice: 10 → 6  
    - Millet: 5 → 3  
    - Legumes: 5 → 3  
    - Potato: 8 → 5  
    - Livestock: 8 → 4  
    - Olives: 4 → 2  
    - Fruit: 4 → 2.5  
    - Beeswax: 2.5 → 1  
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
-Sand added to several production methods, including masonry, weapons, and tools.
-Estate built buildings do not consume goods directly, now add pop to consume goods for them.

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

##### Religion

- Religion opinion satisfaction: 0.05 → 0.02  
- Tolerance on satisfaction scale: 0.05 → 0.02  
- Orthodox religious opinions:  
  - Catholic: positive → negative  
  - Sunni: enemy → negative  
  - Shia: enemy → negative

##### Politics

- Dhimmi estate privileges:  
  - ‘Abrahamic communities’, ‘Promote tolerance’ & ‘Preserve Local Traditions’:  
    - Tolerance of Heathen Beliefs: 1 → 2  
    - Tolerance of the True Faith: \-0.5 (New)  
  - ‘Abrahamic communities’:  
    - No longer reduce local Unrest by 0.1  
- Modify requirements for country rank change
  - prestige requirement changed from 25/50/70 to being positive
  - added requirement about positive stability
  - added requirement about govt. power above 60

##### Disasters

- ‘Decline of empires’ removed, now is ‘Time of struggle’, applies to everyone with more complex logic and less impossible to escape.

##### Warfare

- Land war exhaustion from losses: 100 → 300  
- Fishing boats’ crew is not peasants, but laborers  
- Remove effect of dismantle fort peace option on Theodosian walls

##### Situations

- Fixes to Colombian Exchange situation
  - adapt logic of RGO changing to new mechanics related to demand on goods absent in the market
  - remove prestige cost on changing the RGO
  - modify mapmode and tooltips, so previous and new good is visible to a player
  - remove ability to plant Tobacco in Oceanic climate
  
##### GUI
- Added Goods Domestic Product UI in the Economy panel