export type ThemePreference = "light" | "dark" | "system";

const THEME_STORAGE_KEY = "mua-theme-preference";
const DARK_QUERY = "(prefers-color-scheme: dark)";
let stopSystemThemeListener: (() => void) | null = null;

function isThemePreference(value: string | null): value is ThemePreference {
  return value === "light" || value === "dark" || value === "system";
}

function systemTheme(): "light" | "dark" {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return "light";
  }
  return window.matchMedia(DARK_QUERY).matches ? "dark" : "light";
}

export function getStoredThemePreference(): ThemePreference {
  if (typeof window === "undefined") return "light";
  try {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
    return isThemePreference(stored) ? stored : "light";
  } catch {
    return "light";
  }
}

export function applyThemePreference(preference: ThemePreference) {
  const resolved = preference === "system" ? systemTheme() : preference;
  if (typeof document === "undefined") return;
  document.documentElement.dataset.themePreference = preference;
  document.documentElement.dataset.theme = resolved;
}

export function saveThemePreference(preference: ThemePreference) {
  window.localStorage.setItem(THEME_STORAGE_KEY, preference);
  applyThemePreference(preference);
  updateSystemThemeListener(preference);
}

function updateSystemThemeListener(preference: ThemePreference) {
  stopSystemThemeListener?.();
  stopSystemThemeListener = null;
  if (
    preference !== "system"
    || typeof window === "undefined"
    || typeof window.matchMedia !== "function"
  ) {
    return;
  }
  const query = window.matchMedia(DARK_QUERY);
  const handleChange = () => applyThemePreference("system");
  if (typeof query.addEventListener === "function") {
    query.addEventListener("change", handleChange);
    stopSystemThemeListener = () => query.removeEventListener("change", handleChange);
    return;
  }
  query.addListener(handleChange);
  stopSystemThemeListener = () => query.removeListener(handleChange);
}

export function initializeThemePreference() {
  const preference = getStoredThemePreference();
  applyThemePreference(preference);
  updateSystemThemeListener(preference);
}
