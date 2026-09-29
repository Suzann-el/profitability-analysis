"""Télécharge les tables AdventureWorksDW (CSV) depuis le dépôt Microsoft `sql-server-samples` (licence MIT).

Usage : python scripts/download_data.py [--dest data/raw]
Vérifie la taille et l'empreinte SHA-256 de chaque fichier (manifest `data/manifest.json`) pour garantir
que les résultats du projet portent bien sur les mêmes données.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

BASE = ("https://raw.githubusercontent.com/microsoft/sql-server-samples/master/samples/databases/"
        "adventure-works/data-warehouse-install-script")
TABLES = ["FactResellerSales", "FactInternetSales", "DimProduct", "DimProductSubcategory", "DimProductCategory",
          "DimDate", "DimReseller", "DimCustomer", "DimGeography", "DimSalesTerritory", "DimPromotion", "DimCurrency"]
MANIFEST = Path(__file__).resolve().parents[1] / "data" / "manifest.json"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dest", default="data/raw")
    ap.add_argument("--update-manifest", action="store_true", help="réécrit le manifest (à ne faire que sciemment)")
    a = ap.parse_args(argv)
    dest = Path(a.dest)
    dest.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() and not a.update_manifest else {}
    new = {}
    for t in TABLES:
        path = dest / f"{t}.csv"
        if not path.exists() or path.stat().st_size == 0:
            print(f"Téléchargement {t}.csv …", flush=True)
            urllib.request.urlretrieve(f"{BASE}/{t}.csv", path)
        digest = sha256(path)
        new[t] = {"bytes": path.stat().st_size, "sha256": digest}
        if t in manifest and manifest[t]["sha256"] != digest:
            print(f"ERREUR : {t}.csv diffère du manifest (données modifiées en amont ?)", file=sys.stderr)
            return 1
    if a.update_manifest or not manifest:
        MANIFEST.write_text(json.dumps(new, indent=2))
        print(f"Manifest écrit : {MANIFEST}")
    else:
        print("Toutes les empreintes correspondent au manifest ✔")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
