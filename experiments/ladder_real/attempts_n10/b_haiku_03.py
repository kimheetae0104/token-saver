def find_duplicates(items: list) -> list:
    dupes = []
    seen = set()
    for i in items:
        if i in seen:
            dupes.append(i)
        else:
            seen.add(i)
    return dupes
