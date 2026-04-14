import { computed, type MaybeRefOrGetter, toValue } from "vue";
import { normalizeTaskTreeHealth } from "./taskTreeFeedback";

export function useTaskTreeHealth(source: MaybeRefOrGetter<unknown>) {
  return computed(() => normalizeTaskTreeHealth(toValue(source)));
}
