def normalize(raw: list) -> list:
    result = []
    for record in raw:
        tags_str = record["tags"].strip()
        normalized = {
            "name": record["Name"].strip(),
            "age": int(record["age"]),
            "email": record["email"].strip().lower(),
            "tags": tags_str.split(",") if tags_str else []
        }
        result.append(normalized)
    return result
