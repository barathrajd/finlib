#!/usr/bin/env python3
"""Command-line interface for finlib.

Usage:
    python -m finlib 12/07/2024 31/01/2025
    python -m finlib 12.07.2024 --exclude AFFINSYS
    python -m finlib 31/01/2025 --banks HDFC SBI --no-screenshots
    python -m finlib 12/07/2024 31/01/2025 -o report.pdf
    python -m finlib 15/03/2024 --dir /path/to/Finance --print-only
"""

import argparse
import sys
from pathlib import Path

from finlib.finder import TransactionFinder
from finlib.report import ReportGenerator


def main():
    parser = argparse.ArgumentParser(
        prog="finlib",
        description="Search bank transactions across statements and generate PDF reports.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m finlib 12/07/2024 31/01/2025
  python -m finlib 12.07.2024 --exclude AFFINSYS
  python -m finlib 31/01/2025 --banks HDFC SBI
  python -m finlib 12/07/2024 --dir /path/to/Finance
  python -m finlib 12/07/2024 --print-only
  python -m finlib 12/07/2024 --include-ais
""",
    )
    parser.add_argument(
        "dates",
        nargs="+",
        help="Transaction dates to search (dd/mm/yyyy or dd.mm.yyyy)",
    )
    parser.add_argument(
        "-d", "--dir",
        default=None,
        help="Base directory containing statement PDFs (default: current directory or ~/Finance)",
    )
    parser.add_argument(
        "-o", "--output",
        default=None,
        help="Output PDF path (default: Transactions_<dates>.pdf in statement directory)",
    )
    parser.add_argument(
        "--exclude",
        nargs="+",
        default=None,
        help="Keywords to exclude from results (e.g., AFFINSYS)",
    )
    parser.add_argument(
        "--banks",
        nargs="+",
        default=None,
        help="Only search specific banks or types (e.g., HDFC, SBI, IDFC, Loan)",
    )
    parser.add_argument(
        "--include-ais",
        action="store_true",
        help="Include Income Tax AIS entries in search",
    )
    parser.add_argument(
        "--no-screenshots",
        action="store_true",
        help="Don't attach original statement screenshots",
    )
    parser.add_argument(
        "--print-only",
        action="store_true",
        help="Only print transactions to console, don't generate PDF",
    )

    args = parser.parse_args()

    finder = TransactionFinder(base_dir=args.dir)
    print(f"\nStatement Directory: {finder.base_dir}")
    print(f"Searching dates:     {', '.join(args.dates)}")
    if args.exclude:
        print(f"Excluding keywords:  {', '.join(args.exclude)}")
    if args.banks:
        print(f"Filtering banks:     {', '.join(args.banks)}")
    if args.include_ais:
        print(f"Including AIS:       Yes")
    print()

    # Discover and report statements found
    stmts = finder.discover_statements(banks=args.banks)
    print(f"Discovered {len(stmts)} statement file(s) across folders.")
    print()

    result = finder.search(
        dates=args.dates,
        exclude=args.exclude,
        banks=args.banks,
        include_ais=args.include_ais,
    )

    for query_date in sorted(result.query_dates):
        txns = result.for_date(query_date)
        date_str = query_date.strftime("%d %B %Y")
        print(f"=== {date_str} ===")

        if not txns:
            print("  No transactions found.")
            print()
            continue

        total_debit = 0.0
        total_credit = 0.0

        for i, t in enumerate(txns, 1):
            type_icon = "[-]" if t.txn_type == "debit" else "[+]"
            print(f"  {i}. {type_icon} Rs.{t.amount_display:>12}  {t.bank:<16} {t.description[:55]}")
            if t.txn_type == "debit":
                total_debit += t.amount
            else:
                total_credit += t.amount

        print(f"  {'---':->80}")
        if total_debit:
            print(f"  Total Debits:  Rs.{total_debit:>12,.2f}")
        if total_credit:
            print(f"  Total Credits: Rs.{total_credit:>12,.2f}")
        print()

    if result.errors:
        print("Warnings/Notes:")
        for err in result.errors:
            print(f"  ! {err}")
        print()

    if result.source_pages:
        print(f"Found {len(result.source_pages)} matching page(s) in original statements.")

    if args.print_only:
        print("Done (print-only mode).")
        return

    if not result.transactions and not result.source_pages:
        print("No transactions found. Skipping PDF generation.")
        return

    if args.output:
        output_path = args.output
    else:
        date_parts = []
        for d in sorted(result.query_dates):
            date_parts.append(d.strftime("%d%b%Y"))
        filename = f"Transactions_{'_'.join(date_parts)}.pdf"
        output_path = str(finder.base_dir / filename)

    report = ReportGenerator()
    report.generate(
        result,
        output_path,
        attach_screenshots=not args.no_screenshots,
    )
    print(f"\nPDF report saved to: {output_path}")


if __name__ == "__main__":
    main()
