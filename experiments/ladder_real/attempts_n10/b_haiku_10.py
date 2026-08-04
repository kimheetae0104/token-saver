def find_duplicates(items: list) -> list:
    seen = []
    dupes = []
    for i in items:
        try:
            if i in seen:
                dupes.append(i)
            else:
                seen.append(i)
        except TypeError:
            pass
    return dupes
