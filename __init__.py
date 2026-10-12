"""finlib - Personal Finance Transaction Search Library.

A library to search transactions across HDFC, SBI, and IDFC bank
statement PDFs and generate formatted PDF reports.
"""

from finlib.models import Transaction, SearchResult
from finlib.finder import TransactionFinder
from finlib.report import ReportGenerator

__version__ = "1.0.0"
__all__ = ["Transaction", "SearchResult", "TransactionFinder", "ReportGenerator"]
