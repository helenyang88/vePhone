import { useEffect, useRef } from "react";

import { SingleSelect } from "./single-select";

const PAGE_SIZE_OPTIONS = [
  { value: "10", label: "10 条 / 页" },
  { value: "20", label: "20 条 / 页" },
  { value: "50", label: "50 条 / 页" },
] as const;

export type PaginationControlsProps = {
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: 10 | 20 | 50) => void;
  showPageSize?: boolean;
};

function ChevronLeftIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="m15 18-6-6 6-6" />
    </svg>
  );
}

function ChevronRightIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="m9 18 6-6-6-6" />
    </svg>
  );
}

export function PaginationControls({
  page,
  pageSize,
  total,
  onPageChange,
  onPageSizeChange,
  showPageSize = true,
}: PaginationControlsProps) {
  const totalPages = Math.max(1, Math.ceil(Math.max(0, total) / pageSize));
  const effectivePage = Math.min(Math.max(1, page), totalPages);
  const lastCorrectionRef = useRef<string | null>(null);

  useEffect(() => {
    if (page === effectivePage) {
      lastCorrectionRef.current = null;
      return;
    }
    const correctionKey = `${page}:${effectivePage}:${totalPages}`;
    if (lastCorrectionRef.current === correctionKey) return;
    lastCorrectionRef.current = correctionKey;
    onPageChange(effectivePage);
  }, [effectivePage, onPageChange, page, totalPages]);

  return (
    <div className="pagination-controls" aria-label="分页">
      <span className="pagination-total">共 {Math.max(0, total)} 条</span>
      <div className="pagination-actions">
        <button
          type="button"
          className="page-button"
          aria-label="上一页"
          disabled={effectivePage <= 1}
          onClick={() => onPageChange(effectivePage - 1)}
        >
          <ChevronLeftIcon />
        </button>
        <span className="page-info">
          第 {effectivePage} / {totalPages} 页
        </span>
        <button
          type="button"
          className="page-button"
          aria-label="下一页"
          disabled={effectivePage >= totalPages}
          onClick={() => onPageChange(effectivePage + 1)}
        >
          <ChevronRightIcon />
        </button>
      </div>
      {showPageSize && (
        <SingleSelect
          label="每页条数"
          value={String(pageSize) as "10" | "20" | "50"}
          options={PAGE_SIZE_OPTIONS}
          onChange={(value) => {
            onPageSizeChange(Number(value) as 10 | 20 | 50);
          }}
          className="pagination-page-size"
        />
      )}
    </div>
  );
}
