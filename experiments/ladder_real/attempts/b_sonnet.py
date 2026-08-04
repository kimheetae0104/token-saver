from typing import Any, List, Optional


def find_duplicates(items: List[Any], seen: Optional[List[Any]] = None) -> List[Any]:
    if seen is None:
        seen = []
    dupes: List[Any] = []
    for i in items:
        try:
            if i in seen:
                dupes.append(i)
            else:
                seen.append(i)
        except TypeError:
            pass
    return dupes
