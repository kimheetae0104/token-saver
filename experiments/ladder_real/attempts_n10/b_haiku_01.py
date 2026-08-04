from typing import List, Any

def find_duplicates(items: List[Any]) -> List[Any]:
    dupes = []
    seen = []
    for i in items:
        try:
            if i in seen:
                dupes.append(i)
            else:
                seen.append(i)
        except TypeError:
            pass
    return dupes
