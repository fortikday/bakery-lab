"""Rebuild the offline Bakery Lab dashboard and export the experiment results."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from analysis import ROOT, build_payload, load_data


def write_results(payload: dict, output_dir: Path = ROOT) -> None:
    results_dir = output_dir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    json_text = json.dumps(payload, ensure_ascii=False, allow_nan=False, indent=2)
    (results_dir / "summary.json").write_text(json_text, encoding="utf-8")
    rows = [{"store": store["id"], **prediction}
            for store in payload["stores"] for prediction in store["predictions"]]
    pd.DataFrame(rows, columns=["store", "date", "origin", "horizon", "actual", "baseline", "ml"]).to_csv(
        results_dir / "predictions.csv", index=False
    )
    metrics = [{"store": store["id"], **store["evaluation"]} for store in payload["stores"]]
    pd.DataFrame(metrics).to_csv(results_dir / "metrics.csv", index=False)
    template = (ROOT / "templates" / "dashboard.html").read_text(encoding="utf-8")
    if template.count("__BAKERY_DATA__") != 1:
        raise ValueError("Dashboard template must contain exactly one __BAKERY_DATA__ placeholder.")
    # Escape '<' inside JSON so an imported string cannot close the script tag.
    embedded = json.dumps(payload, ensure_ascii=False, allow_nan=False).replace("<", "\\u003c")
    (output_dir / "index.html").write_text(template.replace("__BAKERY_DATA__", embedded), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--holdout-days", type=int, default=56, help="Multiple of 7; default: 56")
    args = parser.parse_args()
    data = load_data()
    print(f"Loaded {len(data):,} observations across {data['store'].nunique()} stores.", flush=True)
    print("Comparing full-week forecasts on historical dates. This can take a minute.", flush=True)
    payload = build_payload(data, holdout_days=args.holdout_days)
    payload["meta"]["data_sha256"] = hashlib.sha256((ROOT / "data" / "train.csv").read_bytes()).hexdigest()
    write_results(payload)
    overall = payload["overall"]
    if overall["n_predictions"]:
        print(f"Scored {overall['n_predictions']} predictions from {overall['eligible_stores']} eligible stores.")
        print(f"Baseline MAE: {overall['baseline_mae']:.4f}; ML MAE: {overall['ml_mae']:.4f} scaled points.")
    print(f"Open this dashboard: {ROOT / 'index.html'}")


if __name__ == "__main__":
    main()
