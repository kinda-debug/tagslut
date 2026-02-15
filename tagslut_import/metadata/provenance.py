# Provenance helper for metadata cascade (policy compliance)

def write_provenance_json(metadata: dict, path: str) -> None:
    """Write provenance information to a JSON file."""
    import json
    with open(path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)
