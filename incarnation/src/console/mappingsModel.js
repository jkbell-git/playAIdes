// Pure helpers for the console — framework-agnostic so they're unit-testable
// without React/jsdom (vitest include is src/**/*.test.js).

/** Group discovered items by their HA domain. */
export function groupByDomain(items) {
  const groups = {};
  for (const it of items) {
    (groups[it.domain] ??= []).push(it);
  }
  return groups;
}

/** Immutably set a single-entity capability (e.g. say_target). */
export function setSingleMapping(state, capability, provider, entity) {
  return {
    ...state,
    mappings: { ...state.mappings, [capability]: { provider, entity } },
  };
}

/** Immutably set the pip slot to a CAMERA source (a discovered HA entity). */
export function setPipCameraSource(state, provider, entity) {
  return {
    ...state,
    mappings: { ...state.mappings, pip: { kind: 'camera', provider, entity } },
  };
}

/** Immutably set the pip slot to a URL source (operator-entered website/doc link). */
export function setPipUrlSource(state, url, label) {
  return {
    ...state,
    mappings: { ...state.mappings, pip: { kind: 'url', url, label } },
  };
}

/** Resolution: a url-kind source never goes stale; everything else (camera-kind
 *  pip, or a plain single-entity mapping) is resolved iff its entity still exists. */
export function isResolved(mapping, discoveredIds) {
  if (!mapping) return false;
  if (mapping.kind === 'url') return !!mapping.url;
  return discoveredIds.includes(mapping.entity);
}
