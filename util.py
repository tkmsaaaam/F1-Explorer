def join_with_colon(*args):
    return ' : '.join(args)


def time_str_to_seconds(time_str):
    if time_str == "":
        return 0
    parts = time_str.split(":")

    if len(parts) == 1:
        # "SSS.sss"
        return float(parts[0])
    elif len(parts) == 2:
        # "MM:SS.sss"
        minutes, seconds = parts
        return int(minutes) * 60 + float(seconds)
    elif len(parts) == 3:
        # "HH:MM:SS.sss"
        hours, minutes, seconds = parts
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    else:
        raise ValueError(f"Unsupported time format: {time_str}")


def push(driver_number: int, lap_number: int, target_map, value):
    if driver_number in target_map:
        target_map[driver_number][lap_number] = value
    else:
        target_map[driver_number] = {lap_number: value}


def push_stint(key, driver_number: int, stint_number: int, stint, stint_map):
    if key in stint:
        if driver_number in stint_map:
            if stint_number in stint_map[driver_number]:
                stint_map[driver_number][stint_number][key] = stint[key]
            else:
                stint_map[driver_number][stint_number] = {key: stint[key]}
        else:
            stint_map[driver_number] = {stint_number: {key: stint[key]}}
