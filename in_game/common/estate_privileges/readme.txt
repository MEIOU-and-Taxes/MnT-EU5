# Estate Privileges
#
# A set of privileges that can be implemented for any of your estates.
#
# ATTRIBUTES
#
# - estate: <estate type tag> the estate the privilege applies to
# - potential: trigger for whether the action is possible (root = country)
# - allow: trigger for whether the action can start (root = country)
# - years:
# - months:
# - weeks:
# - days: <ints> all used to define how long it takes to become fully implemented. Modifiers will be scaled by how much of this time is completed.
# - on_activate: <effect> fired when the action is chosen (root = country)
# - on_fully_activated: <effect> fired when the action's implementation reaches 100% (instant if there's no time delay)
# - on_deactivate: <effect> fired when the action is removed (root = country)
# - country_modifier: <scaled and triggered modifier (scale = script for the scale, potential_trigger = trigger for if the modifier applies)> which is applied to whole countries
# - province_modifier: <scaled and triggered modifier (scale = script for the scale, potential_trigger = trigger for if the modifier applies)> which is applied to provinces
# - location_modifier: <scaled and triggered modifier (scale = script for the scale, potential_trigger = trigger for if the modifier applies)> which is applied to locations
# - can_revoke: trigger when you should be capable of removing an enacted privilege