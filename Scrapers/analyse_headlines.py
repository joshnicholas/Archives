#!/usr/bin/env python3
"""
Headline analysis: group similar headlines across publications and extract named entities.

Usage:
    python analyse_headlines.py [options]

Options:
    --data PATH         Path to top_stories.json (default: Combined/top_stories.json)
    --sources KEY ...   Source keys to include (default: smh abc news graun age bris bbc)
    --n-groups N        Max groups to display (default: 10)
    --similarity FLOAT  Similarity cutoff 0.0–1.0; higher = stricter (default: 0.55)
    --ignore WORD ...   Extra words to strip from headlines before grouping
    --top-entities N    How many top entities to print (default: 30)
    --output PATH       Save full results to a JSON file

Dependencies:
    pip install sentence-transformers spacy scikit-learn
    python -m spacy download en_core_web_sm

GitHub Actions tip: cache ~/.cache/huggingface and ~/.cache/torch between runs
so the model (~22MB) is only downloaded once.
"""

import argparse
import json
import pathlib
import re
from collections import defaultdict

import numpy as np
import pandas as pd
from sentence_transformers import SentenceTransformer
from sklearn.cluster import AgglomerativeClustering
from sklearn.metrics.pairwise import cosine_similarity

DEFAULT_SOURCES = ["smh", "abc", "news", "graun", "age", "bris", "bbc"]

# Words that carry little subject meaning in news headlines.
# These are stripped before encoding so the model focuses on the actual topic.
NEWS_FILLER = {
    "says", "say", "said", "claims", "claim", "claimed", "reveals", "reveal",
    "revealed", "report", "reports", "reported", "warns", "warn", "warned",
    "hits", "hit", "slams", "slam", "slammed", "calls", "call", "called",
    "faces", "face", "faced", "breaks", "breaking", "exclusive", "update",
    "latest", "new", "news", "live", "watch", "video", "photos", "pictures",
    "opinion", "analysis", "explainer", "everything", "know", "need",
    "just", "now", "today", "first", "last", "year", "week", "day",
    "amid", "after", "before", "following", "amid",
}


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_headlines(data_path: pathlib.Path, sources: list[str]) -> pd.DataFrame:
    with open(data_path) as f:
        data = json.load(f)

    records = []
    for key in sources:
        val = data.get(key)
        if not val or not isinstance(val, list):
            print(f"  Warning: source '{key}' not found or empty in data.")
            continue
        for item in val:
            text = item.get("Headline", "")
            if not text:
                continue
            records.append({
                "headline": str(text).strip(),
                "url": item.get("Url", ""),
                "publication": item.get("publication", key),
                "rank": item.get("Rank"),
                "source_key": key,
            })

    return pd.DataFrame(records).drop_duplicates(subset="headline")


# ---------------------------------------------------------------------------
# Preprocessing
# ---------------------------------------------------------------------------

def preprocess(headline: str, extra_ignore: set[str] | None = None) -> str:
    """Strip filler words so the encoder focuses on subject matter."""
    ignore = NEWS_FILLER | (extra_ignore or set())
    tokens = re.findall(r"\b\w+\b", headline)
    kept = [t for t in tokens if t.lower() not in ignore]
    return " ".join(kept) if kept else headline


# ---------------------------------------------------------------------------
# Headline grouping
# ---------------------------------------------------------------------------

def group_headlines(
    df: pd.DataFrame,
    min_group_size: int = 3,
    similarity_cutoff: float = 0.55,
    extra_ignore: set[str] | None = None,
    model_name: str = "all-MiniLM-L6-v2",
) -> tuple[pd.DataFrame, dict]:
    """
    Embed headlines with a sentence-transformer then cluster by cosine similarity.

    similarity_cutoff: 0.0–1.0; two headlines must score at least this to be grouped.
                       ~0.4 is loose, ~0.6 is tight.
    min_group_size: only return clusters with at least this many headlines.
    """
    if len(df) < 2:
        print("Not enough headlines to cluster.")
        return df, {}

    print(f"  Loading model '{model_name}' …")
    model = SentenceTransformer(model_name)

    cleaned = [preprocess(h, extra_ignore) for h in df["headline"]]
    print(f"  Encoding {len(cleaned)} headlines …")
    embeddings = model.encode(cleaned, show_progress_bar=False, normalize_embeddings=True)

    sim_matrix = cosine_similarity(embeddings)
    dist_matrix = 1.0 - sim_matrix
    np.fill_diagonal(dist_matrix, 0.0)

    clusterer = AgglomerativeClustering(
        n_clusters=None,
        distance_threshold=1.0 - similarity_cutoff,
        metric="precomputed",
        linkage="average",
    )
    labels = clusterer.fit_predict(dist_matrix)

    df = df.copy()
    df["cluster"] = labels

    sizes = df["cluster"].value_counts()
    qualifying_ids = sizes[sizes >= min_group_size].sort_values(ascending=False).index.tolist()

    groups: dict[int, dict] = {}
    for rank, cid in enumerate(qualifying_ids, 1):
        rows = df[df["cluster"] == cid]
        idxs = rows.index.tolist()
        intra_sim = float(sim_matrix[np.ix_(idxs, idxs)].mean())
        groups[rank] = {
            "size": len(rows),
            "mean_similarity": round(intra_sim, 3),
            "headlines": rows[["headline", "publication", "url", "rank"]].to_dict(orient="records"),
        }

    return df, groups


# ---------------------------------------------------------------------------
# Named entity recognition
# ---------------------------------------------------------------------------

ENTITY_TYPES = {"PERSON", "ORG", "GPE", "LOC", "PRODUCT", "EVENT", "WORK_OF_ART", "LAW", "NORP"}


def extract_named_entities(df: pd.DataFrame, nlp) -> dict:
    """
    Returns a dict sorted by mention count (descending):
        entity → {count, type, mentions: [{url, headline, publication}]}
    """
    counts: dict[str, int] = defaultdict(int)
    urls: dict[str, list] = defaultdict(list)
    types: dict[str, str] = {}

    for _, row in df.iterrows():
        doc = nlp(row["headline"])
        seen: set[str] = set()
        for ent in doc.ents:
            if ent.label_ not in ENTITY_TYPES:
                continue
            name = ent.text.strip()
            if not name or name in seen:
                continue
            seen.add(name)
            counts[name] += 1
            urls[name].append({
                "url": row["url"],
                "headline": row["headline"],
                "publication": row["publication"],
            })
            types[name] = ent.label_

    return {
        name: {"count": count, "type": types[name], "mentions": urls[name]}
        for name, count in sorted(counts.items(), key=lambda x: x[1], reverse=True)
    }


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def print_groups(groups: dict, similarity_cutoff: float, min_group_size: int) -> None:
    print(f"\n{'=' * 60}")
    print(f"HEADLINE GROUPS  (similarity: {similarity_cutoff}, min size: {min_group_size})  —  {len(groups)} group(s) found")
    print(f"{'=' * 60}")

    if not groups:
        print("No groups found. Try lowering --similarity.")
        return

    for rank, group in groups.items():
        print(
            f"\nGroup {rank}  ({group['size']} headlines, "
            f"mean similarity: {group['mean_similarity']})"
        )
        for item in group["headlines"]:
            pub = f"[{item['publication']}]"
            print(f"  {pub:20s} {item['headline']}")


def print_entities(entities: dict, top_n: int = 30) -> None:
    print(f"\n{'=' * 60}")
    print(f"NAMED ENTITIES  (top {top_n})")
    print(f"{'=' * 60}")

    if not entities:
        print("No entities found.")
        return

    for name, info in list(entities.items())[:top_n]:
        print(f"\n{name}  ({info['type']})  —  {info['count']} mention(s)")
        for mention in info["mentions"]:
            pub = f"[{mention['publication']}] " if mention["publication"] else ""
            print(f"  {pub}{mention['headline']}")
            if mention["url"]:
                print(f"    {mention['url']}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Analyse scraped headlines")
    parser.add_argument("--data", default="Combined/top_stories.json")
    parser.add_argument(
        "--sources", nargs="+", default=DEFAULT_SOURCES,
        help=f"Source keys to include (default: {' '.join(DEFAULT_SOURCES)})",
    )
    parser.add_argument(
        "--min-group-size", type=int, default=3,
        help="Minimum number of headlines for a cluster to be shown (default 3)",
    )
    parser.add_argument(
        "--similarity", type=float, default=0.55,
        help="Cosine similarity cutoff 0.0–1.0 (default 0.55)",
    )
    parser.add_argument(
        "--ignore", nargs="+", default=[],
        help="Extra words to strip from headlines before grouping",
    )
    parser.add_argument("--top-entities", type=int, default=30)
    parser.add_argument("--output", default=None, help="Save full results to this JSON file")
    args = parser.parse_args()

    data_path = pathlib.Path(args.data)
    if not data_path.is_absolute():
        data_path = pathlib.Path(__file__).parent.parent / data_path

    print(f"Loading from {data_path}")
    print(f"Sources: {args.sources}")
    df = load_headlines(data_path, sources=args.sources)

    if df.empty:
        print("No headlines found. Check --data path or --sources.")
        return

    print(f"Loaded {len(df)} headlines from {df['publication'].nunique()} publication(s).")

    extra_ignore = {w.lower() for w in args.ignore}

    # --- grouping ---
    _, groups = group_headlines(
        df,
        min_group_size=args.min_group_size,
        similarity_cutoff=args.similarity,
        extra_ignore=extra_ignore,
    )
    print_groups(groups, args.similarity, args.min_group_size)

    # --- NER ---
    entities: dict = {}
    try:
        import spacy  # noqa: PLC0415
        nlp = spacy.load("en_core_web_sm")
        entities = extract_named_entities(df, nlp)
        print_entities(entities, top_n=args.top_entities)
    except ImportError:
        print("\n[NER skipped] Install spaCy: pip install spacy")
    except OSError:
        print("\n[NER skipped] Download model: python -m spacy download en_core_web_sm")

    # --- optional JSON output ---
    if args.output:
        out = {"groups": groups, "entities": entities}
        with open(args.output, "w") as f:
            json.dump(out, f, indent=2)
        print(f"\nResults saved to {args.output}")


if __name__ == "__main__":
    main()
