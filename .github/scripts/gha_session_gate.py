"""Print GITHUB_OUTPUT flags for the NSE session workflow."""
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from market_hours import gha_session_phases, now_ist  # noqa: E402

morning, afternoon = gha_session_phases()
now = now_ist()
lines = (
    f"run_morning={str(morning).lower()}\n"
    f"run_afternoon={str(afternoon).lower()}\n"
)
out = os.environ.get("GITHUB_OUTPUT")
if out:
    with open(out, "a", encoding="utf-8") as fh:
        fh.write(lines)
print(f"IST {now.strftime('%Y-%m-%d %H:%M')} | morning={morning} afternoon={afternoon}")
print(lines, end="")
