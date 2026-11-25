"""Clean Sample Superstore data, calculate summaries, and create chart/report outputs."""
from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = PROJECT_ROOT / "data" / "raw" / "raw_superstore.csv"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
TABLE_DIR = PROJECT_ROOT / "outputs" / "tables"
CHART_DIR = PROJECT_ROOT / "outputs" / "charts"
REPORT_DIR = PROJECT_ROOT / "reports"

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
LOGGER = logging.getLogger("superstore_analysis")

ORDER_COLUMNS = [
    "Row ID", "Order ID", "Order Date", "Ship Date", "Ship Mode", "Customer ID",
    "Customer Name", "Segment", "Country", "City", "State", "Postal Code", "Region",
    "Product ID", "Category", "Sub-Category", "Product Name", "Sales", "Quantity",
    "Discount", "Profit",
]
NUMERIC_COLUMNS = ["Sales", "Quantity", "Discount", "Profit"]
DATE_COLUMNS = ["Order Date", "Ship Date"]
CATEGORICAL_COLUMNS = [
    "Order ID", "Ship Mode", "Customer ID", "Customer Name", "Segment", "Country",
    "City", "State", "Region", "Product ID", "Category", "Sub-Category", "Product Name",
]


def split_stacked_source(path: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Split the source CSV's Orders, People and Returns blocks.

    The file uses the Orders header at the top. People and Returns are appended
    below Orders with their own two-column headers, so they are identified by
    the values in the first column rather than treated as malformed order rows.
    """
    if not path.exists():
        raise FileNotFoundError(
            f"Dataset not found: {path}\nRun: python scripts/download_data.py"
        )

    raw = pd.read_csv(path, dtype=str, encoding="latin-1", keep_default_na=False,
                      na_values=[""], low_memory=False)
    missing = set(ORDER_COLUMNS) - set(raw.columns)
    if missing:
        raise ValueError(f"Source data is missing expected columns: {sorted(missing)}")

    row_id = raw["Row ID"].astype(str).str.strip()
    numeric_row = pd.to_numeric(row_id, errors="coerce").notna()
    orders = raw.loc[numeric_row, ORDER_COLUMNS].copy()

    person_header = raw.index[row_id.eq("Person")]
    returns_header = raw.index[row_id.eq("Returned")]
    if len(person_header) and len(returns_header):
        people_mask = (raw.index > person_header[0]) & (raw.index < returns_header[0])
    else:
        people_mask = pd.Series(False, index=raw.index)
    people_mask = people_mask & raw["Row ID"].notna() & raw["Order ID"].notna()
    people_rows = raw.loc[people_mask, ["Row ID", "Order ID"]].copy()
    people_rows.columns = ["Regional Manager", "Region"]
    people = people_rows.reset_index(drop=True)

    returns_mask = row_id.str.casefold().eq("yes")
    if len(returns_header):
        returns_mask = returns_mask & (raw.index > returns_header[0])
    returns = raw.loc[returns_mask, ["Order ID"]].copy()
    returns["Order ID"] = returns["Order ID"].astype(str).str.strip()
    returns = returns[returns["Order ID"].ne("")].drop_duplicates().reset_index(drop=True)

    if orders.empty:
        raise ValueError("No order records were found in the source CSV.")
    if returns.empty:
        LOGGER.warning("No return rows were detected; return metrics will be zero.")
    return orders.reset_index(drop=True), people.reset_index(drop=True), returns


def clean_orders(orders: pd.DataFrame, returns: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Standardise data types, handle missing values and attach return flags."""
    df = orders.copy()
    initial_rows = len(df)
    df.columns = [c.strip() for c in df.columns]

    # Remove exact duplicates first, then duplicate Row IDs (the line-item key).
    exact_duplicates = int(df.duplicated().sum())
    df = df.drop_duplicates()
    duplicate_row_ids = int(df["Row ID"].duplicated().sum())
    df = df.drop_duplicates(subset=["Row ID"], keep="first")

    df["Row ID"] = pd.to_numeric(df["Row ID"], errors="coerce")
    for col in DATE_COLUMNS:
        df[col] = pd.to_datetime(df[col], errors="coerce", format="mixed")
    for col in NUMERIC_COLUMNS:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    invalid_order_dates = int(df["Order Date"].isna().sum())
    invalid_ship_dates = int(df["Ship Date"].isna().sum())
    ship_before_order = int((df["Ship Date"] < df["Order Date"]).fillna(False).sum())
    before_critical_drop = len(df)
    df = df.dropna(subset=["Row ID", "Order ID", "Order Date", "Sales", "Profit"])
    dropped_critical = before_critical_drop - len(df)

    # Impute non-financial numeric fields with their observed median; never impute Sales/Profit.
    numeric_imputation: dict[str, dict[str, float | int]] = {}
    for col in ["Quantity", "Discount"]:
        missing_count = int(df[col].isna().sum())
        if missing_count and df[col].notna().any():
            median_value = float(df[col].median())
            df[col] = df[col].fillna(median_value)
            numeric_imputation[col] = {"count": missing_count, "median": median_value}

    # Keep unknown categorical values explicit; never turn missing financial data into zero.
    for col in CATEGORICAL_COLUMNS:
        if col in df.columns:
            df[col] = df[col].fillna("Unknown").astype(str).str.strip()
            df.loc[df[col].eq(""), col] = "Unknown"
    if "Postal Code" in df.columns:
        df["Postal Code"] = df["Postal Code"].fillna("Unknown").astype(str).str.strip()
        df.loc[df["Postal Code"].eq(""), "Postal Code"] = "Unknown"

    # Return IDs are order-level, so make the join many-to-one and avoid row multiplication.
    returned_ids = set(returns["Order ID"].dropna().astype(str).str.strip())
    df["Is Returned"] = df["Order ID"].isin(returned_ids)
    df["Order Month"] = df["Order Date"].dt.to_period("M").dt.to_timestamp()
    df["Order Year"] = df["Order Date"].dt.year.astype("int64")
    df["Month Name"] = df["Order Date"].dt.strftime("%b")
    df["Days to Ship"] = (df["Ship Date"] - df["Order Date"]).dt.days
    df["Profit Margin"] = np.where(df["Sales"].ne(0), df["Profit"] / df["Sales"], np.nan)
    df["Is Loss Making"] = df["Profit"].lt(0)

    # Referential integrity audit: any returned order not present in Orders is flagged.
    unmatched_return_ids = sorted(returned_ids - set(df["Order ID"].astype(str)))
    quality = {
        "input_order_rows": int(initial_rows),
        "exact_duplicate_rows_removed": exact_duplicates,
        "duplicate_row_ids_removed": duplicate_row_ids,
        "invalid_order_dates": invalid_order_dates,
        "invalid_ship_dates": invalid_ship_dates,
        "ship_before_order_rows": ship_before_order,
        "rows_dropped_for_missing_critical_fields": int(dropped_critical),
        "numeric_median_imputations": numeric_imputation,
        "clean_order_line_rows": int(len(df)),
        "distinct_orders": int(df["Order ID"].nunique()),
        "distinct_returned_orders": int(df.loc[df["Is Returned"], "Order ID"].nunique()),
        "unmatched_return_order_ids": unmatched_return_ids,
        "missing_values_after_cleaning": {
            str(k): int(v) for k, v in df.isna().sum().items() if int(v) > 0
        },
    }
    return df, quality


def build_summaries(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    monthly = (
        df.groupby("Order Month", as_index=False)
        .agg(Sales=("Sales", "sum"), Profit=("Profit", "sum"),
             Order_Lines=("Row ID", "count"), Orders=("Order ID", "nunique"),
             Returned_Orders=("Order ID", lambda x: x[df.loc[x.index, "Is Returned"]].nunique()))
        .sort_values("Order Month")
    )
    # Make the monthly time series continuous, including any months with zero recorded orders.
    full_months = pd.date_range(monthly["Order Month"].min(), monthly["Order Month"].max(), freq="MS")
    monthly = monthly.set_index("Order Month").reindex(full_months).rename_axis("Order Month").reset_index()
    for col in ["Sales", "Profit", "Order_Lines", "Orders", "Returned_Orders"]:
        monthly[col] = monthly[col].fillna(0)
    monthly["Return Rate"] = np.where(monthly["Orders"].gt(0),
                                      monthly["Returned_Orders"] / monthly["Orders"], 0)

    region = (
        df.groupby("Region", as_index=False)
        .agg(Sales=("Sales", "sum"), Profit=("Profit", "sum"),
             Orders=("Order ID", "nunique"), Customers=("Customer ID", "nunique"),
             Returned_Orders=("Order ID", lambda x: x[df.loc[x.index, "Is Returned"]].nunique()))
    )
    region["Profit Margin"] = region["Profit"] / region["Sales"]
    region["Return Rate"] = region["Returned_Orders"] / region["Orders"]
    region = region.sort_values("Sales", ascending=False)

    category = (
        df.groupby("Category", as_index=False)
        .agg(Sales=("Sales", "sum"), Profit=("Profit", "sum"),
             Quantity=("Quantity", "sum"), Orders=("Order ID", "nunique"))
    )
    category["Profit Margin"] = category["Profit"] / category["Sales"]
    category = category.sort_values("Profit", ascending=True)

    subcategory = (
        df.groupby(["Category", "Sub-Category"], as_index=False)
        .agg(Sales=("Sales", "sum"), Profit=("Profit", "sum"),
             Quantity=("Quantity", "sum"), Orders=("Order ID", "nunique"))
        .sort_values("Profit")
    )
    subcategory["Profit Margin"] = subcategory["Profit"] / subcategory["Sales"]

    year = (
        df.groupby("Order Year", as_index=False)
        .agg(Sales=("Sales", "sum"), Profit=("Profit", "sum"),
             Orders=("Order ID", "nunique"))
        .sort_values("Order Year")
    )

    profit_by_subcategory_region = pd.pivot_table(
        df, index="Sub-Category", columns="Region", values="Profit",
        aggfunc="sum", fill_value=0
    ).reset_index()
    sales_by_category_region = pd.pivot_table(
        df, index="Category", columns="Region", values="Sales",
        aggfunc="sum", fill_value=0
    ).reset_index()
    month_year = df.assign(Month_Number=df["Order Date"].dt.month).pivot_table(
        index="Month_Number", columns="Order Year", values="Sales",
        aggfunc="sum", fill_value=0
    ).reset_index()

    return {
        "monthly": monthly, "region": region, "category": category,
        "subcategory": subcategory, "year": year,
        "profit_pivot_subcategory_region": profit_by_subcategory_region,
        "sales_pivot_category_region": sales_by_category_region,
        "sales_pivot_month_year": month_year,
    }


def save_charts(df: pd.DataFrame, summaries: dict[str, pd.DataFrame]) -> list[str]:
    CHART_DIR.mkdir(parents=True, exist_ok=True)
    sns.set_theme(style="whitegrid", context="notebook")
    created: list[str] = []

    monthly = summaries["monthly"]
    fig, ax = plt.subplots(figsize=(12, 5.8))
    sns.lineplot(data=monthly, x="Order Month", y="Sales", marker="o", linewidth=2.2,
                 label="Revenue", ax=ax)
    ax.set(title="Monthly Revenue Trend", xlabel="Order month", ylabel="Revenue (USD)")
    ax.tick_params(axis="x", rotation=45)
    ax.yaxis.set_major_formatter(lambda x, pos: f"${x:,.0f}")
    ax.legend(frameon=False)
    fig.tight_layout()
    path = CHART_DIR / "01_monthly_revenue.png"
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig); created.append(path.name)

    fig, ax = plt.subplots(figsize=(12, 5.8))
    sns.lineplot(data=monthly, x="Order Month", y="Profit", marker="o", linewidth=2.2,
                 label="Profit", ax=ax)
    ax.axhline(0, linewidth=1, linestyle="--")
    ax.set(title="Monthly Profit Trend", xlabel="Order month", ylabel="Profit (USD)")
    ax.tick_params(axis="x", rotation=45)
    ax.yaxis.set_major_formatter(lambda x, pos: f"${x:,.0f}")
    fig.tight_layout()
    path = CHART_DIR / "02_monthly_profit.png"
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig); created.append(path.name)

    fig, ax = plt.subplots(figsize=(9, 5.5))
    cat = summaries["category"].sort_values("Sales", ascending=False)
    ax.bar(cat["Category"], cat["Sales"])
    ax.set(title="Revenue by Product Category", xlabel="Category", ylabel="Revenue (USD)")
    ax.yaxis.set_major_formatter(lambda x, pos: f"${x:,.0f}")
    fig.tight_layout()
    path = CHART_DIR / "03_revenue_by_category.png"
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig); created.append(path.name)

    fig, ax = plt.subplots(figsize=(9, 5.5))
    cat_profit = summaries["category"].sort_values("Profit")
    ax.bar(cat_profit["Category"], cat_profit["Profit"])
    ax.axhline(0, linewidth=1, linestyle="--")
    ax.set(title="Profit by Product Category", xlabel="Category", ylabel="Profit (USD)")
    ax.yaxis.set_major_formatter(lambda x, pos: f"${x:,.0f}")
    fig.tight_layout()
    path = CHART_DIR / "04_profit_by_category.png"
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig); created.append(path.name)

    fig, ax = plt.subplots(figsize=(9, 5.5))
    region = summaries["region"].sort_values("Region")
    positions = np.arange(len(region))
    width = 0.38
    ax.bar(positions - width / 2, region["Sales"], width, label="Sales")
    ax.bar(positions + width / 2, region["Profit"], width, label="Profit")
    ax.set_xticks(positions, region["Region"])
    ax.set(title="Regional Revenue and Profit", xlabel="Region", ylabel="USD")
    ax.yaxis.set_major_formatter(lambda x, pos: f"${x:,.0f}")
    ax.legend(title="", frameon=False)
    fig.tight_layout()
    path = CHART_DIR / "05_regional_performance.png"
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig); created.append(path.name)

    sub = summaries["subcategory"].sort_values("Profit")
    fig, ax = plt.subplots(figsize=(10, 8))
    ax.barh(sub["Sub-Category"], sub["Profit"])
    ax.axvline(0, linewidth=1, linestyle="--")
    ax.set(title="Profit by Sub-Category", xlabel="Profit (USD)", ylabel="Sub-category")
    ax.xaxis.set_major_formatter(lambda x, pos: f"${x:,.0f}")
    fig.tight_layout()
    path = CHART_DIR / "06_profit_by_subcategory.png"
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig); created.append(path.name)

    fig, ax = plt.subplots(figsize=(9, 5.5))
    reg = summaries["region"].sort_values("Return Rate", ascending=False)
    ax.bar(reg["Region"], reg["Return Rate"])
    ax.set(title="Returned-Order Rate by Region", xlabel="Region", ylabel="Returned orders / orders")
    ax.yaxis.set_major_formatter(lambda x, pos: f"{x:.0%}")
    fig.tight_layout()
    path = CHART_DIR / "07_return_rate_by_region.png"
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig); created.append(path.name)
    return created


def build_insights(df: pd.DataFrame, summaries: dict[str, pd.DataFrame], quality: dict[str, Any],
                   chart_files: list[str]) -> str:
    total_sales = float(df["Sales"].sum())
    total_profit = float(df["Profit"].sum())
    orders_n = int(df["Order ID"].nunique())
    returned_n = int(df.loc[df["Is Returned"], "Order ID"].nunique())
    return_rate = returned_n / orders_n if orders_n else 0
    margin = total_profit / total_sales if total_sales else 0

    monthly = summaries["monthly"]
    peak_sales = monthly.loc[monthly["Sales"].idxmax()]
    peak_profit = monthly.loc[monthly["Profit"].idxmax()]
    low_profit_month = monthly.loc[monthly["Profit"].idxmin()]
    best_cat = summaries["category"].sort_values("Profit", ascending=False).iloc[0]
    loss_categories = summaries["category"].query("Profit < 0")
    best_region = summaries["region"].sort_values("Profit", ascending=False).iloc[0]
    high_return_region = summaries["region"].sort_values("Return Rate", ascending=False).iloc[0]
    loss_sub = summaries["subcategory"].query("Profit < 0").sort_values("Profit")

    def money(value: float) -> str:
        return f"${value:,.2f}"

    lines = [
        "# E-commerce Sales Performance — Analysis Findings",
        "",
        "> This report is generated from the local source file when `python scripts/run_analysis.py` is run. Values are not hard-coded.",
        "",
        "## Executive summary",
        "",
        f"- **Revenue:** {money(total_sales)}",
        f"- **Profit:** {money(total_profit)}",
        f"- **Profit margin:** {margin:.1%}",
        f"- **Distinct orders:** {orders_n:,}",
        f"- **Returned orders:** {returned_n:,} ({return_rate:.1%} of distinct orders)",
        "",
        "## Key findings",
        "",
        f"1. **Monthly revenue peak:** {peak_sales['Order Month']:%B %Y} at {money(float(peak_sales['Sales']))}.",
        f"2. **Monthly profit peak:** {peak_profit['Order Month']:%B %Y} at {money(float(peak_profit['Profit']))}; the lowest-profit month was {low_profit_month['Order Month']:%B %Y} ({money(float(low_profit_month['Profit']))}).",
        f"3. **Category leader:** {best_cat['Category']} generated the highest category profit at {money(float(best_cat['Profit']))} ({float(best_cat['Profit Margin']):.1%} margin).",
        f"4. **Regional leader:** {best_region['Region']} led profit with {money(float(best_region['Profit']))}; highest returned-order rate was in {high_return_region['Region']} at {float(high_return_region['Return Rate']):.1%}.",
    ]
    if len(loss_categories):
        labels = ", ".join(f"{r.Category} ({money(float(r.Profit))})" for r in loss_categories.itertuples())
        lines.append(f"5. **Loss-making categories:** {labels}.")
    else:
        lines.append("5. **Loss-making categories:** none at the category total level; sub-category analysis may still show loss-making pockets.")
    if len(loss_sub):
        top_losses = "; ".join(
            f"{row['Sub-Category']} ({money(float(row['Profit']))})"
            for _, row in loss_sub.head(5).iterrows()
        )
        lines.append(f"6. **Sub-categories with the largest losses:** {top_losses}.")
    else:
        lines.append("6. **Loss-making sub-categories:** none in this data slice.")

    lines += [
        "",
        "## Interpretation and recommended actions",
        "",
        "- Investigate negative-profit sub-categories before changing the overall category strategy; a profitable category can contain loss-making product groups.",
        "- Review the discounting, fulfilment and product-mix drivers in the region with the highest return rate.",
        "- Use the monthly revenue and profit lines together: revenue peaks do not necessarily coincide with profit peaks.",
        "- Treat return rate as an order-level metric. A returned order can contain multiple product lines, so the numerator and denominator use distinct `Order ID` values.",
        "",
        "## Data quality checks",
        "",
        f"- Input order rows: {quality['input_order_rows']:,}",
        f"- Exact duplicate rows removed: {quality['exact_duplicate_rows_removed']:,}",
        f"- Duplicate Row IDs removed: {quality['duplicate_row_ids_removed']:,}",
        f"- Invalid order dates: {quality['invalid_order_dates']:,}",
        f"- Invalid ship dates: {quality['invalid_ship_dates']:,}",
        f"- Ship dates earlier than order dates: {quality['ship_before_order_rows']:,}",
        f"- Rows dropped for missing critical fields: {quality['rows_dropped_for_missing_critical_fields']:,}",
        f"- Unmatched return Order IDs: {len(quality['unmatched_return_order_ids']):,}",
        "",
        "## Charts",
        "",
    ]
    lines.extend(f"![{name.replace('_', ' ').replace('.png', '')}](../outputs/charts/{name})" for name in chart_files)
    lines += [
        "",
        "## Caveats",
        "",
        "- The Sample Superstore data is an educational sample for a fictional retailer, not a live company's financial statements.",
        "- `Sales` is treated as revenue proxy and `Profit` as the dataset's profit field. The analysis does not estimate taxes, shipping costs, refunds or other costs not present in the source.",
        "- Returned orders are flagged at order level. This analysis does not subtract a refund amount from sales or profit because the source does not provide refund value.",
        "",
    ]
    return "\n".join(lines)


def run(input_path: Path = DEFAULT_INPUT) -> dict[str, Any]:
    for folder in (PROCESSED_DIR, TABLE_DIR, CHART_DIR, REPORT_DIR):
        folder.mkdir(parents=True, exist_ok=True)

    orders, people, returns = split_stacked_source(input_path)
    LOGGER.info("Loaded %s order lines, %s manager rows, %s distinct returned orders",
                f"{len(orders):,}", f"{len(people):,}", f"{len(returns):,}")
    clean, quality = clean_orders(orders, returns)
    if clean.empty:
        raise ValueError("No valid order rows remain after cleaning; check the source data.")
    summaries = build_summaries(clean)

    clean.to_csv(PROCESSED_DIR / "superstore_clean.csv", index=False)
    people.to_csv(PROCESSED_DIR / "regional_managers.csv", index=False)
    returns.to_csv(PROCESSED_DIR / "returned_orders.csv", index=False)
    with (REPORT_DIR / "data_quality.json").open("w", encoding="utf-8") as f:
        json.dump(quality, f, indent=2, default=str)

    for name, frame in summaries.items():
        frame.to_csv(TABLE_DIR / f"{name}_summary.csv", index=False)
    charts = save_charts(clean, summaries)
    report = build_insights(clean, summaries, quality, charts)
    (REPORT_DIR / "insights.md").write_text(report, encoding="utf-8")

    LOGGER.info("Analysis complete. Outputs written to %s", PROJECT_ROOT)
    LOGGER.info("Revenue: $%s | Profit: $%s | Orders: %s",
                f"{clean['Sales'].sum():,.2f}", f"{clean['Profit'].sum():,.2f}",
                f"{clean['Order ID'].nunique():,}")
    return {"clean": clean, "quality": quality, "summaries": summaries, "charts": charts}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT,
                        help="Path to the stacked Sample Superstore CSV")
    args = parser.parse_args()
    run(args.input)
