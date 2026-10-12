"""Transaction finder - orchestrates auto-discovery and searching across financial statements."""

import os
import re
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from finlib.models import Transaction, SearchResult
from finlib.parsers import (
    HDFCParser,
    SBIParser,
    IDFCParser,
    LoanRepaymentParser,
    AISParser,
    PARSERS,
)


def _find_password_for_file(pdf_path: Path, base_dir: Path) -> Optional[str]:
    """Auto-discover password for a PDF file from nearby password.txt files.

    Checks:
    1. Same directory (e.g. dir/password.txt)
    2. Parent directory
    3. Any sibling directory if named after the bank (e.g. HDFC/*/password.txt)
    """
    # 1. Exact parent directory
    direct_pw = pdf_path.parent / "password.txt"
    if direct_pw.exists():
        return direct_pw.read_text().strip()

    # 2. Walk up to base_dir
    curr = pdf_path.parent
    while curr != base_dir and curr.parent != curr:
        curr = curr.parent
        candidate = curr / "password.txt"
        if candidate.exists():
            return candidate.read_text().strip()

    # 3. Check bank-level root directory (e.g. under HDFC/ or SBI/)
    rel_parts = pdf_path.relative_to(base_dir).parts
    if len(rel_parts) > 1:
        bank_root = base_dir / rel_parts[0]
        # Search for any password.txt inside the bank folder
        for candidate in bank_root.rglob("password.txt"):
            return candidate.read_text().strip()

    return None


def _classify_statement_file(pdf_path: Path) -> Optional[dict]:
    """Detect parser and metadata for a given PDF file based on path & name."""
    path_str = str(pdf_path)
    filename = pdf_path.name
    parent_dir = pdf_path.parent.name.lower()
    grandparent_dir = pdf_path.parent.parent.name.lower() if pdf_path.parent.parent else ""

    # Skip generated transaction reports
    if filename.startswith("Transactions_") or filename.startswith("report"):
        return None

    # HDFC
    if "hdfc" in path_str.lower():
        if "repayment" in filename.lower() or "loan" in parent_dir:
            return {"parser": "loan", "bank": "HDFC Loan", "type": "loan"}
        return {"parser": "hdfc", "bank": "HDFC Savings", "type": "savings"}

    # SBI
    if "sbi" in path_str.lower():
        if "ppf" in path_str.lower():
            # PPF statements can be scanned or standard
            return {"parser": "sbi", "bank": "SBI PPF", "type": "ppf"}
        return {"parser": "sbi", "bank": "SBI Savings", "type": "savings"}

    # IDFC
    if "idfc" in path_str.lower():
        if "credit card" in path_str.lower():
            return {"parser": "idfc", "bank": "IDFC Credit Card", "type": "credit_card"}
        if "emi" in path_str.lower():
            return None  # EMI conversion letters, not transaction lists
        return {"parser": "idfc", "bank": "IDFC Savings", "type": "savings"}

    # Loan Repayment Schedules
    if "loan" in path_str.lower() or "repayment schedule" in filename.lower():
        return {"parser": "loan", "bank": "Loan Schedule", "type": "loan"}

    # AIS (Annual Information Statement)
    if "ais" in path_str.lower():
        return {"parser": "ais", "bank": "Income Tax AIS", "type": "tax_record"}

    # TIS is summary-only (not itemized dates), skip for transaction search
    if "tis" in path_str.lower():
        return None

    return None


class TransactionFinder:
    """Search transactions dynamically across statement PDFs without hardcoded paths.

    Features:
    - Auto-discovers all statement PDFs in `base_dir` (default: current working directory or Finance folder).
    - Auto-detects passwords from directory hierarchy.
    - Classifies statement types automatically (HDFC, SBI, IDFC, Loans, AIS).
    - Can also accept custom file lists or explicit configurations.
    """

    def __init__(self, base_dir: Optional[str] = None, config: Optional[dict] = None):
        """Initialize TransactionFinder.

        Args:
            base_dir: Root directory containing finance statements.
                      Defaults to environment variable `FINANCE_DIR` or current working directory.
            config: Optional custom dictionary if explicit mapping is preferred.
        """
        if base_dir:
            self.base_dir = Path(base_dir).resolve()
        elif "FINANCE_DIR" in os.environ:
            self.base_dir = Path(os.environ["FINANCE_DIR"]).resolve()
        else:
            cwd = Path.cwd().resolve()
            # If current directory is within Finance, or contains bank folders
            if (cwd / "HDFC").exists() or (cwd / "SBI").exists() or cwd.name.lower() == "finance":
                self.base_dir = cwd
            else:
                self.base_dir = Path.home() / "Finance"

        self.config = config

    @staticmethod
    def parse_date(date_str: str) -> date:
        """Parse a date string in various formats."""
        for fmt in ("%d/%m/%Y", "%d.%m.%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y"):
            try:
                return datetime.strptime(date_str.strip(), fmt).date()
            except ValueError:
                continue
        raise ValueError(f"Cannot parse date: '{date_str}'. Use dd/mm/yyyy or dd.mm.yyyy format.")

    def discover_statements(self, banks: Optional[list[str]] = None) -> list[dict]:
        """Automatically find all supported PDF statements in base_dir."""
        discovered = []

        if not self.base_dir.exists():
            return discovered

        for pdf_file in sorted(self.base_dir.rglob("*.pdf")):
            meta = _classify_statement_file(pdf_file)
            if not meta:
                continue

            bank_name = meta["bank"]
            if banks:
                # Filter by requested banks
                matches_filter = any(
                    b.lower() in bank_name.lower() or b.lower() in meta["parser"].lower()
                    for b in banks
                )
                if not matches_filter:
                    continue

            password = _find_password_for_file(pdf_file, self.base_dir)

            discovered.append({
                "path": str(pdf_file),
                "filename": pdf_file.name,
                "parser": meta["parser"],
                "bank": bank_name,
                "account_type": meta["type"],
                "password": password,
            })

        return discovered

    def search(
        self,
        dates: list[str | date],
        exclude: Optional[list[str]] = None,
        banks: Optional[list[str]] = None,
        include_ais: bool = False,
    ) -> SearchResult:
        """Search for transactions on specified dates across all discovered statements.

        Args:
            dates: List of date strings or date objects.
            exclude: Optional list of keywords to exclude (e.g. ['AFFINSYS']).
            banks: Optional list of bank names to limit search.
            include_ais: Whether to include AIS tax records (default: False for bank-only).

        Returns:
            SearchResult containing matching transactions and page references.
        """
        target_dates = []
        for d in dates:
            if isinstance(d, str):
                target_dates.append(self.parse_date(d))
            else:
                target_dates.append(d)

        result = SearchResult(query_dates=target_dates)

        # Auto-discover statements dynamically
        statements = self.discover_statements(banks=banks)

        if not statements:
            result.errors.append(f"No statement files discovered in {self.base_dir}")
            return result

        for stmt in statements:
            parser_name = stmt["parser"]

            # By default skip AIS unless explicitly included or banks list requested 'ais'
            if parser_name == "ais" and not include_ais:
                if not (banks and any("ais" in b.lower() for b in banks)):
                    continue

            parser_cls = PARSERS.get(parser_name)
            if not parser_cls:
                continue

            parser = parser_cls()
            pdf_path = stmt["path"]
            password = stmt["password"]

            try:
                txns = parser.search(pdf_path, target_dates, password)
                for t in txns:
                    t.bank = stmt["bank"]
                    t.account_type = stmt["account_type"]

                result.transactions.extend(txns)

                # Locate page numbers for screenshot attachments
                for d in target_dates:
                    matching_for_date = [t for t in txns if t.date == d]
                    if matching_for_date:
                        pages = parser.find_pages(pdf_path, d, password)
                        for page in pages:
                            result.source_pages[(pdf_path, page)] = d

            except Exception as e:
                result.errors.append(
                    f"Error reading {stmt['bank']} ({stmt['filename']}): {str(e)}"
                )

        result.transactions.sort(key=lambda t: (t.date, t.bank, t.txn_type))

        if exclude:
            result = result.exclude(exclude)

        return result
