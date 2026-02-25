import re
from collections import defaultdict

ENTITY_TYPES = {"PERSON", "ORG", "GPE", "LOC", "NORP", "EVENT", "FAC"}

HONORIFICS = re.compile(
    r"^(Mr|Mrs|Ms|Miss|Dr|Prof|Professor|PM|Senator|Rep|President|Minister"
    r"|Sir|Dame|Lord|Lady|Justice|Judge|Cllr|Cr|MP|MLA|CEO|Gen|Lt|Sgt|Cpl)\b\.?\s*",
    re.IGNORECASE,
)

ARTICLES = re.compile(r"^(the|a|an)\s+", re.IGNORECASE)


def records_from_dicto(dicto, sources):
    records = []
    for key in sources:
        val = dicto.get(key)
        if not val or not isinstance(val, list):
            continue
        for item in val:
            text = item.get("Headline", "")
            if not text:
                continue
            records.append({
                "headline": str(text).strip(),
                "url": item.get("Url", ""),
                "publication": item.get("publication", key),
            })
    seen = set()
    unique = []
    for r in records:
        if r["headline"] not in seen:
            seen.add(r["headline"])
            unique.append(r)
    return unique


def normalise(name):
    name = re.sub(r"'s$", "", name)
    name = HONORIFICS.sub("", name)
    name = ARTICLES.sub("", name)
    return " ".join(name.split()).strip()


def merge_variants(entity_map):
    names = sorted(entity_map.keys(), key=len, reverse=True)
    canonical = {}
    for i, longer in enumerate(names):
        for shorter in names[i + 1:]:
            if shorter in longer and shorter not in canonical:
                canonical[shorter] = longer
    merged = {}
    for name, data in entity_map.items():
        target = canonical.get(name, name)
        if target not in merged:
            merged[target] = {"count": 0, "type": data["type"], "mentions": []}
        merged[target]["count"] += data["count"]
        merged[target]["mentions"].extend(data["mentions"])
    return merged


def extract_entities(records, nlp):
    entity_map = defaultdict(lambda: {"count": 0, "type": "", "mentions": []})
    for record in records:
        doc = nlp(record["headline"])
        seen = set()
        for ent in doc.ents:
            if ent.label_ not in ENTITY_TYPES:
                continue
            norm = normalise(ent.text.strip())
            if not norm or norm.lower() in seen:
                continue
            seen.add(norm.lower())
            entity_map[norm]["count"] += 1
            entity_map[norm]["type"] = ent.label_
            entity_map[norm]["mentions"].append({
                "headline": record["headline"],
                "url": record["url"],
                "publication": record["publication"],
            })
    merged = merge_variants(dict(entity_map))
    return dict(sorted(merged.items(), key=lambda x: x[1]["count"], reverse=True))
