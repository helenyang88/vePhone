import pytest
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile


@pytest.fixture()
def authenticated_client(client, initialized_admin):
    return client


def test_preview_csv_case_import_validates_rows(authenticated_client):
    existing = authenticated_client.post(
        "/api/v1/cases",
        json={
            "title": "已有用例",
            "module": "账号",
            "content_markdown": "## 执行任务\n- 已存在",
            "tags": ["P0"],
            "automation_level": "auto",
        },
    )
    assert existing.status_code == 201

    csv_text = (
        "title,module,tags,content_markdown\n"
        "登录成功,账号,\"P0,smoke\",\"## 执行任务\\n- 打开 App\"\n"
        "已有用例,账号,P1,\"## 执行任务\\n- 重复标题\"\n"
        ",支付,P2,\"## 执行任务\\n- 缺少标题\"\n"
        "空内容,支付,P2,\n"
    )

    response = authenticated_client.post(
        "/api/v1/cases/import/preview",
        json={"format": "csv", "content": csv_text},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["summary"] == {
        "total": 4,
        "valid": 2,
        "warning": 1,
        "error": 2,
    }
    assert body["items"][0]["status"] == "valid"
    assert body["items"][0]["draft"]["tags"] == ["P0", "smoke"]
    assert body["items"][1]["status"] == "warning"
    assert body["items"][1]["messages"] == ["用例库中已有同名用例"]
    assert body["items"][2]["status"] == "error"
    assert body["items"][2]["messages"] == ["用例名称不能为空"]
    assert body["items"][3]["status"] == "error"
    assert body["items"][3]["messages"] == ["用例内容不能为空"]


def test_import_csv_cases_creates_only_confirmed_valid_rows(authenticated_client):
    csv_text = (
        "title,module,tags,content_markdown\n"
        "导入用例A,账号,\"P0, smoke\",\"## 执行任务\\n- 打开 App\"\n"
        "导入用例B,,P1,\"## 执行任务\\n- 查看首页\"\n"
    )
    preview = authenticated_client.post(
        "/api/v1/cases/import/preview",
        json={"format": "csv", "content": csv_text},
    )
    assert preview.status_code == 200
    assert preview.json()["summary"]["valid"] == 2

    response = authenticated_client.post(
        "/api/v1/cases/import",
        json={"items": [item["draft"] for item in preview.json()["items"]]},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["created_count"] == 2
    assert [item["title"] for item in body["items"]] == [
        "导入用例A",
        "导入用例B",
    ]
    assert body["items"][0]["tags"] == ["P0", "smoke"]

    listed = authenticated_client.get(
        "/api/v1/cases",
        params={"search": "导入用例"},
    )
    assert listed.status_code == 200
    assert listed.json()["total"] == 2


def test_case_import_rejects_too_many_rows(authenticated_client):
    csv_text = "title,module,tags,content_markdown\n" + "\n".join(
        f"用例{i},模块,tag,内容{i}" for i in range(101)
    )

    response = authenticated_client.post(
        "/api/v1/cases/import/preview",
        json={"format": "csv", "content": csv_text},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "case_import_too_many_rows"


def test_preview_markdown_case_import(authenticated_client):
    markdown = """---
title: Markdown 导入
module: 账号
tags: [P0, smoke]
---

## 执行任务
- 打开 App
---CASE---
---
title: 第二条
tags: [P1]
---

## 执行任务
- 查看首页
"""

    response = authenticated_client.post(
        "/api/v1/cases/import/preview",
        json={"format": "markdown", "content": markdown},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["valid"] == 2
    assert body["items"][0]["draft"]["title"] == "Markdown 导入"
    assert body["items"][0]["draft"]["module"] == "账号"
    assert body["items"][0]["draft"]["tags"] == ["P0", "smoke"]
    assert body["items"][0]["draft"]["content_markdown"].startswith("## 执行任务")


def test_preview_excel_paste_case_import(authenticated_client):
    tsv = (
        "title\tmodule\ttags\tcontent_markdown\n"
        "Excel 导入\t账号\tP0,smoke\t## 执行任务\\n- 打开 App"
    )

    response = authenticated_client.post(
        "/api/v1/cases/import/preview",
        json={"format": "excel", "content": tsv},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["valid"] == 1
    assert body["items"][0]["draft"]["title"] == "Excel 导入"
    assert body["items"][0]["draft"]["tags"] == ["P0", "smoke"]


def test_preview_csv_file_case_import(authenticated_client):
    csv_text = (
        "title,module,tags,content_markdown\n"
        "文件导入,账号,\"P0,smoke\",\"## 执行任务\\n- 打开 App\""
    )

    response = authenticated_client.post(
        "/api/v1/cases/import/file/preview",
        params={"format": "auto"},
        content=csv_text.encode("utf-8"),
        headers={
            "Content-Type": "application/octet-stream",
            "X-File-Name": "cases.csv",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["valid"] == 1
    assert body["items"][0]["draft"]["title"] == "文件导入"


def test_preview_xlsx_file_case_import(authenticated_client):
    buffer = _xlsx_bytes([
        ["title", "module", "tags", "content_markdown"],
        ["Excel 文件导入", "账号", "P0,smoke", "## 执行任务\n- 打开 App"],
    ])

    response = authenticated_client.post(
        "/api/v1/cases/import/file/preview",
        params={"format": "auto"},
        content=buffer,
        headers={
            "Content-Type": "application/octet-stream",
            "X-File-Name": "cases.xlsx",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["valid"] == 1
    assert body["items"][0]["draft"]["title"] == "Excel 文件导入"


def test_preview_file_import_rejects_unsupported_format(authenticated_client):
    response = authenticated_client.post(
        "/api/v1/cases/import/file/preview",
        content=b"hello",
        headers={
            "Content-Type": "application/octet-stream",
            "X-File-Name": "cases.txt",
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "case_import_unsupported_format"


def _xlsx_bytes(rows: list[list[str]]) -> bytes:
    sheet_rows = []
    for row_index, row in enumerate(rows, start=1):
        cells = []
        for col_index, value in enumerate(row):
            cell_ref = f"{chr(ord('A') + col_index)}{row_index}"
            escaped = (
                value.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )
            cells.append(
                f'<c r="{cell_ref}" t="inlineStr"><is><t>{escaped}</t></is></c>'
            )
        sheet_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')
    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(sheet_rows)}</sheetData>'
        "</worksheet>"
    )
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            "</Types>",
        )
        archive.writestr(
            "xl/workbook.xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<sheets><sheet name="Sheet1" sheetId="1" r:id="rId1" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"/></sheets>'
            "</workbook>",
        )
        archive.writestr("xl/worksheets/sheet1.xml", sheet_xml)
    return output.getvalue()
