def normalize(raw: list) -> list:
    return [
        {
            "name": record["Name"].strip(),
            "age": int(record["age"]),
            "email": record["email"].strip().lower(),
            "tags": record["tags"].split(",") if record["tags"] else []
        }
        for record in raw
    ]
