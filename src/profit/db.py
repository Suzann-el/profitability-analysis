"""Construction de l'entrepôt DuckDB et exécution des requêtes SQL nommées (`-- name: xxx`)."""
from __future__ import annotations

import re
from pathlib import Path

import duckdb
import pandas as pd

from .config import PARAMS, RAW_DIR, SQL_DIR

_BLOCK = re.compile(r"^-- name: (\w+)[^\n]*\n", re.M)


def render(sql: str, params: dict[str, str]) -> str:
    for k, v in params.items():
        sql = sql.replace("${" + k + "}", v)
    left = re.findall(r"\$\{(\w+)\}", sql)
    if left:
        raise KeyError(f"paramètres SQL non résolus : {sorted(set(left))}")
    return sql


def named_queries(path: Path) -> dict[str, str]:
    """Découpe un fichier SQL en requêtes nommées ; retire les commentaires de ligne complets."""
    parts = _BLOCK.split(path.read_text(encoding="utf-8"))[1:]
    out = {}
    for name, body in zip(parts[::2], parts[1::2]):
        lines = [l for l in body.splitlines() if not l.strip().startswith("--")]
        out[name] = "\n".join(lines).strip().rstrip(";")
    return out


class Warehouse:
    def __init__(self, con: duckdb.DuckDBPyConnection, params: dict[str, str]):
        self.con, self.params = con, params
        self._queries: dict[str, str] = {}
        for f in sorted(SQL_DIR.glob("0[2-9]_*.sql")):
            self._queries.update(named_queries(f))

    @classmethod
    def build(cls, raw_dir: Path = RAW_DIR, params: dict[str, str] | None = None, db_path: str | Path = ":memory:") -> "Warehouse":
        params = params or PARAMS
        if not (Path(raw_dir) / "FactResellerSales.csv").exists():
            raise FileNotFoundError(f"CSV introuvables dans {raw_dir} : lancer `python scripts/download_data.py`")
        con = duckdb.connect(str(db_path))
        for f in ("00_staging.sql", "01_model.sql"):
            con.execute(render((SQL_DIR / f).read_text(encoding="utf-8"), {**params, "RAW_DIR": str(raw_dir)}))
        wh = cls(con, params)
        for f in sorted(SQL_DIR.glob("0[3-9]_*.sql")):          # objets dérivés (vues / tables) dans l'ordre des fichiers
            for name, sql in named_queries(f).items():
                if name.startswith("create_"):
                    con.execute(render(sql, params))
        return wh

    def query(self, name: str) -> pd.DataFrame:
        if name not in self._queries:
            raise KeyError(f"requête SQL inconnue : {name}")
        return self.con.execute(render(self._queries[name], self.params)).fetchdf()

    def checks(self) -> pd.DataFrame:
        rows = [(n, float(self.con.execute(render(s, self.params)).fetchone()[0])) for n, s in self._queries.items() if n.startswith("chk_")]
        return pd.DataFrame(rows, columns=["check", "violations"])
