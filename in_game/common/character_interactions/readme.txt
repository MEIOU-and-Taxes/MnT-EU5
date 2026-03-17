#<interaction_name> = {
#	
# message = yes/no whether or not to show a message about this interaction
# sound = sound to use for the action
# on_other_nation = yes/no, whether you can use this on characters from another nation (default = no)
# on_own_nation = yes/no, whether you can use this on characters from your nation (default = no)
# is_consort_action = yes/no, whether this is an interaction on your consort
# potential = trigger, scope:actor is the country attempting to perform the action
# allow = trigger, scope:actor is the country attempting to perform the action
# price = a scripted standard price, listed in \common\prices\ and referenced by name (like price:<price_id>) or as a result of a script (like scope:target.price)
# price_modifier = calculated value, multiplies the price; scope:actor is the country, scope:recipient, scope:target, scope:target_1, scope:target_2....etc
# payer = script to determine who is paying the price. By default, the actor
# payee = script to determine who gets paid. By default, nobody, the price disappears into the ether
# select_trigger = can add multiple of these to allow selection of targets/parameters for the action. They get stored in scope:target, scope:target_1, scope:target_2....etc
#				   format: 
#						looking_for_a = character/location/province/area/region/country/value/boolean etc
#						target_flag = what you want to call this target in the scope (e.g. target, target_1, target_province etc.) Then later you'll use this name to reference what was selected here. If left out it will default to target, target_1, target_2, target_3 etc
#						source = actor/recipient/target/target_1/target_2/target_3/target_4/world
#						source_ai_override = actor/recipient/target/target_1/target_2/target_3/target_4 (ai only)
#                       source_flags = options to improve game performance by narrowing down the choice (neighbor/possible_colonial_charters/include_dead/include_any_present/possible_exploration_areas/adjacent_locations/vacant_adjacent_locations/adjacent_provinces/border/border_or_recipients_capital_area/provinces_ai_wants_to_give_away/only_actual_locations)
#                       source_flags_ai_override = options to improve game performance by narrowing down the choice for Ai countries (neighbor/possible_colonial_charters/include_dead/include_any_present/possible_exploration_areas/adjacent_locations/vacant_adjacent_locations/adjacent_provinces/border/border_or_recipients_capital_area/provinces_ai_wants_to_give_away/only_actual_locations)
#		                source_global_list = <name of global variable list with the list of candidates in> if you have a pre calculated global list of who you want in the select_trigger, use this
# 						interaction_source_list = <effect> gives us a list of possible candidates to look at. scope:actor is the country, scope:recipient, scope:target, scope:target_1, scope:target_2....etc. Fill the list with add_to_list = source on the scope object
# 						ai_interaction_source_list = { #Same as above but it is only applied to Ai countries
#                       pre_evaluation_sort_value = optional script value, use this to sort the initial list of possible targets that pass the trigger and select the top X to evaluate fully (use in conjunction with pre_evaluation_number_to_evaluate_fully)
#                       pre_evaluation_number_to_evaluate_fully = integer, number of the top sorted pre-evaluated targets to pass on for full evaluation (use in conjunction with pre_evaluation_sort_value) (AI only)
#                       max_targets_for_ui = integer, number of the top sorted pre-evaluated targets to pass on to the UI for the user to choose from
#                       cache_targets = yes/no if the list of targets will always be the same, i.e. doesn't depend on any other selection, then set this to yes to save processing
#                       cache_interaction_source_list = yes/no if the interaction source list will always be the same, i.e. doesn't depend on any other selection, then set this to yes to save processing
#                       cache_order = yes/no if the list of targets will always be in the same order of how good they are at the task, set this to yes to save processing
#						name = localisation name of the title for the selection stage
#						allow_null = yes/no to allow the selection of a null object
#                       allow_null_trigger = trigger to check under what circumstances should null be included / excluded, only active when allow_null is set
#                       allow_self = yes/no to allow the actor to be added to the list (only works for countries)
#                       move_to_next_section_on_click yes/no should the UI move to the next stage when you click on an item. Usually left to the default yes, but set to no if you have some other UI that will perform that action somewhere else
#						top_widget = links to a widget type in the gui files to show at the top of the list. 
#						bottom_widget = links to a widget type in the gui files to show at the bottom of the list. 
#						column = { data = <column_id> width = <int> icon = <path> show_icon_in_cells = yes/no } adds a column to the UI to search with
#                                these can also be defaulted, see \common\attribute_columns
#                       default_sort = key of the sort you want the selection to default to. With nothing it will default to the first sort column. The columns you have are specified in columns = above, the sort keys for the sorts are in \common\attribute_columns\
#                       none_available_msg_key = key of the localisation used when there are no available targets to choose from (optional)
#                       show_why_not_visible = yes/no true to show why a target might not be visible if there are no targets
#                       show_why_not_enabled = yes/no true to show why a target might not be enabled if there are no targets
#                       show_if = { <trigger to see if this stage is needed; scope:actor is the country, scope:recipient, scope:target, scope:target_1, scope:target_2....etc}
#						visible = { <some trigger...root is the object being tested, scope:actor is the country, scope:recipient, scope:target, scope:target_1, scope:target_2....etc> }
#						enabled = { <some trigger...root is the object being tested, scope:actor is the country, scope:recipient, scope:target, scope:target_1, scope:target_2....etc> }
#						selected = { <some trigger...root is the object being tested, scope:actor is the country, scope:recipient, scope:target, scope:target_1, scope:target_2....etc> } tests to see if the target is currently selected
#                       min = <script value> minimum value for value types
#                       max = <script value> maximum value for value types
#                       step = <script value> step value for changing value types in the UI
#                       default = <script value> default value for value types
#						map_mode = <map mode tag> map mode the map will switch to while choosing this target (optional)
# 						map_color = <script color> map color for location (root = location, scope:actor/recipient etc)
#                       only_color_selectable = <yes/no> yes to only think about colouring selectable locations; no to be able to colour any location with the script above
# 						secondary_map_color = <script color> striped map color for location (root = location, scope:actor/recipient etc)
# ai_tick = <never/daily/monthly> use to ban the AI from using an action that is already handled in code OR to indicate how often to process
# ai_tick_frequency = <scripted value> how many ticks until next. script to determine how often this action should be checked for each country. root is the country. This is just a per-country check. So ai_tick = monthly and ai_tick_frequency = 6 means "check every 6 months"
# show_message = no, optional, to prevent messages showing
# show_message_to_target = no, optional, to prevent messages to show to the target
# should_execute_price = no, optional, to prevent the price of the action to be paid
# show_in_gui_list = no, optional, to prevent the action to be listed automatically in the GUI. Useful when you want to have very specific buttons for this action
# ai_will_do = effect script for the AI to use, scope:actor is the country, scope:recipient, scope:target, scope:target_1, scope:target_2....etc
# effect = effect, scope:actor is the country, scope:recipient, scope:target, scope:target_1, scope:target_2....etc
# cooldown = { type = <any tag> days/weeks/months/years = <integer> } adds a cooldown for the action during which time it cannot be performed again
#
#
