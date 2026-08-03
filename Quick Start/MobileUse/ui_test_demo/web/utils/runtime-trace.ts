import type {
  RuntimeThreadStep,
  RuntimeToolCallResult,
} from "../api/types";

function stableValue(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(stableValue);
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value)
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([key, item]) => [key, stableValue(item)]),
    );
  }
  return value;
}

function stepKey(step: RuntimeThreadStep): string {
  return `${step.run_id ?? ""}:${step.step_id ?? ""}`;
}

function toolKey(tool: RuntimeToolCallResult): string {
  return JSON.stringify(stableValue(tool));
}

function mergeTools(
  previous: RuntimeToolCallResult[],
  incoming: RuntimeToolCallResult[],
): RuntimeToolCallResult[] {
  const seen = new Set(previous.map(toolKey));
  const appended = incoming.filter((tool) => {
    const key = toolKey(tool);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
  return [...previous, ...appended];
}

export function mergeRuntimeThreadSteps(
  previous: RuntimeThreadStep[],
  incoming: RuntimeThreadStep[],
): RuntimeThreadStep[] {
  const byKey = new Map(previous.map((step) => [stepKey(step), step]));
  const merged = [...previous];

  for (const nextStep of incoming) {
    const key = stepKey(nextStep);
    const current = byKey.get(key);
    if (!current) {
      merged.push(nextStep);
      byKey.set(key, nextStep);
      continue;
    }
    const updated = {
      ...current,
      ...nextStep,
      results: mergeTools(current.results, nextStep.results),
    };
    const index = merged.indexOf(current);
    merged[index] = updated;
    byKey.set(key, updated);
  }

  return merged;
}

export function runtimeToolCount(steps: RuntimeThreadStep[]): number {
  return steps.reduce((count, step) => count + step.results.length, 0);
}
