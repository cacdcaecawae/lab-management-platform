import type { Router } from 'vue-router'

// Keep only real internal application routes. Resolve once, then let the usual
// navigation guard enforce the destination's roles on the actual navigation.
// Not the workbench, where signing in goes anyway: someone who only typed the site's address sees the home page, not
// the sign-in sheet that a page to return to opens.
export function postAuthTarget(router: Router, candidate: unknown): string | undefined {
  if (typeof candidate !== 'string' || !candidate.startsWith('/') || candidate.startsWith('//') ||
      /[\\\u0000-\u001f\u007f]/.test(candidate)) return
  const target = router.resolve(candidate)
  if (!target.name || ['login', 'password', 'not-found', 'workbench'].includes(String(target.name))) return
  return target.fullPath
}
