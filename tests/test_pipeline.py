from pathlib import Path
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from run_analysis import split_stacked_source, clean_orders, build_summaries  # noqa: E402


def write_stacked_fixture(path: Path) -> None:
    columns = [
        "Row ID", "Order ID", "Order Date", "Ship Date", "Ship Mode", "Customer ID",
        "Customer Name", "Segment", "Country", "City", "State", "Postal Code", "Region",
        "Product ID", "Category", "Sub-Category", "Product Name", "Sales", "Quantity",
        "Discount", "Profit",
    ]
    rows = [
        columns,
        ["1", "ORD-1", "1/2/2020", "1/4/2020", "Standard", "C1", "Alex", "Consumer", "US", "A", "CA", "90001", "West", "P1", "Tech", "Phones", "Phone", "100", "1", "0", "20"],
        ["2", "ORD-1", "1/2/2020", "1/4/2020", "Standard", "C1", "Alex", "Consumer", "US", "A", "CA", "90001", "West", "P2", "Tech", "Accessories", "Case", "50", "1", "0", "5"],
        ["3", "ORD-2", "2/5/2020", "2/8/2020", "Second", "C2", "Sam", "Corporate", "US", "B", "NY", "10001", "East", "P3", "Furniture", "Tables", "Desk", "200", "1", "0.5", "-10"],
        ["Person", "Region"],
        ["Manager West", "West"],
        ["Manager East", "East"],
        ["Returned", "Order ID"],
        ["Yes", "ORD-1"],
        ["Yes", "ORD-1"],
    ]
    import csv
    with path.open("w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)


def test_split_clean_and_order_level_returns(tmp_path: Path) -> None:
    source = tmp_path / "source.csv"
    write_stacked_fixture(source)
    orders, people, returns = split_stacked_source(source)
    assert len(orders) == 3
    assert len(people) == 2
    assert len(returns) == 1

    clean, quality = clean_orders(orders, returns)
    assert len(clean) == 3
    assert clean["Order Date"].notna().all()
    assert clean["Is Returned"].sum() == 2  # two lines belong to one returned order
    assert clean.loc[clean["Order ID"] == "ORD-1", "Is Returned"].all()
    assert quality["distinct_returned_orders"] == 1

    summaries = build_summaries(clean)
    returned_orders = int(summaries["monthly"]["Returned_Orders"].sum())
    distinct_orders = int(summaries["monthly"]["Orders"].sum())
    assert returned_orders == 1
    assert distinct_orders == 2
    assert abs(returned_orders / distinct_orders - 0.5) < 1e-9
    assert "profit_pivot_subcategory_region" in summaries
    assert "sales_pivot_category_region" in summaries
