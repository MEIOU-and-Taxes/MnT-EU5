When running any script, make sure the working directory is a child of `tools` (or a sibling of `shared` folder)


Launchers
=========
Double-click the .bat files in Windows to run them. They need Python3. The two window launchers offer
to install Python if it is missing.

MnT Building Setup.bat
    Opens the building setup window. It sets the starting level of each building type in each
    location, from settings for pops, development, terrain and location rank. Apply writes the
    setup files in main_menu/setup/1337. Apply Dry Run shows what would change and writes nothing.
    Gather Foundational Building Setup Data starts the game once to record the buildings each
    location has in the base game. Do this again after a game patch.

MnT Provisions.bat
    Opens the provisions methods window. It sets the recipe and food amount of each production
    method that makes provisions, and the provisions in army maintenance. Apply writes the building
    files and army_demands.txt, and saves a backup first.

MnT Unit Maintenance.bat
    Opens the unit maintenance window. Each unit type uses a maintenance demand, and any number of
    unit types can share one. The window sets each demand's goods and food, and each unit type's
    demand, manpower and sailors. Apply writes the goods demands, the unit type changes and the
    maintenance prices. Land unit gold follows the value of the goods. Run Apply again after you
    change a goods price.
