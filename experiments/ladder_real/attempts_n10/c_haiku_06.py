def normalize(raw: list) -> list:
    result = []
    for record in raw:
        tags_str = record["tags"].strip()
        tags = [tag.strip() for tag in tags_str.split(",")] if tags_str else []
        normalized = {
            "name": record["Name"].strip(),
            "age": int(record["age"]),
            "email": record["email"].strip().lower(),
            "tags": tags
        }
        result.append(normalized)
    return result
