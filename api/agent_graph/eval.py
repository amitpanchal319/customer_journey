# api/agent_graph/eval.py
# ----------------------------------------------------------------
# Lightweight evaluation harness for the agent. Run:
#   python -m api.agent_graph.eval
# Extend GOLDEN with more cases. Wire into CI to catch regressions.
# ----------------------------------------------------------------

import sys
from .graph import run_agent

# Each case: question, optional store scope, and lightweight checks.
GOLDEN = [
    {"q": "How many total customers do we have?",                      "store": None,
     "expect_tables": ["cust_master_profile"]},
    {"q": "Top 5 EBO stores by total customers",                       "store": None,
     "expect_tables": ["cust_ebo_salescombo_view", "store_summary_mv"]},
    {"q": "Top categories at Lajpat Nagar Delhi by revenue",           "store": "Lajpat Nagar Delhi",
     "expect_tables": ["item_master"], "expect_store": "Lajpat Nagar Delhi"},
    {"q": "How many High churn-risk customers are there?",             "store": None,
     "expect_sql_contains": ["churn_risk"]},
    {"q": "Which sizes sell most at Rajouri Mall Delhi?",              "store": "Rajouri Mall Delhi",
     "expect_store": "Rajouri Mall Delhi"},
]


def _check(case, r):
    fails = []
    if r.get("status") != "success":
        return [f"status={r.get('status')} error={r.get('error')}"]
    if not (r.get("answer") or "").strip():
        fails.append("empty answer")
    sql = (r.get("sql") or "").lower()
    for t in case.get("expect_tables", []):
        # at least one expected table should appear (loose check)
        pass
    if case.get("expect_tables") and not any(t.lower() in sql for t in case["expect_tables"]):
        fails.append(f"none of expected tables {case['expect_tables']} in SQL")
    for s in case.get("expect_sql_contains", []):
        if s.lower() not in sql:
            fails.append(f"SQL missing '{s}'")
    if case.get("expect_store") and case["expect_store"].lower() not in sql:
        fails.append(f"store '{case['expect_store']}' not enforced in SQL")
    return fails


def main():
    passed = 0
    for i, case in enumerate(GOLDEN, 1):
        r = run_agent(case["q"], case.get("store"), [])
        fails = _check(case, r)
        status = "PASS" if not fails else "FAIL"
        if not fails:
            passed += 1
        print(f"[{status}] {i}. {case['q']}  ({r.get('elapsed_s')}s, tools={r.get('tools_used')})")
        for f in fails:
            print(f"        - {f}")
    print(f"\n{passed}/{len(GOLDEN)} passed")
    sys.exit(0 if passed == len(GOLDEN) else 1)


if __name__ == "__main__":
    main()
