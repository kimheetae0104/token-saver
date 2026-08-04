def find_duplicates(items: list, seen: list = None) -> list:
    if seen is None:
        seen = []
    dupes = []
    for item in items:
        try:
            if item in seen:
                dupes.append(item)
            else:
                seen.append(item)
        except TypeError:
            pass
    return dupes
