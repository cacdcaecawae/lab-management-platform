import type { RouteLocationNormalizedLoaded, RouteLocationRaw, Router } from 'vue-router'

// Transient one-shot intent: browser history/back and ordinary links never inherit it.
const replacements = new WeakMap<Router, { from: RouteLocationNormalizedLoaded; to: string }>()

export async function replaceSavedEditor(router: Router, from: RouteLocationNormalizedLoaded, target: RouteLocationRaw) {
  if (router.currentRoute.value !== from) return
  const change = { from, to: router.resolve(target).fullPath }
  replacements.set(router, change)
  try {
    return await router.replace(target)
  } finally {
    if (replacements.get(router) === change) replacements.delete(router)
  }
}

export function isSavedEditorReplacement(router: Router | undefined, from: RouteLocationNormalizedLoaded, to: RouteLocationNormalizedLoaded) {
  const change = router && replacements.get(router)
  return change?.from === from && change.to === to.fullPath
}

export function consumeSavedEditorReplacement(router: Router, from: RouteLocationNormalizedLoaded, to: RouteLocationNormalizedLoaded) {
  if (!isSavedEditorReplacement(router, from, to)) return false
  replacements.delete(router)
  return true
}
