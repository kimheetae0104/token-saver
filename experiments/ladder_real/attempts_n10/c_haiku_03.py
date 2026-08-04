def normalize(raw: list) -> list:
    result = []
    for record in raw:
        normalized = {
            "name": record["Name"].strip(),
            "age": int(record["age"]),
            "email": record["email"].strip().lower(),
            "tags": record["tags"].strip().split(",") if record["tags"].strip() else []
        }
        result.append(normalized)
    return result
