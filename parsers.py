"""Bank statement and financial document PDF parsers.

Each parser extracts transactions/records from bank-specific PDF formats
using pdftotext with -layout mode for column-aligned output.
"""

import re
import subprocess
from abc import ABC, abstractmethod
from datetime import date, datetime
from typing import Optional

from finlib.models import Transaction


def _parse_amount(s: str) -> float:
    """Parse a comma-formatted amount string like '10,045.00' to float."""
    if not s or s.strip() == "" or s.strip() == "-":
        return 0.0
    return float(s.strip().replace(",", ""))


def _extract_text(pdf_path: str, password: Optional[str] = None, layout: bool = True) -> str:
    """Extract text from a PDF using pdftotext."""
    cmd = ["pdftotext"]
    if password:
        cmd.extend(["-upw", password])
    if layout:
        cmd.append("-layout")
    cmd.extend([pdf_path, "-"])
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout


def _extract_page_text(pdf_path: str, page: int, password: Optional[str] = None, layout: bool = True) -> str:
    """Extract text from a specific page of a PDF."""
    cmd = ["pdftotext"]
    if password:
        cmd.extend(["-upw", password])
    if layout:
        cmd.append("-layout")
    cmd.extend(["-f", str(page), "-l", str(page), pdf_path, "-"])
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout


def _find_pages_with_date(pdf_path: str, date_str: str, password: Optional[str] = None, max_pages: int = 200) -> list[int]:
    """Find which pages in a PDF contain a specific date string."""
    pages = []
    for page in range(1, max_pages + 1):
        text = _extract_page_text(pdf_path, page, password, layout=False)
        if text.strip() == "":
            break
        if date_str in text:
            pages.append(page)
    return pages


class BankParser(ABC):
    """Base class for financial statement parsers."""

    bank_name: str = ""
    date_format: str = ""

    @abstractmethod
    def parse_transactions(self, pdf_path: str, password: Optional[str] = None) -> list[Transaction]:
        """Parse all transactions/records from a document PDF."""
        ...

    @abstractmethod
    def format_date_for_search(self, d: date) -> str:
        """Convert a date to the string format used in this document's text."""
        ...

    def find_pages(self, pdf_path: str, d: date, password: Optional[str] = None) -> list[int]:
        """Find pages containing transactions for a given date."""
        date_str = self.format_date_for_search(d)
        return _find_pages_with_date(pdf_path, date_str, password)

    def search(self, pdf_path: str, target_dates: list[date], password: Optional[str] = None) -> list[Transaction]:
        """Search for transactions on specific dates."""
        all_txns = self.parse_transactions(pdf_path, password)
        return [t for t in all_txns if t.date in target_dates]


class HDFCParser(BankParser):
    """Parser for HDFC Bank savings account statements."""

    bank_name = "HDFC Bank"

    TXN_PATTERN = re.compile(
        r"^\s*(\d{2}/\d{2}/\d{2})\s+"   # transaction date
        r"(.+?)\s{2,}"                  # description
        r"(\d{10,16})\s+"              # reference number
        r"(\d{2}/\d{2}/\d{2})\s+"      # value date
        r"(.*)$"                        # amounts
    )

    def format_date_for_search(self, d: date) -> str:
        return d.strftime("%d/%m/%y")

    def _parse_date(self, s: str) -> date:
        return datetime.strptime(s, "%d/%m/%y").date()

    def parse_transactions(self, pdf_path: str, password: Optional[str] = None) -> list[Transaction]:
        text = _extract_text(pdf_path, password, layout=True)
        transactions = []

        for line in text.split("\n"):
            m = self.TXN_PATTERN.match(line)
            if not m:
                continue

            txn_date = self._parse_date(m.group(1))
            description = m.group(2).strip()
            ref_no = m.group(3).strip()
            value_date = self._parse_date(m.group(4))
            amounts_str = m.group(5).strip()

            amounts = re.findall(r"[\d,]+\.\d{2}", amounts_str)

            if len(amounts) < 2:
                continue

            balance = _parse_amount(amounts[-1])

            if len(amounts) == 2:
                amount = _parse_amount(amounts[0])
                amt_pos_in_line = line.find(amounts[0], line.find(ref_no) + len(ref_no))
                if amt_pos_in_line < 165:
                    txn_type = "debit"
                else:
                    txn_type = "credit"
            elif len(amounts) == 3:
                debit = _parse_amount(amounts[0])
                credit = _parse_amount(amounts[1])
                if debit > 0:
                    amount = debit
                    txn_type = "debit"
                else:
                    amount = credit
                    txn_type = "credit"
            else:
                continue

            transactions.append(Transaction(
                date=txn_date,
                description=description,
                amount=amount,
                balance=balance,
                txn_type=txn_type,
                ref_no=ref_no,
                value_date=value_date,
                bank=self.bank_name,
                account_type="savings",
                raw_line=line.strip(),
            ))

        return transactions


class SBIParser(BankParser):
    """Parser for SBI savings account statements."""

    bank_name = "SBI"

    TXN_PATTERN = re.compile(
        r"^\s*(\d{2}/\d{2}/\d{4})\s+"
        r"(\d{2}/\d{2}/\d{4})\s+"
        r"(.+?)\s+"
        r"(-\s+)?([\d,]+\.\d{2})\s+"
        r"(-\s+)?([\d,]+\.\d{2})\s*$"
    )

    def format_date_for_search(self, d: date) -> str:
        return d.strftime("%d/%m/%Y")

    def _parse_date(self, s: str) -> date:
        return datetime.strptime(s, "%d/%m/%Y").date()

    def parse_transactions(self, pdf_path: str, password: Optional[str] = None) -> list[Transaction]:
        text = _extract_text(pdf_path, password, layout=True)
        transactions = []
        current_txn = None

        for line in text.split("\n"):
            m = self.TXN_PATTERN.match(line)
            if m:
                if current_txn:
                    transactions.append(current_txn)

                txn_date = self._parse_date(m.group(1))
                value_date = self._parse_date(m.group(2))
                description = m.group(3).strip()
                amount = _parse_amount(m.group(5))
                balance = _parse_amount(m.group(7))

                has_leading_dash = m.group(4) is not None
                txn_type = "debit" if has_leading_dash else "credit"

                current_txn = Transaction(
                    date=txn_date,
                    description=description,
                    amount=amount,
                    balance=balance,
                    txn_type=txn_type,
                    value_date=value_date,
                    bank=self.bank_name,
                    account_type="savings",
                    raw_line=line.strip(),
                )
            elif current_txn and line.strip() and not line.strip().startswith("Page"):
                extra = line.strip()
                if extra and not re.match(r"^\s*Balance", extra):
                    current_txn.description += " " + extra

        if current_txn:
            transactions.append(current_txn)

        return transactions


class IDFCParser(BankParser):
    """Parser for IDFC First Bank savings and credit card statements."""

    bank_name = "IDFC First Bank"

    TXN_PATTERN = re.compile(
        r"^\s*(\d{2}-[A-Za-z]{3}-\d{4})\s+"
        r"(\d{2}-[A-Za-z]{3}-\d{4})\s+"
        r"(.*)$"
    )

    def format_date_for_search(self, d: date) -> str:
        return d.strftime("%d-%b-%Y")

    def _parse_date(self, s: str) -> date:
        return datetime.strptime(s, "%d-%b-%Y").date()

    def parse_transactions(self, pdf_path: str, password: Optional[str] = None) -> list[Transaction]:
        text = _extract_text(pdf_path, password, layout=True)
        transactions = []
        current_txn = None

        for line in text.split("\n"):
            m = self.TXN_PATTERN.match(line)
            if m:
                if current_txn:
                    transactions.append(current_txn)

                txn_date = self._parse_date(m.group(1))
                value_date = self._parse_date(m.group(2))
                rest = m.group(3).strip()

                amounts = re.findall(r"[\d,]+\.\d{2}", rest)
                desc = re.sub(r"\s*[\d,]+\.\d{2}", "", rest).strip()

                if len(amounts) >= 2:
                    balance = _parse_amount(amounts[-1])
                    first_amt = amounts[0]
                    first_amt_pos = line.find(first_amt, line.find(m.group(2)) + len(m.group(2)))

                    if len(amounts) == 3:
                        amount = _parse_amount(amounts[0])
                        txn_type = "debit"
                    elif len(amounts) == 2:
                        amount = _parse_amount(amounts[0])
                        if first_amt_pos < 100:
                            txn_type = "credit"
                        else:
                            txn_type = "debit"
                    else:
                        continue

                    current_txn = Transaction(
                        date=txn_date,
                        description=desc if desc else "(see continuation)",
                        amount=amount,
                        balance=balance,
                        txn_type=txn_type,
                        value_date=value_date,
                        bank=self.bank_name,
                        account_type="savings",
                        raw_line=line.strip(),
                    )
                else:
                    current_txn = None
            elif current_txn and line.strip():
                extra = line.strip()
                if (extra and not extra.startswith("REGISTERED") 
                    and not extra.startswith("Page") 
                    and not extra.startswith("STATEMENT")):
                    if current_txn.description == "(see continuation)":
                        current_txn.description = extra
                    else:
                        current_txn.description += " " + extra

        if current_txn:
            transactions.append(current_txn)

        return transactions


class LoanRepaymentParser(BankParser):
    """Parser for loan repayment schedule PDFs (HDFC/Bajaj/NBFC)."""

    bank_name = "Loan Schedule"

    def format_date_for_search(self, d: date) -> str:
        return d.strftime("%d/%m/%Y")

    def _parse_date(self, s: str) -> date:
        return datetime.strptime(s, "%d/%m/%Y").date()

    def parse_transactions(self, pdf_path: str, password: Optional[str] = None) -> list[Transaction]:
        text = _extract_text(pdf_path, password, layout=True)
        transactions = []

        # Find agreement/account number or customer name if present
        loan_ref = ""
        ref_match = re.search(r"(?:Agreement No\.|Loan Account Number)\s*:?\s*(\w+)", text)
        if ref_match:
            loan_ref = ref_match.group(1).strip()

        # Format 1: Instl No | Due Date | Instl Amt | Principal | Interest | O/s Principal
        # Format 2: Instl Num | Due Date | Opening Principal | Installment Amt | Principal | Interest | Closing Principal
        line_pattern = re.compile(
            r"^\s*(\d{1,3})\s+(\d{2}/\d{2}/\d{4})\s+([\d,]+\.?\d*)\s+([\d,]+\.?\d*)\s+([\d,]+\.?\d*)"
        )

        for line in text.split("\n"):
            m = line_pattern.match(line)
            if not m:
                continue

            instl_no = m.group(1)
            due_date = self._parse_date(m.group(2))
            amounts = re.findall(r"[\d,]+\.\d{2}|[\d,]+", line[m.end(2):])
            
            if len(amounts) >= 3:
                # Installment amount & closing balance
                instl_amt = _parse_amount(amounts[0])
                closing_bal = _parse_amount(amounts[-1])
                desc = f"Loan EMI #{instl_no}" + (f" (A/c {loan_ref})" if loan_ref else "")

                transactions.append(Transaction(
                    date=due_date,
                    description=desc,
                    amount=instl_amt,
                    balance=closing_bal,
                    txn_type="debit",
                    ref_no=f"EMI-{instl_no}",
                    value_date=due_date,
                    bank="Loan Repayment",
                    account_type="loan",
                    raw_line=line.strip(),
                ))

        return transactions


class AISParser(BankParser):
    """Parser for Annual Information Statement (AIS) PDFs."""

    bank_name = "AIS"

    # Line pattern: Serial | Quarter | Date | Paid/Credited | TDS Deducted | TDS Deposited | Status
    LINE_PATTERN = re.compile(
        r"^\s*(\d+)\s+(Q[1-4]\([^\)]+\))\s+(\d{2}/\d{2}/\d{4})\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+(\w+)"
    )

    def format_date_for_search(self, d: date) -> str:
        return d.strftime("%d/%m/%Y")

    def _parse_date(self, s: str) -> date:
        return datetime.strptime(s, "%d/%m/%Y").date()

    def parse_transactions(self, pdf_path: str, password: Optional[str] = None) -> list[Transaction]:
        text = _extract_text(pdf_path, password, layout=True)
        transactions = []

        current_category = "Tax / Income Record"
        for line in text.split("\n"):
            # Detect section header (Salary, Dividend, Interest, etc.)
            if line.strip() in ("Salary", "Dividend", "Interest from savings bank", "Sale of securities and units of mutual fund"):
                current_category = line.strip()

            m = self.LINE_PATTERN.match(line)
            if not m:
                continue

            sr_no = m.group(1)
            quarter = m.group(2)
            rec_date = self._parse_date(m.group(3))
            amt_paid = _parse_amount(m.group(4))
            tds_ded = _parse_amount(m.group(5))
            status = m.group(7)

            if amt_paid <= 0 and tds_ded <= 0:
                continue

            desc = f"AIS: {current_category} ({quarter}, TDS: Rs.{tds_ded:,.0f}, Status: {status})"

            transactions.append(Transaction(
                date=rec_date,
                description=desc,
                amount=amt_paid,
                balance=0.0,
                txn_type="credit",
                ref_no=f"AIS-{sr_no}",
                value_date=rec_date,
                bank="Income Tax AIS",
                account_type="tax_record",
                raw_line=line.strip(),
            ))

        return transactions


PARSERS = {
    "hdfc": HDFCParser,
    "sbi": SBIParser,
    "idfc": IDFCParser,
    "loan": LoanRepaymentParser,
    "ais": AISParser,
}
