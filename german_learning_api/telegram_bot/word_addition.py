import unicodedata

PARTS_OF_SPEECH = ("noun", "verb", "adj", "adv")


def normalize_text(value: str) -> str:
    return unicodedata.normalize("NFC", " ".join(value.split()))


def chosen_translations(data: dict) -> list[dict]:
    available = {item["id"]: item["value"] for item in data.get("available_translations", [])}
    chosen = [
        {"key": f"base:{translation_id}", "value": available[translation_id], "custom": False}
        for translation_id in data.get("selected_base_ids", [])
        if translation_id in available
    ]
    if custom := data.get("custom_translation"):
        chosen.append({"key": "custom", "value": custom, "custom": True})
    return chosen


def selection_payload(data: dict) -> dict | None:
    selected_ids = data.get("selected_base_ids", [])
    custom = data.get("custom_translation")
    if not selected_ids and not custom:
        return None
    primaries = set(data.get("primary_keys", []))
    return {
        "base_translation_ids": selected_ids,
        "primary_base_translation_ids": [item for item in selected_ids if f"base:{item}" in primaries],
        "custom_translation": custom,
        "custom_is_card_primary": "custom" in primaries,
    }
