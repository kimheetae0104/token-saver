def normalize(raw: list) -> list:
    result = []
    for rec in raw:
        tags = rec["tags"].strip()
        result.append({
            "name": rec["Name"].strip(),
            "age": int(rec["age"]),
            "email": rec["email"].strip().lower(),
            "tags": tags.split(",") if tags else [],
        })
    return result
