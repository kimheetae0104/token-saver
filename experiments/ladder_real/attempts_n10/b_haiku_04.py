def find_duplicates(items: list) -> list:
    seen = []
    dupes = []
    for i in items:
        if i in seen:
            dupes.append(i)
        else:
            seen.append(i)
    return dupes
