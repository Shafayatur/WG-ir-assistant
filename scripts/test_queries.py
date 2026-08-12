"""
Exercises every function in src/queries.py once and prints the result,
so we can eyeball correctness before wiring these into the chatbot or
dashboard UI.

Run from the project root:
    python -m scripts.test_queries
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src import queries

print("=" * 60); print("get_latest_cf_day()"); print("=" * 60)
print(queries.get_latest_cf_day())

print("\n" + "=" * 60); print("get_cf_summary()"); print("=" * 60)
print(queries.get_cf_summary())

print("\n" + "=" * 60); print("compare_cf_periods(period='month', n_periods=6)"); print("=" * 60)
print(queries.compare_cf_periods(period="month", n_periods=6))

print("\n" + "=" * 60); print("filter_orders(stage='active', limit=5)"); print("=" * 60)
print(queries.filter_orders(stage="active", limit=5))

print("\n" + "=" * 60); print("get_order_summary(stage='closed')"); print("=" * 60)
print(queries.get_order_summary(stage="closed"))

print("\n" + "=" * 60); print("top_investors(n=5)"); print("=" * 60)
print(queries.top_investors(n=5))

print("\n" + "=" * 60); print("compare_order_periods(period='month', n_periods=6)"); print("=" * 60)
print(queries.compare_order_periods(period="month", n_periods=6))

print("\n" + "=" * 60); print("list_projects(limit=10)"); print("=" * 60)
print(queries.list_projects(limit=10))