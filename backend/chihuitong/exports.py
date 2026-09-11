import io

from django.http import HttpResponse
from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell


def excel_response(headers, rows, *, filename="export.xlsx"):
    book = Workbook(write_only=True)
    sheet = book.create_sheet("明细")
    sheet.append(headers)
    for values in rows:
        cells = []
        for value in values:
            cell = WriteOnlyCell(sheet, value=value)
            if isinstance(value, str):
                cell.data_type = "s"
            cells.append(cell)
        sheet.append(cells)
    output = io.BytesIO()
    book.save(output)
    response = HttpResponse(
        output.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
