def normalize(raw: list) -> list:
    result = []
    for record in raw:
        normalized = {
            "name": record.get("Name", "").strip(),
            "age": int(record.get("age", 0)),
            "email": record.get("email", "").strip().lower(),
            "tags": [tag.strip() for tag in record.get("tags", "").split(",") if tag.strip()]
        }
        result.append(normalized)
    return result
