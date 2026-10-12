# finlib - Personal Finance Transaction Library

A Python library to search transactions across personal finance statements (HDFC, SBI, IDFC First Bank, Loan Repayment Schedules, and AIS) without any hardcoded paths, and generate formatted PDF reports with original statement page screenshots attached.

---

## 📦 Prerequisites

```bash
pip install fpdf2 pymupdf
```

Requires `pdftotext` (available on macOS via `brew install poppler`).

---

## 🔍 How File Discovery Works (No Hardcoded Paths)

`finlib` removes all hardcoded file and directory locations:

1. **Auto-Discovered Directory**: Defaults to the current working directory, or searches recursively under `FINANCE_DIR` environment variable, or `~/Finance`. You can also supply `-d /path/to/Finance` or pass `base_dir` in Python.
2. **Auto-Discovered Statements**: Recursively scans all `.pdf` files in the folder and automatically detects their bank and document type using name and content signatures.
3. **Auto-Discovered Passwords**: Walks directory trees to find nearby `password.txt` files for password-protected statements.

---

## 🏦 Supported Financial Statements

| Statement Type | Categories / Folders | Parser | Description |
|---|---|---|---|
| **HDFC Bank** | Savings Account (`HDFC/Personal Account`) | `hdfc` | Parses debit/credit, UPI, ref nos, balances |
| **State Bank of India (SBI)** | Savings Account (`SBI/Personal Account`) | `sbi` | Multi-line UPI transaction blocks, balances |
| **IDFC First Bank** | Savings Account (`IDFC/Personal Account`) | `idfc` | Monthly statements, credits, debits |
| **IDFC First Bank** | Credit Card (`IDFC/Credit Card`) | `idfc` | Credit card transactions and charges |
| **Loan Schedules** | Personal Loans (`Loan/`) | `loan` | Installment dates, EMI amounts, interest & principal |
| **Income Tax AIS** | Tax Information (`AIS/`) | `ais` | Salary TDS, dividend, and tax payment entries (optional via `--include-ais`) |

---

## 🚀 Usage

### 1. Command Line Interface (CLI)

```bash
# Search across all discovered statements for specific dates
python3 -m finlib 12/07/2024 31/01/2025

# Specify a custom statements root directory
python3 -m finlib 12/07/2024 -d /path/to/my/statements

# Exclude salary or specific keywords
python3 -m finlib 12/07/2024 31/01/2025 --exclude AFFINSYS

# Search only specific banks/sources (e.g., HDFC, Loan, SBI, IDFC)
python3 -m finlib 07/04/2025 --banks HDFC Loan

# Include Annual Information Statement (AIS) entries
python3 -m finlib 31/01/2025 --include-ais

# Print results only without writing a PDF
python3 -m finlib 12/07/2024 --print-only

# Generate PDF to a custom output path without attaching original screenshots
python3 -m finlib 12/07/2024 -o report.pdf --no-screenshots
```

### 2. Python API

```python
from finlib import TransactionFinder, ReportGenerator

# 1. Initialize finder (auto-discovers directory and statements)
finder = TransactionFinder(base_dir="/Users/barathrajdevarajan/Finance")

# Or let it detect automatically:
# finder = TransactionFinder()

# 2. Search for any dates (supports dd/mm/yyyy, dd.mm.yyyy, yyyy-mm-dd)
result = finder.search(["12/07/2024", "31/01/2025"], exclude=["AFFINSYS"])

# 3. View transactions
for txn in result.transactions:
    print(f"{txn.date} | {txn.bank} | {txn.txn_type.upper()} | Rs.{txn.amount:,.2f} | {txn.description}")

# 4. Filter or check totals
print(f"Total Debits:  Rs.{result.total_debits:,.2f}")
print(f"Total Credits: Rs.{result.total_credits:,.2f}")

# 5. Generate formatted PDF with attached screenshots of original statement pages
reporter = ReportGenerator()
reporter.generate(result, "Transactions_Report.pdf", attach_screenshots=True)
```

---

## 📁 Project Structure

```
finlib/
├── __init__.py      # Package exports (Transaction, SearchResult, TransactionFinder, ReportGenerator)
├── __main__.py      # Command line runner
├── models.py        # Data structures with totals and filtering
├── parsers.py       # Bank & document parsers (HDFC, SBI, IDFC, Loan, AIS)
├── finder.py        # Dynamic statement & password discovery engine
├── report.py        # PDF generator with statement screenshots
└── README.md        # Documentation
```
