def detect_family(model: str | None) -> str | None:
    if not model:
        return None

    model = model.upper()

    # Catalyst 9200 family
    if model.startswith("C9200"):
        return "C9200"

    # Catalyst 9300 family
    if model.startswith("C9300"):
        return "C9300"

    # Catalyst 9500 family
    if model.startswith("C9500"):
        return "C9500"

    # Catalyst 2960X
    if model.startswith("WS-C2960X") or model.startswith("C2960X"):
        return "C2960X"

    # Catalyst 2960
    if model.startswith("WS-C2960"):
        return "C2960"

    # Nexus (ejemplo)
    if model.startswith("N9K"):
        return "N9K"

    return None
