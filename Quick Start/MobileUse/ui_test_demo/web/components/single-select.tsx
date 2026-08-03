import {
  useEffect,
  useId,
  useRef,
  useState,
  type FocusEvent,
  type KeyboardEvent,
} from "react";

export type SelectOption<T extends string> = {
  value: T;
  label: string;
};

export type SingleSelectProps<T extends string> = {
  label: string;
  value: T;
  options: readonly SelectOption<T>[];
  onChange: (value: T) => void;
  name?: string;
  disabled?: boolean;
  className?: string;
  searchValue?: string;
  onSearchChange?: (value: string) => void;
  searchLabel?: string;
  emptyText?: string;
};

export function SingleSelect<T extends string>({
  label,
  value,
  options,
  onChange,
  name,
  disabled = false,
  className = "",
  searchValue,
  onSearchChange,
  searchLabel = "搜索选项",
  emptyText = "暂无匹配选项",
}: SingleSelectProps<T>) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const listboxId = useId();
  const selectedIndex = Math.max(
    0,
    options.findIndex((option) => option.value === value),
  );
  const [activeIndex, setActiveIndex] = useState(selectedIndex);
  const selected = options[selectedIndex];
  const activeOptionId = open && options[activeIndex]
    ? `${listboxId}-option-${activeIndex}`
    : undefined;

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
    setActiveIndex((current) =>
      Math.max(0, Math.min(current, options.length - 1))
    );
  }, [options.length]);

  function openMenu() {
    setActiveIndex(selectedIndex);
    setOpen(true);
  }

  function closeMenu() {
    setOpen(false);
    triggerRef.current?.focus();
  }

  function handleBlur(event: FocusEvent<HTMLDivElement>) {
    if (!event.currentTarget.contains(event.relatedTarget)) {
      setOpen(false);
    }
  }

  function selectActiveOption() {
    const option = options[activeIndex];
    if (!option) return;
    onChange(option.value);
    closeMenu();
  }

  function moveActiveOption(direction: 1 | -1) {
    setActiveIndex((current) =>
      options.length > 0
        ? (current + direction + options.length) % options.length
        : current
    );
  }

  function handleKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
    if (event.key === "Escape") {
      event.preventDefault();
      closeMenu();
      return;
    }

    if (event.key === "ArrowDown") {
      event.preventDefault();
      if (!open) {
        openMenu();
        return;
      }
      moveActiveOption(1);
      return;
    }

    if (event.key === "ArrowUp") {
      event.preventDefault();
      if (!open) {
        openMenu();
        return;
      }
      moveActiveOption(-1);
      return;
    }

    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      if (open) {
        selectActiveOption();
      } else {
        openMenu();
      }
    }
  }

  function handleSearchKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Escape") {
      event.preventDefault();
      closeMenu();
      return;
    }
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      moveActiveOption(event.key === "ArrowDown" ? 1 : -1);
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      selectActiveOption();
    }
  }

  return (
    <div
      className={`single-select ${className}`.trim()}
      ref={rootRef}
      onBlur={handleBlur}
    >
      <button
        ref={triggerRef}
        type="button"
        name={name}
        disabled={disabled}
        role="combobox"
        aria-label={label}
        aria-expanded={open}
        aria-controls={listboxId}
        aria-activedescendant={activeOptionId}
        className={`single-select-trigger${open ? " open" : ""}`}
        onClick={() => {
          if (disabled) return;
          if (open) {
            closeMenu();
          } else {
            openMenu();
          }
        }}
        onKeyDown={handleKeyDown}
      >
        <span>{selected?.label ?? ""}</span>
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="m7 10 5 5 5-5" />
        </svg>
      </button>
      {open && (
        <div className="single-select-menu">
          {searchValue !== undefined && onSearchChange && (
            <label className="single-select-search">
              <span className="sr-only">{searchLabel}</span>
              <input
                type="search"
                name={`${listboxId}-search`}
                autoComplete="off"
                aria-label={searchLabel}
                aria-controls={listboxId}
                aria-activedescendant={activeOptionId}
                placeholder={`${searchLabel}…`}
                value={searchValue}
                onChange={(event) => onSearchChange(event.target.value)}
                onKeyDown={handleSearchKeyDown}
              />
            </label>
          )}
          <div
            id={listboxId}
            role="listbox"
            aria-label={`${label}选项`}
            className="single-select-option-list"
          >
            {options.length === 0 ? (
              <div className="single-select-empty">{emptyText}</div>
            ) : options.map((option, index) => (
              <button
                key={option.value}
                id={`${listboxId}-option-${index}`}
                type="button"
                role="option"
                tabIndex={-1}
                aria-selected={option.value === value}
                className={[
                  "single-select-option",
                  option.value === value ? "selected" : "",
                  index === activeIndex ? "active" : "",
                ].filter(Boolean).join(" ")}
                onMouseEnter={() => setActiveIndex(index)}
                onClick={() => {
                  onChange(option.value);
                  closeMenu();
                }}
              >
                <span>{option.label}</span>
                {option.value === value && <span aria-hidden="true">✓</span>}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
