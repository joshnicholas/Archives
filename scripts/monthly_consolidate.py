import json
import re
import tempfile
from pathlib import Path

import duckdb

sources = [
    Path("Archive/smh_top"),
    Path("Archive/abc_top"),
    Path("Archive/newscom_top"),
    Path("Archive/graun_top"),
    Path("Archive/age"),
    Path("Archive/brisbane_times"),
    Path("Archive/bbc_top"),
    Path("Archive/google_top"),
    Path("Archive/wiki"),
    Path("Archive/wiki_edits"),
    Path("Archive/bsky"),
    Path("Archive/google_trends_rss"),
]

# Dump files are processed in batches rather than all at once. Most sources only ever have
# a month's worth of files here, but a source that's never been consolidated before (or that
# missed several runs) can have years of backlog — e.g. wiki/daily_dumps had ~19k files going
# back to 2017. Handing DuckDB all of those in one read_json/COPY call made it try to hold the
# whole backlog (plus schema-union bookkeeping across thousands of files) in memory at once,
# which is what blew past the default memory_limit and OOM'd. Batching bounds the working set
# per call regardless of how big the backlog is.
BATCH_SIZE = 2000


def chunked(items: list, size: int) -> list:
    return [items[i : i + size] for i in range(0, len(items), size)]


# Every dump filename observed across sources starts with a 4-digit year, whatever comes
# after it — "2017-12-29.json", "2021_02_20_10.json", "20230515.json" all match. Using the
# filename rather than parsing scraped_datetime out of the file's own content means this works
# even for the handful of legacy CSV files that don't carry a scraped_datetime field at all.
YEAR_RE = re.compile(r"^(\d{4})")


def year_of(dump_file: Path) -> str:
    match = YEAR_RE.match(dump_file.stem)
    if not match:
        raise ValueError(f"can't determine year from filename: {dump_file}")
    return match.group(1)


def classify(dump_file: Path) -> str:
    """Return 'csv', 'double_encoded', or 'json' for a dump file.

    A batch of old wiki dumps (2017-12-29 through 2023-05-14) were written by a scraper bug
    that ran json.dumps() on already-serialized JSON text, so the file's top-level value is a
    JSON *string* containing the real array, not the array itself — DuckDB's JSON reader sees
    those as a single opaque string column unless unwrapped first. Detected by sniffing the
    first non-whitespace byte: a real JSON array/object starts with '[' or '{', the
    double-encoded ones start with '"'.
    """
    if dump_file.suffix == ".csv":
        return "csv"
    with dump_file.open("rb") as f:
        head = f.read(256).lstrip()
    return "double_encoded" if head.startswith(b'"') else "json"


def unwrap_double_encoded(dump_file: Path, out_path: Path) -> None:
    with dump_file.open() as f:
        inner_json_text = json.load(f)  # outer value is itself a JSON string
    out_path.write_text(inner_json_text)


def consolidate(source_dir: Path) -> None:
    dump_files = sorted(
        p for p in source_dir.glob("daily_dumps/*") if p.suffix in (".json", ".csv")
    )
    if not dump_files:
        return  # nothing scraped since last month's run — leave the existing file untouched

    # One parquet file per calendar year, inside the source's own folder, rather than one
    # ever-growing monolithic file: keeps individual files well under GitHub's 100MB push
    # limit and means a month with a few new rows only touches (and re-commits) that one
    # year's file instead of rewriting the whole source's history every run.
    yearly_dir = source_dir / "yearly_dumps"
    yearly_dir.mkdir(parents=True, exist_ok=True)

    files_by_year: dict[str, list[Path]] = {}
    for dump_file in dump_files:
        files_by_year.setdefault(year_of(dump_file), []).append(dump_file)

    with tempfile.TemporaryDirectory(prefix="duckdb_consolidate_") as tmp_dir_str:
        tmp_dir = Path(tmp_dir_str)
        con = duckdb.connect()
        # Lets DuckDB spill to disk instead of OOMing on a batch that's still bigger than
        # expected. The default in-memory connection has no temp_directory, so without this
        # it has nowhere to spill and just dies at the memory_limit instead.
        con.execute(f"SET temp_directory = '{tmp_dir}'")
        con.execute("SET preserve_insertion_order = false")

        for year, year_files in files_by_year.items():
            parquet_path = yearly_dir / f"{year}.parquet"

            for batch in chunked(year_files, BATCH_SIZE):
                json_like_files = []  # real json files, plus double-encoded ones unwrapped to temp copies
                csv_files = []

                for dump_file in batch:
                    kind = classify(dump_file)
                    if kind == "csv":
                        csv_files.append(str(dump_file))
                    elif kind == "double_encoded":
                        unwrapped = tmp_dir / f"{dump_file.stem}.unwrapped.json"
                        unwrap_double_encoded(dump_file, unwrapped)
                        json_like_files.append(str(unwrapped))
                    else:
                        json_like_files.append(str(dump_file))

                # union_by_name: not every dump file necessarily has identical columns in the
                # same order (confirmed real option against DuckDB's CSV/JSON reader docs) —
                # align by column name instead of position so that's never a silent
                # data-shuffling bug. This also carries real schema drift on purpose (e.g.
                # wiki's pre-2023-05-15 trending-topic rows vs its later pageview rows): both
                # land in the same year's file with the columns that don't apply to a given
                # row left null, rather than losing either shape.
                parts = []
                if json_like_files:
                    json_rel = con.read_json(json_like_files, union_by_name=True)
                    con.register("batch_json", json_rel)
                    parts.append("SELECT * FROM batch_json")
                if csv_files:
                    csv_rel = con.read_csv(csv_files, union_by_name=True)
                    con.register("batch_csv", csv_rel)
                    parts.append("SELECT * FROM batch_csv")
                new_rows_query = " UNION ALL BY NAME ".join(parts)

                if parquet_path.exists():
                    query = "{} UNION ALL BY NAME SELECT * FROM read_parquet('{}')".format(
                        new_rows_query, parquet_path
                    )
                else:
                    query = new_rows_query

                # Reading from and writing to the SAME path in one statement "is not
                # guaranteed to be safe" — DuckDB's own COPY docs say so explicitly — so the
                # result is written to a different path first, then swapped in, rather than
                # unioning parquet_path into a COPY that also targets parquet_path itself.
                tmp_path = parquet_path.with_suffix(".tmp.parquet")
                con.sql(f"COPY ({query}) TO '{tmp_path}' (FORMAT PARQUET)")
                tmp_path.replace(parquet_path)  # same-filesystem rename — atomic, can't leave a half file

                # Deleting only this batch's source files (not all of dump_files) means a
                # later batch crashing still leaves everything consolidated so far safely
                # swapped into its year's file, with just the unprocessed remainder left to
                # retry next run.
                for dump_file in batch:
                    dump_file.unlink()


def main() -> None:
    print(sources)
    for source_dir in sources:
        consolidate(source_dir)


if __name__ == "__main__":
    main()
