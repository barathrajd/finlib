"""Data models for transactions and search results."""

from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass
class Transaction:
    """Represents a single bank transaction."""

    date: date
    description: str
    amount: float
    balance: float
    txn_type: str  # 'debit' or 'credit'
    ref_no: str = ""
    value_date: Optional[date] = None
    bank: str = ""
    account_type: str = ""  # 'savings', 'credit_card'
    raw_line: str = ""  # original text from PDF

    @property
    def amount_display(self) -> str:
        """Format amount with commas for display."""
        return f"{self.amount:,.2f}"

    @property
    def balance_display(self) -> str:
        """Format balance with commas for display."""
        return f"{self.balance:,.2f}"


@dataclass
class SearchResult:
    """Result of a transaction search across bank statements."""

    query_dates: list[date] = field(default_factory=list)
    transactions: list[Transaction] = field(default_factory=list)
    source_pages: dict = field(default_factory=dict)  # {(pdf_path, page_num): date}
    errors: list[str] = field(default_factory=list)

    @property
    def total_debits(self) -> float:
        return sum(t.amount for t in self.transactions if t.txn_type == "debit")

    @property
    def total_credits(self) -> float:
        return sum(t.amount for t in self.transactions if t.txn_type == "credit")

    def for_date(self, d: date) -> list[Transaction]:
        """Get transactions for a specific date."""
        return [t for t in self.transactions if t.date == d]

    def for_bank(self, bank: str) -> list[Transaction]:
        """Get transactions for a specific bank."""
        return [t for t in self.transactions if t.bank.lower() == bank.lower()]

    def exclude(self, keywords: list[str]) -> "SearchResult":
        """Return a new SearchResult excluding transactions matching keywords."""
        filtered = [
            t for t in self.transactions
            if not any(kw.lower() in t.description.lower() for kw in keywords)
        ]
        return SearchResult(
            query_dates=self.query_dates,
            transactions=filtered,
            source_pages=self.source_pages,
            errors=self.errors,
        )
