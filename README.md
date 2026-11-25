# E-commerce / Retail Sales Performance Dashboard

An end-to-end retail analytics project built with **Python, Pandas, GroupBy, pivot tables, Matplotlib and Seaborn**. It cleans the classic Sample Superstore data, analyses revenue, profit and returned orders, and exports reproducible summary tables, charts and written insights.

> **Dataset note:** Sample Superstore is an educational dataset for a fictional US retailer. The project uses its order-line data and the accompanying appended `People` and `Returns` sections. It is not a live company's financial data.

## Project questions

1. How do revenue and profit change month by month and year by year?
2. Which product categories and sub-categories contribute profit or generate losses?
3. Which regions lead sales, profit and returned-order rate?
4. Which months have the highest revenue and highest profit?
5. How many distinct orders are returned, and how does return rate vary by region?

## What this project does

- Splits the source CSV into `Orders`, `People` and `Returns` sections.
- Cleans duplicate order-line IDs, parses order/ship dates, coerces numeric fields, and handles missing categorical values explicitly.
- Does **not** fill missing Sales or Profit with zero. Rows missing critical financial/date identifiers are excluded and counted in the quality report.
- Joins returned order IDs to order lines without multiplying rows.
- Calculates return rate at the **distinct order** level, not at the product-line level.
- Uses Pandas `groupby()` and pivot-style summaries for month, year, region, category and sub-category.
- Produces charts with Matplotlib and Seaborn and writes a findings report from the current data.

## Repository structure

```text
 e-commerce-sales-performance-dashboard/
 ├── data/
 │   ├── raw/                 # downloaded source file (not committed)
 │   └── processed/           # cleaned data and split reference tables
 ├── notebooks/
 │   └── 01_sales_performance_analysis.ipynb
 ├── outputs/
 │   ├── charts/              # PNG visualisations
 │   └── tables/              # monthly, regional, category summaries
 ├── reports/
 │   ├── insights.md          # generated narrative findings
 │   └── data_quality.json    # generated quality checks
 ├── scripts/
 │   ├── download_data.py
 │   └── run_analysis.py
 ├── tests/
 │   └── test_pipeline.py
 ├── requirements.txt
 └── README.md
```

## Dataset source and attribution

The source is the public [Sample Superstore raw CSV](https://raw.githubusercontent.com/thummam/superstore-sales-dashboard/main/data/raw_superstore.csv), made available in the [thummam/superstore-sales-dashboard repository](https://github.com/thummam/superstore-sales-dashboard). The upstream repository documents the file as the Tableau Sample Superstore data, with the `Orders` block followed by `People` and `Returns` blocks. The project downloads the raw stacked file so that the split-and-clean process remains part of the analysis.

The raw dataset is deliberately not committed to this repository. Confirm the dataset's redistribution terms before publishing the raw file yourself; the download script obtains it from the public source at runtime.

## Run locally (Windows / macOS / Linux)

### 1. Install Python

Use Python 3.10 or newer. In a terminal, move into the project folder:

```bash
cd ecommerce_sales_performance_dashboard
```

### 2. Create and activate a virtual environment

**Windows PowerShell**

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**macOS / Linux**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Download the dataset

```bash
python scripts/download_data.py
```

This creates `data/raw/raw_superstore.csv`. To use another copy of the same stacked source file, place it there or pass a path to the analysis command.

### 5. Run the complete analysis

```bash
python scripts/run_analysis.py
```

To point to a file in another location:

```bash
python scripts/run_analysis.py --input "C:/path/to/raw_superstore.csv"
```

### 6. Review the results

After the pipeline finishes, open:

- `reports/insights.md` — written findings and recommended follow-ups.
- `reports/data_quality.json` — duplicate, date, missing-value and join checks.
- `outputs/charts/` — monthly revenue, monthly profit, category, regional, sub-category and return-rate charts.
- `outputs/tables/` — monthly, yearly, regional, category and sub-category summaries.
- `data/processed/superstore_clean.csv` — clean order-line data with date features and return flags.

### 7. Open the Jupyter notebook (optional)

```bash
jupyter notebook notebooks/01_sales_performance_analysis.ipynb
```

Run the cells from top to bottom after downloading the dataset and running the pipeline once.

## Key metric definitions

| Metric | Definition |
|---|---|
| Revenue | Sum of `Sales` at order-line grain |
| Profit | Sum of the source `Profit` field |
| Profit margin | Total Profit / Total Sales |
| Orders | Distinct `Order ID` count |
| Returned orders | Distinct `Order ID` count where `Is Returned` is true |
| Return rate | Returned orders / distinct orders |

**Important:** a returned order may contain multiple product lines. Therefore, `Is Returned` is joined to each matching order line for analysis, but the return-rate numerator and denominator both use distinct order IDs. The project flags returned orders; it does not estimate the refund amount because the source does not provide return-value data.

## Data quality approach

- **Duplicates:** remove exact duplicate rows and duplicate `Row ID` values, retaining the first occurrence.
- **Dates:** parse `Order Date` and `Ship Date`; invalid dates are counted and rows missing critical order date fields are excluded.
- **Numeric values:** coerce `Sales`, `Profit`, `Quantity` and `Discount` to numeric values. Missing Sales or Profit values are not silently replaced with zero.
- **Categoricals:** fill missing categorical labels with `Unknown` so the rows remain visible in grouped summaries.
- **Return join:** de-duplicate returned `Order ID` values before flagging order lines; unmatched return IDs are reported.
- **Auditability:** all key removals and quality counts are written to `reports/data_quality.json`.

## Tests

```bash
pytest -q
```

The tests use a tiny synthetic fixture to validate parsing, date conversion, return joins and order-level return-rate logic. The fixture is only for unit testing; it is not used as a substitute for the Superstore dataset.

## Upload this project to GitHub

### Option A — GitHub website (no Git commands)

1. Sign in to GitHub and click **New repository**.
2. Name it `ecommerce-sales-performance-dashboard`.
3. Choose **Public** or **Private**. Do not initialise it with another README, `.gitignore` or licence because this project already contains a README and `.gitignore`.
4. Create the repository.
5. On your computer, open the project folder and remove the `.venv` folder if it exists. Do not upload `.venv` or the downloaded raw CSV.
6. On the empty GitHub repository page, choose **Add file → Upload files**.
7. Drag the project files and folders into the upload area. Ensure `README.md`, `requirements.txt`, `scripts/`, `notebooks/`, `tests/`, `outputs/` and `reports/` are included. The raw dataset is excluded by `.gitignore`.
8. Add the commit message `Add retail sales performance analysis project` and click **Commit changes**.

### Option B — Git command line (recommended)

Create an empty repository on GitHub first, then run these commands from the project folder. Replace `YOUR-USERNAME` with your GitHub username:

```bash
git init
git add .
git status
git commit -m "Add retail sales performance analysis project"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/ecommerce-sales-performance-dashboard.git
git push -u origin main
```

Before `git commit`, inspect `git status`. The `.gitignore` should keep `.venv/`, the raw downloaded CSV, Python cache files and notebook checkpoints out of the commit.

### After uploading

- Open the repository page and confirm the README renders correctly.
- Check that no `.venv/` or raw data file was uploaded.
- Add a short repository description such as: `Retail sales and profitability analysis using Python, Pandas, GroupBy, pivot tables, Matplotlib and Seaborn.`
- Add topics such as `python`, `pandas`, `data-analysis`, `seaborn`, `matplotlib`, `retail-analytics` and `superstore`.

## Limitations

- The Superstore dataset is fictional and historical; results are an analytics exercise, not current market performance.
- Sales and Profit are used as supplied. This source does not provide a complete accounting bridge, product costs, refund values or a return reason.
- The regional and monthly results are descriptive and do not establish causation.

## License

No license is added for the upstream dataset. Add a code license only after deciding how you want others to reuse your project code, and verify the upstream data's own terms separately.
