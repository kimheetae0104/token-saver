def normalize(raw: list) -> list:
    result = []
    for record in raw:
        normalized = {
            "name": record["Name"].strip(),
            "age": int(record["age"]),
            "email": record["email"].strip().lower(),
            "tags": [tag.strip() for tag in record["tags"].split(",") if tag.strip()]
        }
        result.append(normalized)
    return result
