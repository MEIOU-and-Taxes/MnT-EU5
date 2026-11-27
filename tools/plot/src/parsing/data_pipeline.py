"""Mathematical transformations pipeline for chart plotting: Density, Baseline, and Derivatives."""


def apply_data_pipeline(
    filtered,
    density_mode,
    baseline_mode,
    deriv_order,
    from_moment,
    is_yr_offset,
    value_key,
    category_key,
    entity_key,
    rloc_map,
    value_label
):
    """
    Transforms filtered data through Density, Baseline, and Derivative calculations.
    Returns: (transformed_data, effective_value_label, base_year_disp, error_message)
    """
    effective_val_label = value_label
    base_year_disp = None

    # 1. Density Transformation
    if density_mode == "location":
        effective_val_label = f"{effective_val_label} / Location"
        has_valid_locations = False
        transformed = []
        for itm in filtered:
            copy_item = dict(itm)
            locs = 0.0
            if "locations" in copy_item and (copy_item.get("locations") or 0) > 0:
                locs = float(copy_item["locations"])
                has_valid_locations = True
            else:
                reg = copy_item.get("region", "")
                locs = float(rloc_map.get(reg, 0))
                if locs > 0:
                    has_valid_locations = True
            copy_item[value_key] = (copy_item[value_key] / locs) if locs > 0 else 0.0
            transformed.append(copy_item)

        if not has_valid_locations:
            return None, effective_val_label, None, "No count of locations stored for this data.\nCannot calculate density by location."
        filtered = transformed

    elif density_mode == "population":
        effective_val_label = f"{effective_val_label} / 1M Pop"
        has_valid_population = False
        transformed = []
        for itm in filtered:
            copy_item = dict(itm)
            pop = copy_item.get("population") or copy_item.get("total_population") or copy_item.get("Population") or 0.0
            try:
                pop = float(pop)
            except (ValueError, TypeError):
                pop = 0.0

            if pop > 0:
                has_valid_population = True
                copy_item[value_key] = (copy_item[value_key] / pop) * 1_000_000.0
            else:
                copy_item[value_key] = 0.0
            transformed.append(copy_item)

        if not has_valid_population:
            return None, effective_val_label, None, "No population stored for this data.\nCannot calculate density by population."
        filtered = transformed

    # 2. Baseline Transformation (Ratio % / Difference Δ)
    if baseline_mode in ("ratio", "difference"):
        all_filt_moments = sorted(set(i['moment'] for i in filtered))
        base_year = from_moment if (from_moment is not None and from_moment in all_filt_moments) else (all_filt_moments[0] if all_filt_moments else None)

        if base_year is not None:
            base_year_disp = str(base_year - 1337) if is_yr_offset else str(base_year)
            if baseline_mode == "ratio":
                effective_val_label = f"% of Year {base_year_disp} ({effective_val_label})"
            else:
                effective_val_label = f"Δ from Year {base_year_disp} ({effective_val_label})"

            base_lookup = {}
            for itm in filtered:
                if itm['moment'] == base_year:
                    ent = itm.get(entity_key, itm.get('country', itm.get('region', '')))
                    cat = itm.get(category_key, '')
                    base_lookup[(ent, cat)] = float(itm[value_key])

            base_transformed = []
            for itm in filtered:
                ent = itm.get(entity_key, itm.get('country', itm.get('region', '')))
                cat = itm.get(category_key, '')
                base_val = base_lookup.get((ent, cat))

                if base_val is None:
                    continue
                if baseline_mode == "ratio" and base_val == 0:
                    continue

                copy_item = dict(itm)
                if baseline_mode == "ratio":
                    copy_item[value_key] = ((float(itm[value_key]) / base_val) - 1.0) * 100.0
                else:
                    copy_item[value_key] = float(itm[value_key]) - base_val
                base_transformed.append(copy_item)

            filtered = base_transformed

    # 3. Derivative Transformation (Rate / Acceleration)
    if deriv_order > 0:
        if deriv_order == 1:
            effective_val_label = f"Δ {effective_val_label} / Year"
        elif deriv_order == 2:
            effective_val_label = f"%Δ {effective_val_label} / Year"
        elif deriv_order == 3:
            effective_val_label = f"Δ² {effective_val_label} / Year²"

        deriv_transformed = []
        entity_series_map = {}
        for item in filtered:
            ent = item.get(entity_key, item.get('country', item.get('region', '')))
            c_val = item.get(category_key, '')
            key = (ent, c_val)
            entity_series_map.setdefault(key, []).append(dict(item))

        for key, series_items in entity_series_map.items():
            series_items.sort(key=lambda x: x['moment'])
            if deriv_order == 1:
                for i in range(1, len(series_items)):
                    diff_item = dict(series_items[i])
                    diff_item[value_key] = series_items[i][value_key] - series_items[i - 1][value_key]
                    deriv_transformed.append(diff_item)
            elif deriv_order == 2:
                for i in range(1, len(series_items)):
                    rel_item = dict(series_items[i])
                    prev_v = series_items[i - 1][value_key]
                    rel_item[value_key] = (((series_items[i][value_key] - prev_v) / prev_v) * 100.0) if abs(prev_v) > 1e-12 else 0.0
                    deriv_transformed.append(rel_item)
            elif deriv_order == 3:
                for i in range(2, len(series_items)):
                    accel_item = dict(series_items[i])
                    d_curr = series_items[i][value_key] - series_items[i - 1][value_key]
                    d_prev = series_items[i - 1][value_key] - series_items[i - 2][value_key]
                    accel_item[value_key] = d_curr - d_prev
                    deriv_transformed.append(accel_item)

        if not deriv_transformed:
            needed = 3 if deriv_order == 3 else 2
            d_term = "relative rate (%Δ)" if deriv_order == 2 else ("rate (Δ)" if deriv_order == 1 else "acceleration (Δ²)")
            return None, effective_val_label, None, f"Need at least {needed} consecutive time steps to calculate {d_term}."

        filtered = deriv_transformed

    return filtered, effective_val_label, base_year_disp, None