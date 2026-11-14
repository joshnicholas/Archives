"""One-time migration: split each source's monolithic Archive/<source>.parquet into
Archive/<source>/yearly_dumps/<year>.parquet files, matching the layout monthly_consolidate.py
now writes going forward. Run once; re-running is harmless (it just skips sources that have
already been migrated, since it only acts on a monolithic file if one still exists).
"""

import duckdb

from monthly_consolidate import sources


def split(source_dir) -> None:
    old_parquet = source_dir.with_suffix(".parquet")
    if not old_parquet.exists():
        return  # already migrated, or this source has never been consolidated

    yearly_dir = source_dir / "yearly_dumps"
    yearly_dir.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect()
    # scraped_datetime shows up in a few different formats across sources and eras
    # ("2017-12-29", "2021_02_20_10", "20230515"), but all of them start with the 4-digit
    # year, so a plain substring works without needing to parse each format. A handful of
    # legacy rows (from two stray CSV dumps that predated scraped_datetime being recorded at
    # all) have no value there — those land in an honest "unknown" bucket rather than being
    # guessed into a year that isn't actually recorded anywhere.
    year_expr = "COALESCE(substr(scraped_datetime, 1, 4), 'unknown')"
    years = [row[0] for row in con.sql(
        f"SELECT DISTINCT {year_expr} FROM read_parquet('{old_parquet}')"
    ).fetchall()]

    total_before = con.sql(f"SELECT count(*) FROM read_parquet('{old_parquet}')").fetchone()[0]
    total_after = 0
    for year in years:
        if year != "unknown" and not year.isdigit():
            raise ValueError(f"{source_dir.name}: unexpected year value {year!r}")
        out_path = yearly_dir / f"{year}.parquet"
        con.sql(
            f"COPY (SELECT * FROM read_parquet('{old_parquet}') WHERE {year_expr} = '{year}') "
            f"TO '{out_path}' (FORMAT PARQUET)"
        )
        rows = con.sql(f"SELECT count(*) FROM read_parquet('{out_path}')").fetchone()[0]
        total_after += rows
        print(f"{source_dir.name}: {out_path} ({rows} rows)")

    if total_after != total_before:
        raise AssertionError(
            f"{source_dir.name}: row count mismatch after split "
            f"({total_before} before, {total_after} after) — not removing the original file"
        )

    # Renamed rather than deleted: these parquet files were never committed to git (the
    # consolidation that produced them hadn't been committed yet either), so there's no git
    # history to fall back on if this script has a bug. Safe to delete by hand once checked.
    old_parquet.rename(old_parquet.with_suffix(".parquet.bak"))


def main() -> None:
    for source_dir in sources:
        split(source_dir)


if __name__ == "__main__":
    main()
