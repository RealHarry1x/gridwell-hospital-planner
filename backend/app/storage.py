"""Small SQLite repository. JSON payloads keep the prototype easy to inspect."""

import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parents[2] / "data" / "demo.sqlite3"


class Store:
    def __init__(self, path=None):
        self.path = str(path or os.environ.get("GRIDWELL_DB_PATH", DEFAULT_DB))
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS plans (
                    id TEXT PRIMARY KEY, date TEXT NOT NULL, revision INTEGER NOT NULL,
                    status TEXT NOT NULL, payload TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS history (
                    date TEXT PRIMARY KEY, payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS presets (
                    id TEXT PRIMARY KEY, payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS plans_date_idx ON plans(date);
            """)

    @contextmanager
    def connection(self):
        conn = sqlite3.connect(self.path, timeout=15)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def meta(self, key, default=None):
        with self.connection() as conn:
            result = conn.execute("SELECT value FROM metadata WHERE key=?", (key,)).fetchone()
            return json.loads(result["value"]) if result else default

    def set_meta(self, key, value):
        with self.connection() as conn:
            conn.execute("INSERT OR REPLACE INTO metadata VALUES (?,?)", (key, json.dumps(value)))

    def save_plan(self, plan):
        with self.connection() as conn:
            conn.execute("""INSERT INTO plans(id,date,revision,status,payload) VALUES (?,?,?,?,?)
                          ON CONFLICT(id) DO UPDATE SET revision=excluded.revision,
                          status=excluded.status,payload=excluded.payload""",
                         (plan["id"], plan["date"], plan["revision"], plan["status"], json.dumps(plan)))

    def get_plan(self, plan_id):
        with self.connection() as conn:
            row = conn.execute("SELECT payload FROM plans WHERE id=?", (plan_id,)).fetchone()
            return json.loads(row["payload"]) if row else None

    def latest_plan(self, day):
        with self.connection() as conn:
            row = conn.execute("SELECT payload FROM plans WHERE date=? ORDER BY rowid DESC LIMIT 1", (str(day),)).fetchone()
            return json.loads(row["payload"]) if row else None

    def history(self, limit=30, before=None):
        with self.connection() as conn:
            where, params = ("WHERE date < ?", (str(before), limit)) if before else ("", (limit,))
            return [json.loads(row["payload"]) for row in conn.execute(f"SELECT payload FROM history {where} ORDER BY date DESC LIMIT ?", params)][::-1]

    def carry(self, day, capacity):
        with self.connection() as conn:
            row = conn.execute("SELECT payload FROM history WHERE date < ? ORDER BY date DESC LIMIT 1", (str(day),)).fetchone()
        if row:
            previous = json.loads(row["payload"])
            return {"energy_kwh": previous["battery_soc_end_kwh"], "from_date": previous["date"],
                    "source": previous["source"], "first_day": False,
                    "note": "Carried from the last recorded simulated day. Unapproved dates do not consume energy."}
        initial = self.meta("initial_soc_pct", 70)
        return {"energy_kwh": capacity * initial / 100, "from_date": None, "source": "initial assumption",
                "first_day": True, "note": f"First simulated day only: adjustable {initial:g}% opening assumption."}

    def save_history(self, entry):
        with self.connection() as conn:
            conn.execute("INSERT OR REPLACE INTO history VALUES (?,?)", (entry["date"], json.dumps(entry)))

    def approve(self, plan, entry):
        # The carry check, approval and downstream invalidation are one write
        # transaction so two tabs cannot create inconsistent simulation history.
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            current = conn.execute("SELECT payload FROM plans WHERE id=?", (plan["id"],)).fetchone()
            if not current or json.loads(current["payload"])["revision"] != plan["revision"]:
                raise ValueError("Plan changed in another tab. Reload and review it.")
            previous = conn.execute("SELECT payload FROM history WHERE date < ? ORDER BY date DESC LIMIT 1", (plan["date"],)).fetchone()
            if previous and abs(json.loads(previous["payload"])["battery_soc_end_kwh"] - plan["battery_carry"]["energy_kwh"]) > 1e-5:
                raise ValueError("Opening battery carry has changed. Recalculate before approval.")
            # Re-approving the same revision is idempotent: it must not erase
            # newer approvals or seeded records.
            if json.loads(current["payload"])["status"] == "approved":
                return []
            future = list(conn.execute("SELECT id,payload FROM plans WHERE date > ?", (plan["date"],)))
            conn.execute("DELETE FROM history WHERE date >= ?", (plan["date"],))
            invalidated = []
            for row in future:
                downstream = json.loads(row["payload"])
                downstream["status"] = "stale"
                conn.execute("UPDATE plans SET status='stale',payload=? WHERE id=?", (json.dumps(downstream), row["id"]))
                invalidated.append(row["id"])
            conn.execute("UPDATE plans SET status='approved',payload=? WHERE id=?", (json.dumps(plan), plan["id"]))
            conn.execute("INSERT INTO history VALUES (?,?)", (entry["date"], json.dumps(entry)))
        return invalidated

    def presets(self):
        with self.connection() as conn:
            return [json.loads(row["payload"]) for row in conn.execute("SELECT payload FROM presets ORDER BY rowid")]

    def save_preset(self, preset):
        with self.connection() as conn:
            conn.execute("INSERT OR REPLACE INTO presets VALUES (?,?)", (preset["id"], json.dumps(preset)))

    def delete_preset(self, preset_id):
        with self.connection() as conn:
            return conn.execute("DELETE FROM presets WHERE id=?", (preset_id,)).rowcount

    def reset(self, initial_soc_pct):
        with self.connection() as conn:
            counts = {"deleted_plans": conn.execute("SELECT COUNT(*) FROM plans").fetchone()[0],
                      "deleted_history_records": conn.execute("SELECT COUNT(*) FROM history").fetchone()[0],
                      "kept_custom_presets": conn.execute("SELECT COUNT(*) FROM presets").fetchone()[0]}
            for table in ("plans", "history", "metadata"):
                conn.execute(f"DELETE FROM {table}")
            conn.execute("INSERT INTO metadata VALUES ('initial_soc_pct',?)", (json.dumps(initial_soc_pct),))
        return counts
