"""Task C oracle — data transform+schema. 지저분한 레코드를 스키마에 맞게 정규화."""
import jsonschema

RAW = [
    {"Name": " Alice ", "age": "29", "email": "ALICE@Example.com", "tags": "admin,user"},
    {"Name": "bob", "age": 41, "email": "bob@example.com ", "tags": ""},
    {"Name": " Carol", "age": "17", "email": "Carol@EXAMPLE.com", "tags": "user"},
]

SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "minLength": 1},
            "age": {"type": "integer", "minimum": 0},
            "email": {"type": "string", "pattern": r"^[^@]+@[^@]+\.[a-z]+$"},
            "tags": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["name", "age", "email", "tags"],
        "additionalProperties": False,
    },
}

EXPECTED = [
    {"name": "Alice", "age": 29, "email": "alice@example.com", "tags": ["admin", "user"]},
    {"name": "bob", "age": 41, "email": "bob@example.com", "tags": []},
    {"name": "Carol", "age": 17, "email": "carol@example.com", "tags": ["user"]},
]


def check(candidate_output):
    try:
        jsonschema.validate(candidate_output, SCHEMA)
    except jsonschema.ValidationError as e:
        return False, [f"schema violation: {e.message}"]
    if candidate_output != EXPECTED:
        diffs = []
        for i, (got, exp) in enumerate(zip(candidate_output, EXPECTED)):
            if got != exp:
                diffs.append(f"record {i}: expected {exp}, got {got}")
        return False, diffs or ["length mismatch"]
    return True, []


if __name__ == "__main__":
    def reference(raw):
        out = []
        for r in raw:
            tags = [t for t in r["tags"].split(",") if t]
            out.append({
                "name": r["Name"].strip(),
                "age": int(r["age"]),
                "email": r["email"].strip().lower(),
                "tags": tags,
            })
        return out
    ok, errs = check(reference(RAW))
    print("OK" if ok else errs)
