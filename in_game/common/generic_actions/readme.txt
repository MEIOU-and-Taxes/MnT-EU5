# Generic action system - create an action entirely in script and place a GUI button for it entirely in script - no need for coders!
#
# This is the action script. In addition to adding an action here, you'll need strings for the name (tag is the <action_tag>) and description (tag is <action_tag>_desc)
#
# type = owncountry/religious/religiousfaction/diplomacy/subject/character/location/internationalorganization/situation/internationalorganizationparliament
# sound = sound to use for the action
# message = message key for when sensing pop up messages to the user
# potential = trigger, scope:actor is the country attempting to perform the action
# allow = trigger, scope:actor is the country attempting to perform the action
# ai_prerequisite = trigger to check if the AI should do this action, root is the country attempting to perform the action, no scopes or targets are available at this early stage
# price = a scripted standard price, listed in \common\prices\ and referenced by name (like price:<price_id>) or as a result of a script (like scope:target.price)
# price_modifier = calculated value, multiplies the price; scope:actor is the country, scope:recipient, scope:target, scope:target_1, scope:target_2....etc
# payer = script to determine who is paying the price. By default, the actor
# payee = script to determine who gets paid. By default, nobody, the price disappears into the ether
# select_trigger = can add multiple of these to allow selection of targets/parameters for the action. They get stored in scope:target, scope:target_1, scope:target_2....etc
# 				   PerformGenericAction takes the user through selecting these targets
#				   format: 
#						looking_for_a = character/location/province/area/region/country/value/boolean etc
#						target_flag = what you want to call this target in the scope (e.g. target, target_1, target_province etc.) Then later you'll use this name to reference what was selected here. If left out it will default to target, target_1, target_2, target_3 etc
#						source = actor/recipient/target/target_1/target_2/target_3/target_4/world
#						source_ai_override = actor/recipient/target/target_1/target_2/target_3/target_4 (ai only)
#                       source_flags = options to improve game performance by narrowing down the choice (neighbor/possible_colonial_charters/include_dead/include_any_present/possible_exploration_areas/adjacent_locations/vacant_adjacent_locations/adjacent_provinces/border/border_or_recipients_capital_area/provinces_ai_wants_to_give_away/only_actual_locations/only_defending_sieges/only_attacking_sieges/include_subjects)
#                       source_flags_ai_override = options to improve game performance by narrowing down the choice for Ai countries (neighbor/possible_colonial_charters/include_dead/include_any_present/possible_exploration_areas/adjacent_locations/vacant_adjacent_locations/adjacent_provinces/border/border_or_recipients_capital_area/provinces_ai_wants_to_give_away/only_actual_locations/include_subjects)
#		                source_global_list = <name of global variable list with the list of candidates in> if you have a pre calculated global list of who you want in the select_trigger, use this
# 						interaction_source_list = <effect> gives us a list of possible candidates to look at. scope:actor is the country, scope:recipient, scope:target, scope:target_1, scope:target_2....etc. Fill the list with add_to_list = source on the scope object
# 						ai_interaction_source_list = { #Same as above but it is only applied to Ai countries
#                       pre_evaluation_sort_value = optional script value, use this to sort the initial list of possible targets that pass the trigger and select the top X to evaluate fully (use in conjunction with pre_evaluation_number_to_evaluate_fully)
#                       pre_evaluation_number_to_evaluate_fully = integer, number of the top sorted pre-evaluated targets to pass on for full evaluation (use in conjunction with pre_evaluation_sort_value) (AI only)
#                       max_targets_for_ui = integer, number of the top sorted pre-evaluated targets to pass on to the UI for the user to choose from
#                       max_targets_for_ui = integer, number of the top sorted pre-evaluated targets to pass on to the UI for the user to choose from
#                       cache_targets = yes/no if the list of targets will always be the same, i.e. doesn't depend on any other selection, then set this to yes to save processing
#                       cache_interaction_source_list = yes/no if the interaction source list will always be the same, i.e. doesn't depend on any other selection, then set this to yes to save processing
#                       cache_order = yes/no if the list of targets will always be in the same order of how good they are at the task, set this to yes to save processing
#						name = localisation name of the title for the selection stage
#						allow_null = yes/no to allow the selection of a null object, can be a trigger to check under what circumstances should null be included / excluded instead
#                       allow_self = yes/no to allow the actor to be added to the list (only works for countries)
#                       move_to_next_section_on_click yes/no should the UI move to the next stage when you click on an item. Usually left to the default yes, but set to no if you have some other UI that will perform that action somewhere else
#						top_widget = links to a widget type in the gui files to show at the top of the list. 
#						bottom_widget = links to a widget type in the gui files to show at the bottom of the list. 
#						column = { data = <column_id> width = <int> icon = <path> show_icon_in_cells = yes/no } adds a column to the UI to search with
#                                these can also be defaulted, see \common\attribute_columns
#                       default_sort = key of the sort you want the selection to default to. With nothing it will default to the first sort column. The columns you have are specified in columns = above, the sort keys for the sorts are in \common\attribute_columns\
#						tooltip_msg_key = key of the localisation for anything you want added to the tooltip on the map
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
#                       ai_override_value = <script value> sole value to test for the AI [optional, use for performance reasons]
#						map_mode = <map mode tag> map mode the map will switch to while choosing this target (optional)
# 						map_color = <script color> map color for location (root = location, scope:actor/recipient etc)
#                       only_color_selectable = <yes/no> yes to only think about colouring selectable locations; no to be able to colour any location with the script above
# 						secondary_map_color = <script color> striped map color for location (root = location, scope:actor/recipient etc)

# ai_tick = <never/daily/monthly> use to ban the AI from using an action that is already handled in code OR to indicate how often to process
# ai_tick_frequency = <scripted value> how many ticks until next. script to determine how often this action should be checked for each country. root is the country. This is just a per-country check. So ai_tick = monthly and ai_tick_frequency = 6 means "check every 6 months"
# automation_tick = <never/daily/monthly> use to ban the AI from using an action that is already handled in code OR to indicate how often to process. Used for the automation
# automation_tick_frequency = <scripted value> how many ticks until next. script to determine how often this action should be checked for each country. root is the country. This is just a per-country check. So automation_tick = monthly and automation_tick_frequency = 6 means "check every 6 months". Used for the automation process
# show_message = no, optional, to prevent messages showing
# show_message_to_target = no, optional, to prevent messages to show to the target
# should_execute_price = no, optional, to prevent the price of the action to be paid
# show_in_gui_list = no, optional, to prevent the action to be listed automatically in the GUI. Useful when you want to have very specific buttons for this action
# ai_will_do = effect script for the AI to use, scope:actor is the country, scope:recipient, scope:target, scope:target_1, scope:target_2....etc
# player_automated_category = system, if the human player activates the automation for the system then the action may be executed according to ai_will_do
#                               possible values: finances/research/trade/productionmethods/laws/cabinet/parliament/estates/exploration/colonies/cultureacceptance/religiousdoctrines/buildings/rgo/armybuilder/navybuilder
# effect = effect, scope:actor is the country, scope:recipient, scope:target, scope:target_1, scope:target_2....etc plus scope:price/scope:price_modifier/scope:payer/scope:payee returns the price details
# cooldown = { type = <any tag> days/weeks/months/years = <integer> } adds a cooldown for the action during which time it cannot be performed again
# maximum_targets_in_one_tick = <int> allows ai to perform the same action multiple times per check, -1 for unlimited, default 1
# disallowed_duplicates_of_targets_for_ai = {} list of target flags that can't have duplicates when maximum_targets_in_one_tick is not 1, for example target_location so AI won't target the same location twice in the same tick
# force_click_and_confirm_or_hold = yes, optional, to always show confirmation dialog. Useful for tweaking dangerous IO actions like declaring wars without redoing UI layout
# To use the action in GUI script, use this sort of thing:
#
#action_button_default = {
#	title = "<optional title for action tooltip>"
#	description = "<optional description for action tooltip. By default, uses the generic action description>"
#	effects = "<optional description of the effects for action tooltip. By default, uses the generic action effects but you can override>"
#	conditions = "<optional description of the conditions for action tooltip. By default, uses the generic action trigger but you can override>"
#	actor = "[GUI script to get the country that is performing the action]"
#	recipient = "[<GUI script to get the recipient of the action>]"
#	target = "[<GUI script to get the target of the action>]"
#   target = ... (you can add as many targets as you want in case the action has several)
#	left_action = "<id of the action to perform with a click of the left button>"
#	left_click_and_hold_action = "<id of the action to perform with a click and hold of the left button>"
#	right_action = "<id of the action to perform with a click of the right button>"
#	right_click_and_hold_action = "<id of the action to perform with a click and hold of the right button>"
#}
#
#
# As for message types that get sent to the player, the format is as follows. At the very least, the generic version should be provided. If the more specific ones are available, they will be used.
# Generic catch-all message: PERFORM_ + Key + _ACTION e.g. PERFORM_do_some_stuff_ACTION
#
# These are added as message types in gui/messagetypes.txt.
#
# The text for them needs to be added as localizations. There are plenty of examples, all the localizations use the stem of the action type as the basis for the localization key.
#
# When the player does the action: WE_PERFORM_ + Key + _ACTION e.g. WE_PERFORM_throw_tomatoes_ACTION
# When another country does it: OTHER_PERFORMS_ + Key + _ACTION e.g. OTHER_PERFORMS_rain_dance_ACTION
# When another country does it to us: ACTION_ + Key + _PERFORMED_ON_US e.g. ACTION_declare_war_PERFORMED_ON_US
#
# In the strings for these messages, in addition to being able to use the scope variables in the strings, you can use the following presets:
# $ACTION$ - the name of the action
# $EFFECT$ - the effect of the action
# $DESC$ - the action description (<action_tag>_desc)