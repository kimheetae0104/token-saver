def find_duplicates(items: list, seen: list | None = None) -> list:
    if seen is None:
        seen = []
    dupes = []
    for i in items:
        if i in seen:
            dupes.append(i)
        else:
            seen.append(i)
    return dupes
