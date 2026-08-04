def find_duplicates(items: list) -> list:
    seen = set()
    dupes = []
    for i in items:
        try:
            if i in seen:
                dupes.append(i)
            else:
                seen.add(i)
        except TypeError:
            pass
    return dupes
