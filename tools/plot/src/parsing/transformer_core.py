_reported_duplicate_names = set()
_duplicate_name_callback = None


def set_duplicate_name_callback(cb):
    """Sets a GUI notification callback when duplicate entity names are discovered."""
    global _duplicate_name_callback
    _duplicate_name_callback = cb


def check_and_notify_duplicate_names(entity_type: str, name_to_identifiers: dict):
    """Checks if different entities share identical display names and notifies once via callback."""
    duplicates = {name: ids for name, ids in name_to_identifiers.items() if len(ids) > 1}
    if not duplicates:
        return

    new_duplicates = {k: v for k, v in duplicates.items() if (entity_type, k) not in _reported_duplicate_names}
    if not new_duplicates:
        return

    for k in new_duplicates:
        _reported_duplicate_names.add((entity_type, k))

    msg_lines = [f"Duplicate {entity_type} names detected across different entities:\n"]
    for name, ids in sorted(new_duplicates.items()):
        msg_lines.append(f"  • '{name}' used by: {', '.join(sorted(ids))}")
    msg_lines.append("\nDifferent tags/identifiers will be appended in parentheses.")

    print("[WARNING] " + "\n".join(msg_lines))
    if _duplicate_name_callback:
        _duplicate_name_callback(entity_type, "\n".join(msg_lines))