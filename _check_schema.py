"""Quick sanity check for schema changes."""
from regrisk.tracing.db import TraceDB
import tempfile, os

db = TraceDB(os.path.join(tempfile.mkdtemp(), "test.db"))
cols = [r["name"] for r in db._conn.execute("PRAGMA table_info(llm_calls)").fetchall()]
print("New columns:", "validation_passed" in cols and "parsed_output" in cols)
tables = [r[0] for r in db._conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print("run_metrics:", "run_metrics" in tables)
print("run_comparisons:", "run_comparisons" in tables)
db.close()
print("PASS")
