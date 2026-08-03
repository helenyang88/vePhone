import {
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type FocusEvent,
  type KeyboardEvent,
} from "react";

export type MultiSelectOption = {
  value: string;
  label: string;
  count?: number;
  foregroundColor: string;
  backgroundColor: string;
};

export type MultiSelectProps = {
  label: string;
  values: string[];
  options: readonly MultiSelectOption[];
  onChange: (values: string[]) => void;
  searchValue: string;
  onSearchChange: (value: string) => void;
  onConfirm?: (values: string[]) => void;
  className?: string;
};

function ChevronIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="m7 10 5 5 5-5" />
    </svg>
  );
}

function RoundedCheckIcon() {
  return (
    <svg className="multi-select-check" viewBox="0 0 24 24" aria-hidden="true">
      <path
        d="m5 12 4 4L19 6"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function MultiSelect({
  label,
  values,
  options,
  onChange,
  searchValue,
  onSearchChange,
  onConfirm,
  className = "",
}: MultiSelectProps) {
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const [draftValues, setDraftValues] = useState(values);
  const activeIndexRef = useRef(0);
  const draftValuesRef = useRef(values);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const listboxId = useId();
  const selected = new Set(draftValues);
  const activeOptionId = open && options[activeIndex]
    ? `${listboxId}-option-${activeIndex}`
    : undefined;

  useLayoutEffect(() => {
    const next = [...values];
    draftValuesRef.current = next;
    setDraftValues(next);
  }, [values]);

  useEffect(() => {
    if (!open) return;

    function closeOnOutsideClick(event: MouseEvent) {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    }

    document.addEventListener("mousedown", closeOnOutsideClick);
    return () => document.removeEventListener("mousedown", closeOnOutsideClick);
  }, [open]);

  useEffect(() => {
    const next = Math.max(
      0,
      Math.min(activeIndexRef.current, options.length - 1),
    );
    activeIndexRef.current = next;
    setActiveIndex(next);
  }, [options.length]);

  function openMenu() {
    activeIndexRef.current = 0;
    setActiveIndex(0);
    setOpen(true);
  }

  function closeMenu({ restoreFocus = true } = {}) {
    setOpen(false);
    if (restoreFocus) {
      triggerRef.current?.focus();
    }
  }

  function toggle(value: string) {
    const current = draftValuesRef.current;
    const next = current.includes(value)
      ? current.filter((item) => item !== value)
      : [...current, value];
    draftValuesRef.current = next;
    setDraftValues(next);
    onChange(next);
  }

  function moveActiveOption(direction: 1 | -1) {
    if (options.length === 0) return;
    const next = (
      activeIndexRef.current
      + direction
      + options.length
    ) % options.length;
    activeIndexRef.current = next;
    setActiveIndex(next);
  }

  function toggleActiveOption() {
    const option = options[activeIndexRef.current];
    if (option) {
      toggle(option.value);
    }
  }

  function handleBlur(event: FocusEvent<HTMLDivElement>) {
    if (!event.currentTarget.contains(event.relatedTarget)) {
      closeMenu({ restoreFocus: false });
    }
  }

  function handleRootKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape" && open) {
      event.preventDefault();
      event.stopPropagation();
      closeMenu();
    }
  }

  function handleKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (!open) {
        openMenu();
        return;
      }
      moveActiveOption(event.key === "ArrowDown" ? 1 : -1);
      return;
    }

    if (
      event.key === "Enter"
      || event.key === " "
      || event.key === "Space"
    ) {
      event.preventDefault();
      if (!open) {
        openMenu();
        return;
      }
      toggleActiveOption();
    }
  }

  function handleSearchKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      moveActiveOption(event.key === "ArrowDown" ? 1 : -1);
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      toggleActiveOption();
    }
  }

  return (
    <div
      ref={rootRef}
      className={`single-select multi-select ${className}`.trim()}
      onBlur={handleBlur}
      onKeyDownCapture={handleRootKeyDown}
    >
      <button
        ref={triggerRef}
        type="button"
        role="combobox"
        aria-label={label}
        aria-expanded={open}
        aria-controls={listboxId}
        aria-activedescendant={activeOptionId}
        className={`single-select-trigger multi-select-trigger${open ? " open" : ""}`}
        onClick={() => {
          if (open) {
            closeMenu();
          } else {
            openMenu();
          }
        }}
        onKeyDown={handleKeyDown}
      >
        <span>
          {draftValues.length
            ? `标签（${draftValues.length}）`
            : "全部标签"}
        </span>
        <ChevronIcon />
      </button>

      {open && (
        <div className="single-select-menu multi-select-menu">
          <label className="multi-select-search">
            <span className="sr-only">搜索标签</span>
            <input
              type="search"
              name="tag_search"
              autoComplete="off"
              aria-label="搜索标签"
              aria-controls={listboxId}
              aria-activedescendant={activeOptionId}
              placeholder="搜索标签"
              value={searchValue}
              onChange={(event) => onSearchChange(event.target.value)}
              onKeyDown={handleSearchKeyDown}
            />
          </label>
          <div
            id={listboxId}
            role="listbox"
            aria-label={`${label}选项`}
            aria-multiselectable="true"
            className="multi-select-options"
          >
            {options.length === 0 ? (
              <div className="multi-select-empty">暂无匹配标签</div>
            ) : (
              options.map((option, index) => {
                const isSelected = selected.has(option.value);
                return (
                  <button
                    key={option.value}
                    id={`${listboxId}-option-${index}`}
                    type="button"
                    role="option"
                    tabIndex={-1}
                    aria-selected={isSelected}
                    className={[
                      "single-select-option",
                      "multi-select-option",
                      isSelected ? "selected" : "",
                      index === activeIndex ? "active" : "",
                    ].filter(Boolean).join(" ")}
                    style={isSelected
                      ? {
                          border: 0,
                          boxShadow: "none",
                          color: option.foregroundColor,
                          backgroundColor: option.backgroundColor,
                        }
                      : undefined}
                    onMouseEnter={() => {
                      activeIndexRef.current = index;
                      setActiveIndex(index);
                    }}
                    onClick={() => toggle(option.value)}
                  >
                    <span className="multi-select-option-label">
                      <span>{option.label}</span>
                      {option.count !== undefined && (
                        <span className="multi-select-option-count">
                          {option.count}
                        </span>
                      )}
                    </span>
                    {isSelected && <RoundedCheckIcon />}
                  </button>
                );
              })
            )}
          </div>
          {onConfirm && (
            <div className="multi-select-footer">
              <button
                type="button"
                className="multi-select-confirm"
                aria-label="确认标签选择"
                onClick={() => {
                  onConfirm(draftValuesRef.current);
                  closeMenu();
                }}
              >
                确定
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
