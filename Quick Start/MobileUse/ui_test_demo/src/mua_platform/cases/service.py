import csv
from datetime import UTC, datetime, time, timedelta
from io import BytesIO, StringIO
from pathlib import Path
from zoneinfo import ZoneInfo
from zipfile import BadZipFile, ZipFile
import xml.etree.ElementTree as ET
from uuid import uuid4

from sqlalchemy import case as sql_case
from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session

from mua_platform.business.models import DEFAULT_BUSINESS_ID
from mua_platform.cases.models import CASE_TEMPLATE, TestCase
from mua_platform.cases.schemas import (
    CaseImportPreviewItem,
    CaseImportPreviewResponse,
    CaseImportSummary,
    TestCaseCreate,
    TestCaseResponse,
    TestCaseUpdate,
)
from mua_platform.tasks.models import Task
from mua_platform.tasks.state_machine import ExecutionStatus, Verdict


def _terminal_task_conditions():
    return (
        Task.execution_status == ExecutionStatus.RESULT_READY,
        Task.verdict.in_((Verdict.PASS, Verdict.FAIL)),
    )


def _today_utc_bounds_for_shanghai() -> tuple[datetime, datetime]:
    today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    start = datetime.combine(
        today,
        time.min,
        tzinfo=ZoneInfo("Asia/Shanghai"),
    ).astimezone(UTC)
    return start, start + timedelta(days=1)


def _case_statistics_subquery():
    return (
        select(
            Task.case_id,
            func.count(Task.id).label("execution_count"),
            func.sum(
                sql_case((Task.verdict == Verdict.PASS, 1), else_=0)
            ).label("pass_count"),
            func.sum(
                sql_case((Task.verdict == Verdict.FAIL, 1), else_=0)
            ).label("fail_count"),
            func.max(Task.finished_at).label("last_executed_at"),
        )
        .where(*_terminal_task_conditions())
        .group_by(Task.case_id)
        .subquery()
    )


def _as_utc(value):
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=UTC)


class CaseService:
    def __init__(self, db: Session):
        self.db = db

    def create_case(
        self,
        payload: TestCaseCreate,
        created_by: str = "system",
        business_id: str = DEFAULT_BUSINESS_ID,
    ) -> TestCase:
        case = TestCase(
            id=f"case_{uuid4().hex}",
            business_id=business_id,
            title=payload.title,
            module=payload.module,
            content_markdown=payload.content_markdown or CASE_TEMPLATE,
            tags=payload.tags,
            automation_level=payload.automation_level,
            default_agent_options=(
                payload.default_agent_options.model_dump(exclude_none=True)
                if payload.default_agent_options is not None
                else None
            ),
            created_by=created_by,
        )
        try:
            self._ensure_tag_colors(case.tags)
            self.db.add(case)
            self.db.commit()
            self.db.refresh(case)
            return case
        except Exception:
            self.db.rollback()
            raise

    def get_case(
        self,
        case_id: str,
        business_id: str = DEFAULT_BUSINESS_ID,
    ) -> TestCase | None:
        return self.db.scalar(
            select(TestCase).where(
                TestCase.id == case_id,
                TestCase.business_id == business_id,
                TestCase.deleted_at.is_(None),
            )
        )

    def case_response(self, case: TestCase) -> TestCaseResponse:
        return self.case_responses([case])[0]

    def case_responses(
        self,
        cases: list[TestCase],
    ) -> list[TestCaseResponse]:
        if not cases:
            return []
        from mua_platform.test_plans.models import TestPlan, TestPlanCase

        case_ids = [case.id for case in cases]
        statistics = _case_statistics_subquery()
        statistics_by_case_id = {
            case_id: (
                execution_count,
                pass_count,
                fail_count,
                last_executed_at,
            )
            for (
                case_id,
                execution_count,
                pass_count,
                fail_count,
                last_executed_at,
            ) in self.db.execute(
                select(
                    statistics.c.case_id,
                    statistics.c.execution_count,
                    statistics.c.pass_count,
                    statistics.c.fail_count,
                    statistics.c.last_executed_at,
                ).where(statistics.c.case_id.in_(case_ids))
            )
        }
        bound_counts = {
            case_id: count
            for case_id, count in self.db.execute(
                select(
                    TestPlanCase.case_id,
                    func.count(TestPlanCase.plan_id),
                )
                .join(TestPlan, TestPlan.id == TestPlanCase.plan_id)
                .where(
                    TestPlanCase.case_id.in_(case_ids),
                    TestPlan.deleted_at.is_(None),
                )
                .group_by(TestPlanCase.case_id)
            )
        }
        responses = []
        for case in cases:
            values = statistics_by_case_id.get(case.id)
            responses.append(
                TestCaseResponse.model_validate(case).model_copy(
                    update={
                        "execution_count": values[0] if values else 0,
                        "pass_count": values[1] if values else 0,
                        "fail_count": values[2] if values else 0,
                        "last_executed_at": (
                            _as_utc(values[3]) if values else None
                        ),
                        "bound_plan_count": bound_counts.get(case.id, 0),
                    }
                )
            )
        return responses

    def copy_case(
        self,
        case_id: str,
        created_by: str = "system",
        business_id: str = DEFAULT_BUSINESS_ID,
    ) -> TestCase | None:
        source = self.get_case(case_id, business_id)
        if source is None:
            return None
        copied = TestCase(
            id=f"case_{uuid4().hex}",
            business_id=business_id,
            title=f"{source.title[:197]} 副本",
            module=source.module,
            content_markdown=source.content_markdown,
            tags=list(source.tags or []),
            automation_level=source.automation_level,
            default_agent_options=(
                dict(source.default_agent_options)
                if source.default_agent_options
                else None
            ),
            created_by=created_by,
        )
        try:
            self._ensure_tag_colors(copied.tags)
            self.db.add(copied)
            self.db.commit()
            self.db.refresh(copied)
            return copied
        except Exception:
            self.db.rollback()
            raise

    def preview_import(self, import_format: str, content: str) -> CaseImportPreviewResponse:
        rows = _parse_import_rows(import_format, content)
        return self._preview_import_rows(rows)

    def preview_import_file(
        self,
        *,
        filename: str,
        content: bytes,
        import_format: str = "auto",
    ) -> CaseImportPreviewResponse:
        if len(content) > 5 * 1024 * 1024:
            raise ValueError("case_import_file_too_large")
        rows = _parse_import_file(filename, content, import_format)
        return self._preview_import_rows(rows)

    def _preview_import_rows(
        self,
        rows: list[tuple[int, dict[str, str]]],
    ) -> CaseImportPreviewResponse:
        if len(rows) > 100:
            raise ValueError("case_import_too_many_rows")

        existing_titles = {
            title.casefold()
            for title in self.db.scalars(
                select(TestCase.title).where(TestCase.deleted_at.is_(None))
            ).all()
            if isinstance(title, str)
        }
        items: list[CaseImportPreviewItem] = []
        for row_number, row in rows:
            messages: list[str] = []
            title = (row.get("title") or "").strip()
            module = (row.get("module") or "").strip() or None
            content_markdown = _normalize_multiline(
                (row.get("content_markdown") or "").strip()
            )
            tags = _normalize_tags(row.get("tags") or "")

            if not title:
                messages.append("用例名称不能为空")
            if not content_markdown:
                messages.append("用例内容不能为空")
            if title and title.casefold() in existing_titles:
                messages.append("用例库中已有同名用例")

            status = "valid"
            if any(message.endswith("不能为空") for message in messages):
                status = "error"
            elif messages:
                status = "warning"

            items.append(
                CaseImportPreviewItem(
                    row=row_number,
                    status=status,
                    messages=messages,
                    draft=TestCaseCreate(
                        title=title or "缺少标题",
                        module=module,
                        content_markdown=content_markdown or " ",
                        tags=tags,
                        automation_level="auto",
                    ),
                )
            )

        return CaseImportPreviewResponse(
            items=items,
            summary=CaseImportSummary(
                total=len(items),
                valid=sum(item.status in {"valid", "warning"} for item in items),
                warning=sum(item.status == "warning" for item in items),
                error=sum(item.status == "error" for item in items),
            ),
        )

    def import_cases(
        self,
        drafts: list[TestCaseCreate],
        *,
        created_by: str,
        business_id: str = DEFAULT_BUSINESS_ID,
    ) -> list[TestCaseResponse]:
        created: list[TestCase] = []
        try:
            for draft in drafts:
                case = TestCase(
                    id=f"case_{uuid4().hex}",
                    business_id=business_id,
                    title=draft.title.strip(),
                    module=draft.module.strip() if draft.module else None,
                    content_markdown=draft.content_markdown,
                    tags=list(dict.fromkeys(tag.strip() for tag in draft.tags if tag.strip())),
                    automation_level=draft.automation_level,
                    default_agent_options=(
                        draft.default_agent_options.model_dump(exclude_none=True)
                        if draft.default_agent_options is not None
                        else None
                    ),
                    created_by=created_by,
                )
                self._ensure_tag_colors(case.tags)
                self.db.add(case)
                created.append(case)
            self.db.commit()
            for case in created:
                self.db.refresh(case)
            return self.case_responses(created)
        except Exception:
            self.db.rollback()
            raise

    def stats(self, business_id: str = DEFAULT_BUSINESS_ID) -> dict[str, int]:
        active_cases = (
            TestCase.deleted_at.is_(None),
            TestCase.business_id == business_id,
        )
        total = self.db.scalar(
            select(func.count(TestCase.id)).where(*active_cases)
        ) or 0
        auto_count = self.db.scalar(
            select(func.count(TestCase.id)).where(
                *active_cases,
                TestCase.automation_level == "auto"
            )
        ) or 0
        today_start, tomorrow_start = _today_utc_bounds_for_shanghai()
        today_executions = self.db.scalar(
            select(func.count(Task.id)).join(
                TestCase,
                TestCase.id == Task.case_id,
            ).where(
                *active_cases,
                *_terminal_task_conditions(),
                Task.finished_at >= today_start,
                Task.finished_at < tomorrow_start,
            )
        ) or 0
        total_executions, total_passes = self.db.execute(
            select(
                func.count(Task.id),
                func.sum(
                    sql_case((Task.verdict == Verdict.PASS, 1), else_=0)
                ),
            ).join(
                TestCase,
                TestCase.id == Task.case_id,
            ).where(
                *active_cases,
                *_terminal_task_conditions(),
            )
        ).one()
        total_executions = total_executions or 0
        total_passes = total_passes or 0
        pass_rate = (
            round((total_passes / total_executions) * 100)
            if total_executions
            else 0
        )
        return {
            "total": total,
            "auto_count": auto_count,
            "today_executions": today_executions,
            "total_executions": total_executions,
            "pass_rate": pass_rate,
        }

    def list_cases(
        self,
        *,
        business_id: str = DEFAULT_BUSINESS_ID,
        page: int = 1,
        page_size: int = 10,
        search: str | None = None,
        module: str | None = None,
        tags: list[str] | None = None,
        automation_level: str | None = None,
        created_by: str | None = None,
    ) -> tuple[list[TestCaseResponse], int]:
        from mua_platform.test_plans.models import TestPlan, TestPlanCase

        statistics = _case_statistics_subquery()
        query = (
            select(
                TestCase,
                statistics.c.execution_count,
                statistics.c.pass_count,
                statistics.c.fail_count,
                statistics.c.last_executed_at,
            )
            .outerjoin(statistics, statistics.c.case_id == TestCase.id)
        )
        filters = [
            TestCase.deleted_at.is_(None),
            TestCase.business_id == business_id,
        ]
        count_query = select(func.count(TestCase.id))

        if search:
            pattern = f"{search}%"
            filters.append(
                or_(
                    TestCase.title.ilike(pattern),
                    TestCase.id.ilike(pattern),
                    TestCase.module.ilike(pattern),
                )
            )
        if module:
            filters.append(TestCase.module == module)
        if automation_level:
            filters.append(TestCase.automation_level == automation_level)
        if created_by:
            filters.append(TestCase.created_by == created_by)
        tag_filters = list(dict.fromkeys(tags or []))
        if tag_filters:
            tag_values = (
                func.json_each(TestCase.tags)
                .table_valued("value")
                .alias("case_tag")
            )
            filters.append(
                exists(
                    select(1)
                    .select_from(tag_values)
                    .where(tag_values.c.value.in_(tag_filters))
                )
            )

        if filters:
            query = query.where(*filters)
            count_query = count_query.where(*filters)

        total = self.db.scalar(count_query) or 0
        rows = list(self.db.execute(
            query.order_by(TestCase.updated_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ))
        page_case_ids = [case.id for case, *_rest in rows]
        bound_counts = {
            case_id: count
            for case_id, count in self.db.execute(
                select(
                    TestPlanCase.case_id,
                    func.count(TestPlanCase.plan_id),
                )
                .join(TestPlan, TestPlan.id == TestPlanCase.plan_id)
                .where(
                    TestPlanCase.case_id.in_(page_case_ids),
                    TestPlan.deleted_at.is_(None),
                )
                .group_by(TestPlanCase.case_id)
            )
        } if page_case_ids else {}
        items = [
            TestCaseResponse.model_validate(case).model_copy(
                update={
                    "execution_count": execution_count or 0,
                    "pass_count": pass_count or 0,
                    "fail_count": fail_count or 0,
                    "last_executed_at": _as_utc(last_executed_at),
                    "bound_plan_count": bound_counts.get(case.id, 0),
                }
            )
            for (
                case,
                execution_count,
                pass_count,
                fail_count,
                last_executed_at,
            ) in rows
        ]
        return items, total

    def update_case(
        self,
        case_id: str,
        payload: TestCaseUpdate,
        business_id: str = DEFAULT_BUSINESS_ID,
    ) -> TestCase | None:
        case = self.get_case(case_id, business_id)
        if case is None:
            return None
        data = payload.model_dump(exclude_unset=True)
        for key, value in data.items():
            setattr(case, key, value)
        try:
            self._ensure_tag_colors(case.tags)
            self.db.commit()
            self.db.refresh(case)
            return case
        except Exception:
            self.db.rollback()
            raise

    def delete_case(
        self,
        case_id: str,
        business_id: str = DEFAULT_BUSINESS_ID,
    ) -> bool:
        from mua_platform.test_plans.models import TestPlan, TestPlanCase

        case = self.get_case(case_id, business_id)
        if case is None:
            return False
        if self.db.scalar(
            select(TestPlanCase.case_id)
            .join(TestPlan, TestPlan.id == TestPlanCase.plan_id)
            .where(
                TestPlanCase.case_id == case_id,
                TestPlan.deleted_at.is_(None),
            )
            .limit(1)
        ) is not None:
            raise ValueError("case_has_test_plans")
        active_statuses = (
            ExecutionStatus.SCRIPT_PENDING,
            ExecutionStatus.QUEUED,
            ExecutionStatus.RUNNING,
        )
        if self.db.scalar(
            select(Task.id)
            .where(
                Task.case_id == case_id,
                Task.execution_status.in_(active_statuses),
            )
            .limit(1)
        ) is not None:
            raise ValueError("case_has_tasks")
        case.deleted_at = datetime.now(UTC)
        self.db.commit()
        return True

    def list_tags(self, business_id: str = DEFAULT_BUSINESS_ID) -> list[str]:
        rows = self.db.scalars(
            select(TestCase.tags).where(
                TestCase.deleted_at.is_(None),
                TestCase.business_id == business_id,
            )
        ).all()
        tag_set: set[str] = set()
        for tags in rows:
            if isinstance(tags, list):
                tag_set.update(t for t in tags if isinstance(t, str))
        return sorted(tag_set)

    def list_modules(self, business_id: str = DEFAULT_BUSINESS_ID) -> list[str]:
        rows = self.db.scalars(
            select(TestCase.module)
            .where(
                TestCase.deleted_at.is_(None),
                TestCase.business_id == business_id,
                TestCase.module.is_not(None),
            )
            .distinct()
        ).all()
        return sorted(r for r in rows if isinstance(r, str))

    def list_creators(self, business_id: str = DEFAULT_BUSINESS_ID) -> list[str]:
        rows = self.db.scalars(
            select(TestCase.created_by)
            .where(
                TestCase.deleted_at.is_(None),
                TestCase.business_id == business_id,
                TestCase.created_by.is_not(None),
                TestCase.created_by != "",
            )
            .distinct()
            .order_by(TestCase.created_by)
        ).all()
        return [creator for creator in rows if isinstance(creator, str)]

    def _ensure_tag_colors(self, tags: list[str] | None) -> None:
        from mua_platform.test_plans.service import TagColorService

        TagColorService(self.db).ensure(tags or [])


def _parse_csv_rows(content: str) -> list[tuple[int, dict[str, str]]]:
    reader = csv.DictReader(StringIO(content))
    required = {"title", "module", "tags", "content_markdown"}
    if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
        raise ValueError("case_import_invalid_csv_header")
    return [
        (index, {key: value or "" for key, value in row.items() if key})
        for index, row in enumerate(reader, start=2)
    ]


def _parse_excel_rows(content: str) -> list[tuple[int, dict[str, str]]]:
    reader = csv.DictReader(StringIO(content), delimiter="\t")
    required = {"title", "module", "tags", "content_markdown"}
    if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
        raise ValueError("case_import_invalid_csv_header")
    return [
        (index, {key: value or "" for key, value in row.items() if key})
        for index, row in enumerate(reader, start=2)
    ]


def _parse_markdown_rows(content: str) -> list[tuple[int, dict[str, str]]]:
    rows: list[tuple[int, dict[str, str]]] = []
    for index, block in enumerate(content.split("---CASE---"), start=1):
        text = block.strip()
        if not text:
            continue
        meta: dict[str, str] = {}
        body = text
        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) >= 3:
                frontmatter = parts[1]
                body = parts[2].strip()
                for line in frontmatter.splitlines():
                    if ":" not in line:
                        continue
                    key, value = line.split(":", 1)
                    meta[key.strip()] = value.strip()
        rows.append(
            (
                index,
                {
                    "title": meta.get("title", ""),
                    "module": meta.get("module", ""),
                    "tags": _frontmatter_tags(meta.get("tags", "")),
                    "content_markdown": body,
                },
            )
        )
    return rows


def _parse_import_rows(import_format: str, content: str) -> list[tuple[int, dict[str, str]]]:
    if import_format == "csv":
        return _parse_csv_rows(content)
    if import_format == "excel":
        return _parse_excel_rows(content)
    if import_format == "markdown":
        return _parse_markdown_rows(content)
    raise ValueError("case_import_unsupported_format")


def _parse_import_file(
    filename: str,
    content: bytes,
    import_format: str,
) -> list[tuple[int, dict[str, str]]]:
    resolved_format = _resolve_import_file_format(filename, import_format)
    if resolved_format == "excel" and filename.lower().endswith(".xlsx"):
        return _parse_xlsx_rows(content)
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("case_import_invalid_encoding") from exc
    return _parse_import_rows(resolved_format, text)


def _resolve_import_file_format(filename: str, import_format: str) -> str:
    if import_format != "auto":
        if import_format in {"csv", "markdown", "excel"}:
            return import_format
        raise ValueError("case_import_unsupported_format")
    suffix = Path(filename).suffix.lower()
    if suffix == ".csv":
        return "csv"
    if suffix in {".md", ".markdown"}:
        return "markdown"
    if suffix in {".tsv", ".xls", ".xlsx"}:
        return "excel"
    raise ValueError("case_import_unsupported_format")


def _parse_xlsx_rows(content: bytes) -> list[tuple[int, dict[str, str]]]:
    try:
        with ZipFile(BytesIO(content)) as archive:
            shared_strings = _xlsx_shared_strings(archive)
            sheet_xml = archive.read("xl/worksheets/sheet1.xml")
    except (BadZipFile, KeyError) as exc:
        raise ValueError("case_import_parse_failed") from exc

    namespace = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    root = ET.fromstring(sheet_xml)
    parsed_rows: list[list[str]] = []
    for row in root.findall(".//x:sheetData/x:row", namespace):
        values_by_column: dict[int, str] = {}
        for cell in row.findall("x:c", namespace):
            ref = cell.attrib.get("r", "")
            column_index = _xlsx_column_index(ref)
            values_by_column[column_index] = _xlsx_cell_value(cell, shared_strings, namespace)
        if values_by_column:
            parsed_rows.append([
                values_by_column.get(index, "")
                for index in range(max(values_by_column) + 1)
            ])

    if not parsed_rows:
        raise ValueError("case_import_empty_file")
    headers = [header.strip() for header in parsed_rows[0]]
    required = {"title", "module", "tags", "content_markdown"}
    if not required.issubset(set(headers)):
        raise ValueError("case_import_invalid_csv_header")
    return [
        (index, dict(zip(headers, row, strict=False)))
        for index, row in enumerate(parsed_rows[1:], start=2)
    ]


def _xlsx_shared_strings(archive: ZipFile) -> list[str]:
    try:
        xml = archive.read("xl/sharedStrings.xml")
    except KeyError:
        return []
    namespace = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    root = ET.fromstring(xml)
    return [
        "".join(text.text or "" for text in item.findall(".//x:t", namespace))
        for item in root.findall("x:si", namespace)
    ]


def _xlsx_cell_value(cell: ET.Element, shared_strings: list[str], namespace: dict[str, str]) -> str:
    if cell.attrib.get("t") == "inlineStr":
        return "".join(text.text or "" for text in cell.findall(".//x:t", namespace))
    value = cell.find("x:v", namespace)
    if value is None or value.text is None:
        return ""
    if cell.attrib.get("t") == "s":
        index = int(value.text)
        return shared_strings[index] if 0 <= index < len(shared_strings) else ""
    return value.text


def _xlsx_column_index(ref: str) -> int:
    letters = "".join(char for char in ref if char.isalpha())
    index = 0
    for char in letters:
        index = index * 26 + (ord(char.upper()) - ord("A") + 1)
    return max(0, index - 1)


def _frontmatter_tags(value: str) -> str:
    stripped = value.strip()
    if stripped.startswith("[") and stripped.endswith("]"):
        return stripped[1:-1]
    return stripped


def _normalize_tags(value: str) -> list[str]:
    return list(
        dict.fromkeys(
            tag.strip()
            for tag in value.split(",")
            if tag.strip()
        )
    )


def _normalize_multiline(value: str) -> str:
    return value.replace("\\n", "\n")
