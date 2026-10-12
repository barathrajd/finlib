"""PDF report generator for transaction search results."""

import os
from datetime import date
from pathlib import Path
from typing import Optional

import pymupdf
from fpdf import FPDF

from finlib.models import SearchResult, Transaction


class _TransactionPDF(FPDF):
    """Internal PDF class with formatted headers and footers."""

    def header(self):
        self.set_font("Helvetica", "B", 16)
        self.set_text_color(33, 37, 41)
        self.cell(0, 12, "Bank Transaction Statement", align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(0, 102, 204)
        self.set_line_width(0.8)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(6)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}}", align="C")


class ReportGenerator:
    """Generate PDF reports from transaction search results."""

    COLS = ["#", "Bank", "Description", "Type", "Amount (Rs.)", "Balance (Rs.)"]
    WIDTHS = [8, 24, 72, 14, 28, 28]
    ALIGNS = ["C", "L", "L", "C", "R", "R"]

    def generate(
        self,
        result: SearchResult,
        output_path: str,
        attach_screenshots: bool = True,
        title: str = "Bank Transaction Statement",
    ) -> str:
        pdf = _TransactionPDF()
        pdf.alias_nb_pages()
        pdf.set_auto_page_break(auto=True, margin=20)
        pdf.add_page()

        for query_date in sorted(result.query_dates):
            txns = result.for_date(query_date)
            if not txns:
                self._add_empty_section(pdf, query_date)
                continue

            self._add_date_section(pdf, query_date, txns)

        pdf.ln(8)
        self._add_note(pdf, result)

        temp_path = output_path + ".tmp"
        pdf.output(temp_path)

        if attach_screenshots and result.source_pages:
            self._attach_screenshots(temp_path, output_path, result)
        else:
            if os.path.exists(output_path):
                os.remove(output_path)
            os.rename(temp_path, output_path)

        return output_path

    def _add_date_section(self, pdf: FPDF, d: date, txns: list[Transaction]):
        date_str = d.strftime("%d %B %Y")

        if pdf.get_y() > 240:
            pdf.add_page()

        pdf.set_font("Helvetica", "B", 13)
        pdf.set_fill_color(0, 102, 204)
        pdf.set_text_color(255, 255, 255)
        banks_in_section = ", ".join(sorted(set(t.bank for t in txns)))
        pdf.cell(0, 10, f"  {date_str}  -  {banks_in_section}", fill=True,
                 new_x="LMARGIN", new_y="NEXT")
        pdf.ln(3)

        pdf.set_font("Helvetica", "B", 8)
        pdf.set_fill_color(240, 240, 240)
        pdf.set_text_color(33, 37, 41)
        pdf.set_draw_color(200, 200, 200)
        for i, col in enumerate(self.COLS):
            pdf.cell(self.WIDTHS[i], 8, col, border=1, fill=True, align="C")
        pdf.ln()

        for idx, txn in enumerate(txns):
            if pdf.get_y() > 265:
                pdf.add_page()
                pdf.set_font("Helvetica", "B", 8)
                pdf.set_fill_color(240, 240, 240)
                pdf.set_text_color(33, 37, 41)
                for i, col in enumerate(self.COLS):
                    pdf.cell(self.WIDTHS[i], 8, col, border=1, fill=True, align="C")
                pdf.ln()

            self._add_row(pdf, idx + 1, txn, is_alt=(idx % 2 == 1))

        total_debit = sum(t.amount for t in txns if t.txn_type == "debit")
        total_credit = sum(t.amount for t in txns if t.txn_type == "credit")
        self._add_summary(pdf, total_debit, total_credit)
        pdf.ln(8)

    def _add_empty_section(self, pdf: FPDF, d: date):
        date_str = d.strftime("%d %B %Y")
        pdf.set_font("Helvetica", "B", 13)
        pdf.set_fill_color(180, 180, 180)
        pdf.set_text_color(255, 255, 255)
        pdf.cell(0, 10, f"  {date_str}  -  No transactions found", fill=True,
                 new_x="LMARGIN", new_y="NEXT")
        pdf.ln(5)

    def _add_row(self, pdf: FPDF, idx: int, txn: Transaction, is_alt: bool = False):
        pdf.set_font("Helvetica", "", 7.5)
        pdf.set_text_color(50, 50, 50)
        pdf.set_fill_color(248, 249, 250) if is_alt else pdf.set_fill_color(255, 255, 255)
        pdf.set_draw_color(220, 220, 220)

        row_h = 8
        values = [
            str(idx),
            txn.bank.split()[0],
            txn.description[:52],
            "Dr" if txn.txn_type == "debit" else "Cr",
            txn.amount_display,
            txn.balance_display,
        ]

        for i, val in enumerate(values):
            pdf.cell(self.WIDTHS[i], row_h, val, border=1, fill=True, align=self.ALIGNS[i])
        pdf.ln()

    def _add_summary(self, pdf: FPDF, total_debit: float, total_credit: float):
        pdf.set_font("Helvetica", "B", 8.5)
        pdf.set_fill_color(230, 240, 255)
        pdf.set_text_color(0, 51, 153)
        pdf.set_draw_color(0, 102, 204)

        label_w = sum(self.WIDTHS[:-2])
        parts = []
        if total_debit > 0:
            parts.append(f"Debits: {total_debit:,.2f}")
        if total_credit > 0:
            parts.append(f"Credits: {total_credit:,.2f}")
        label = "Total " + "  |  ".join(parts)

        net = total_credit - total_debit
        net_str = f"Net: {'+' if net >= 0 else ''}{net:,.2f}"

        pdf.cell(label_w, 9, label, border=1, fill=True, align="R")
        pdf.cell(self.WIDTHS[-2], 9, net_str, border=1, fill=True, align="R")
        pdf.cell(self.WIDTHS[-1], 9, "", border=1, fill=True, align="R")
        pdf.ln()

    def _add_note(self, pdf: FPDF, result: SearchResult):
        pdf.set_font("Helvetica", "I", 7.5)
        pdf.set_text_color(120, 120, 120)
        dates_str = ", ".join(d.strftime("%d/%m/%Y") for d in sorted(result.query_dates))
        note = f"Report generated for dates: {dates_str}."
        if result.errors:
            note += " Some sources could not be read: " + "; ".join(result.errors[:3])
        pdf.multi_cell(0, 4, note)

    def _attach_screenshots(
        self, temp_pdf_path: str, output_path: str, result: SearchResult
    ):
        doc = pymupdf.open(temp_pdf_path)

        sep = doc.new_page(width=595, height=842)
        sep.insert_text(
            pymupdf.Point(50, 100),
            "Original Bank Statement Screenshots",
            fontsize=20, fontname="helv", color=(0, 0.4, 0.8),
        )
        sep.insert_text(
            pymupdf.Point(50, 140),
            "The following pages are extracted from original bank statement PDFs.",
            fontsize=12, fontname="helv", color=(0.3, 0.3, 0.3),
        )
        sep.draw_line(
            pymupdf.Point(50, 160), pymupdf.Point(545, 160),
            color=(0, 0.4, 0.8), width=1.5,
        )

        y_pos = 190
        for i, ((pdf_path, page_num), d) in enumerate(sorted(result.source_pages.items(), key=lambda x: x[1])):
            bank_name = Path(pdf_path).stem
            label = f"Page {i + 1}:  {bank_name} - Page {page_num} ({d.strftime('%d %B %Y')})"
            sep.insert_text(
                pymupdf.Point(50, y_pos),
                label, fontsize=12, fontname="helv", color=(0.2, 0.2, 0.2),
            )
            y_pos += 25

        for (pdf_path, page_num), d in sorted(result.source_pages.items(), key=lambda x: x[1]):
            password = None
            pdf_dir = Path(pdf_path).parent
            pw_file = pdf_dir / "password.txt"
            if pw_file.exists():
                password = pw_file.read_text().strip()

            try:
                src_doc = pymupdf.open(pdf_path)
                if password:
                    src_doc.authenticate(password)

                page = src_doc[page_num - 1]
                zoom = 200 / 72
                pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))

                img_data = pix.tobytes("png")
                img_doc = pymupdf.open("png", img_data)
                img_pdf = pymupdf.open("pdf", img_doc.convert_to_pdf())
                doc.insert_pdf(img_pdf)

                img_doc.close()
                img_pdf.close()
                src_doc.close()
            except Exception as e:
                err_page = doc.new_page(width=595, height=842)
                err_page.insert_text(
                    pymupdf.Point(50, 100),
                    f"Could not render: {Path(pdf_path).name} page {page_num}",
                    fontsize=14, fontname="helv", color=(0.8, 0, 0),
                )
                err_page.insert_text(
                    pymupdf.Point(50, 130),
                    str(e), fontsize=10, fontname="helv", color=(0.5, 0.5, 0.5),
                )

        if os.path.exists(output_path):
            os.remove(output_path)
        doc.save(output_path)
        doc.close()

        if os.path.exists(temp_pdf_path):
            os.unlink(temp_pdf_path)
