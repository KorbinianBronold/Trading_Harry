"""Beschriftet BESTEHENDE Predictions nachtraeglich ueber mehrere Haltedauern.

Anders als die Fundamental-Rohwerte (C.20) ist das hier moeglich: die Tagesbars
liegen vollstaendig in price_history. Jede Prediction bekommt je Handelstag bis
MAX_HOLD_DAYS eine Zeile in outcome_horizons -- Schlusskurs, Rendite, ob TP/SL
bis dahin gefallen waeren, ob die Richtung stimmte.

Idempotent (INSERT OR REPLACE auf (prediction_id, horizon_days)): ein zweiter
Lauf korrigiert, statt zu verdoppeln.

    python setup/backfill_horizons.py --db-path data/tracking.db [--dry-run]
"""
import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from src import db
from src.evaluator import horizon_labels, _bar_sequence

log = logging.getLogger("backfill_horizons")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", default=str(config.DB_PATH))
    parser.add_argument("--dry-run", action="store_true",
                        help="nur zaehlen, nichts schreiben")
    ns = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    conn = db.connect(ns.db_path)
    db.init_schema(conn)
    preds = conn.execute(
        """SELECT * FROM predictions
            WHERE entry_price IS NOT NULL AND tp_price IS NOT NULL
              AND sl_price IS NOT NULL
            ORDER BY id"""
    ).fetchall()

    written = skipped = 0
    for pred in preds:
        # Kein Provider: der Backfill liest ausschliesslich aus price_history.
        # Fehlende Bars sind hier kein Fehler, sondern eine junge Prediction.
        ohlc = _bar_sequence(conn, None, pred)
        if ohlc is None or ohlc.empty:
            skipped += 1
            continue
        rows = horizon_labels(
            ohlc, entry=float(pred["entry_price"]),
            tp=float(pred["tp_price"]), sl=float(pred["sl_price"]),
            direction=pred["direction"],
            # ohne Provider gibt es keine Signaltag-Bar -- Tag 1 ist hier D+1
            includes_signal_day=False,
        )
        if not rows:
            skipped += 1
            continue
        if not ns.dry_run:
            db.save_outcome_horizons(conn, pred["id"], rows)
        written += 1
        log.info(f"  #{pred['id']:<4}{pred['ticker']:<9}{pred['direction']:<6}"
                 f"{len(rows)} Horizonte")

    verb = "wuerde schreiben" if ns.dry_run else "beschriftet"
    log.info(f"\n{verb}: {written} Predictions, uebersprungen (keine Bars): {skipped}")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
