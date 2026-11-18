import io


def xlsx_bytes(book):
    """The workbook as .xlsx bytes, every cell plain data. openpyxl stores a string that starts with "=" as a formula,
    so a reimbursement note or a paper title someone typed as "=..." would be evaluated by Excel; the exports write
    no formulas of their own."""
    for sheet in book.worksheets:
        for row in sheet.iter_rows():
            for cell in row:
                if cell.data_type == "f":
                    cell.data_type = "s"
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()
