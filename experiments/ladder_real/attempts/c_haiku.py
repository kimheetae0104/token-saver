def normalize(raw: list) -> list:
    return [
        {
            "name": record["Name"].strip(),
            "age": int(record["age"]),
            "email": record["email"].strip().lower(),
            "tags": record["tags"].strip().split(",") if record["tags"].strip() else []
        }
        for record in raw
    ]
