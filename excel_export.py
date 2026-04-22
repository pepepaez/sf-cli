"""Generate Excel workbooks from sf-cli data without a template.

Public API:
    create_xlsx(sheets, out_path)
    sheets: list of (sheet_name, headers, rows)
    rows:   list of lists — each value is str, int, float, or None
"""

import io
import re
import zipfile
from xml.sax.saxutils import escape as xml_escape

_INVALID_XML = re.compile(
    r"[^\x09\x0A\x0D\x20-퟿-�\U00010000-\U0010FFFF]"
)

_WORKSHEET_TYPE = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"
)
_STYLES_TYPE = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles"
)


def _sanitize(s):
    return _INVALID_XML.sub("", str(s)) if s is not None else ""


def _col_letter(n):
    """0-based column index to Excel letter(s): 0→A, 25→Z, 26→AA …"""
    s = ""
    n += 1
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _cell(col_idx, row_num, value):
    ref = f"{_col_letter(col_idx)}{row_num}"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f'<c r="{ref}"><v>{value}</v></c>'
    s = xml_escape(_sanitize(value)) if value else ""
    if not s:
        return ""
    return f'<c r="{ref}" t="inlineStr"><is><t xml:space="preserve">{s}</t></is></c>'


def _sheet_xml(headers, rows):
    n_cols   = len(headers)
    all_rows = [headers] + rows
    last_col = _col_letter(n_cols - 1)
    last_row = len(all_rows)

    row_xml = []
    for r_idx, row_vals in enumerate(all_rows, start=1):
        cells = "".join(_cell(c, r_idx, v) for c, v in enumerate(row_vals))
        row_xml.append(f'<row r="{r_idx}">{cells}</row>')

    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<dimension ref="A1:{last_col}{last_row}"/>'
        '<sheetViews><sheetView workbookViewId="0">'
        '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
        '</sheetView></sheetViews>'
        '<sheetData>' + "".join(row_xml) + '</sheetData>'
        f'<autoFilter ref="A1:{last_col}{last_row}"/>'
        '</worksheet>'
    ).encode("utf-8")


_STYLES_XML = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>
  <fills count="2">
    <fill><patternFill patternType="none"/></fill>
    <fill><patternFill patternType="gray125"/></fill>
  </fills>
  <borders count="1">
    <border><left/><right/><top/><bottom/><diagonal/></border>
  </borders>
  <cellStyleXfs count="1">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0"/>
  </cellStyleXfs>
  <cellXfs count="1">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
  </cellXfs>
</styleSheet>"""


def create_xlsx(sheets, out_path):
    """Write a multi-sheet xlsx to out_path.

    sheets: [(name, headers_list, rows_list), ...]
    """
    n = len(sheets)

    content_types = "\n".join(
        f'  <Override PartName="/xl/worksheets/sheet{i+1}.xml"'
        f' ContentType="application/vnd.openxmlformats-officedocument'
        f'.spreadsheetml.worksheet+xml"/>'
        for i in range(n)
    )

    sheet_els = "\n".join(
        f'    <sheet name="{xml_escape(name)}" sheetId="{i+1}" r:id="rId{i+1}"/>'
        for i, (name, _, _) in enumerate(sheets)
    )

    ws_rels = "\n".join(
        f'  <Relationship Id="rId{i+1}" Type="{_WORKSHEET_TYPE}"'
        f' Target="worksheets/sheet{i+1}.xml"/>'
        for i in range(n)
    )
    styles_rel = (
        f'  <Relationship Id="rId{n+1}" Type="{_STYLES_TYPE}"'
        f' Target="styles.xml"/>'
    )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
{content_types}
</Types>""")

        zf.writestr("_rels/.rels", """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>""")

        zf.writestr("xl/workbook.xml", f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
{sheet_els}
  </sheets>
</workbook>""")

        zf.writestr("xl/_rels/workbook.xml.rels", f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
{ws_rels}
{styles_rel}
</Relationships>""")

        zf.writestr("xl/styles.xml", _STYLES_XML)

        for i, (_, headers, rows) in enumerate(sheets):
            zf.writestr(f"xl/worksheets/sheet{i+1}.xml", _sheet_xml(headers, rows))

    with open(out_path, "wb") as f:
        f.write(buf.getvalue())
