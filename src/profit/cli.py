"""`python -m profit build` : entrepôt -> contrôles -> résultats -> figures -> tableau de bord -> exports -> note Word."""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from . import charts, dashboard, export, results
from .config import EXPORT_DIR, RAW_DIR, REPORT_DIR, ROOT
from .db import Warehouse


def cmd_build(a) -> int:
    wh = Warehouse.build(Path(a.raw_dir))
    chk = wh.checks()
    bad = chk[chk["violations"] > 0.005]
    print(f"Contrôles qualité : {len(chk) - len(bad)}/{len(chk)} OK")
    if len(bad):
        print(bad.to_string(index=False)); return 1
    REPORT_DIR.mkdir(exist_ok=True)
    res = results.collect(wh)
    results.save(res, REPORT_DIR / "results.json")
    figs = charts.make_all(wh, res, REPORT_DIR / "figures")
    dashboard.build(res, figs, REPORT_DIR / "dashboard.html")
    print(f"Tableau de bord : {REPORT_DIR / 'dashboard.html'}")
    if not a.no_export:
        counts = export.export_all(wh, EXPORT_DIR)
        print(f"Exports CSV : {len(counts)} tables + 3 agrégats -> {EXPORT_DIR}")
    node, script = shutil.which("node"), ROOT / "note" / "build_note.js"
    if not node:
        print("Note Word non générée : Node.js introuvable (installer Node puis `cd note && npm install && node build_note.js`).")
    elif not (ROOT / "note" / "node_modules" / "docx").exists() and subprocess.run([node, "-e", "require('docx')"], cwd=ROOT / "note", capture_output=True).returncode:
        print("Note Word non générée : module `docx` absent (`cd note && npm install`).")
    else:
        r = subprocess.run([node, str(script)], cwd=ROOT / "note", capture_output=True, text=True)
        print((r.stdout or r.stderr).strip())
        if r.returncode:
            return r.returncode
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="profit", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("build", help="tout régénérer")
    p.add_argument("--raw-dir", default=str(RAW_DIR)); p.add_argument("--no-export", action="store_true")
    p.set_defaults(fn=cmd_build)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
