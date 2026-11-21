import { ref } from 'vue'

// The phone layout (DESIGN.md "手机"): screens up to 768px wide. Same breakpoint as the CSS.
const query = typeof window !== 'undefined' && window.matchMedia ? window.matchMedia('(max-width: 768px)') : null
export const phone = ref(query?.matches ?? false)
query?.addEventListener('change', (e) => (phone.value = e.matches))

// Detail / edit pages show their own back + title (PageHeader) in the card, so the phone top bar stays hidden there.
export const pageHeaders = ref(0)

// On a phone the list page's buttons (PageToolbar #actions) move into the top bar. Only one toolbar may own it: the
// page's first; toolbars further down (a tab's own, one in a dialog) keep their buttons where they are.
export const topBarOwner = ref<symbol | null>(null)

/** Writes each column's header onto its body cells (`data-label`) and marks empty cells (`data-empty`), so the phone
 *  styles can turn table rows into cards ("表头 值" lines) without a separate template per page. */
export function labelTableCells(root: ParentNode) {
  for (const table of root.querySelectorAll('.el-table')) {
    const heads = Array.from(table.querySelectorAll('.el-table__header-wrapper th.el-table__cell'), (th) => th.textContent?.trim() ?? '')
    for (const row of table.querySelectorAll('.el-table__body-wrapper tr.el-table__row')) {
      Array.from(row.children).forEach((cell, i) => {
        if (cell.getAttribute('data-label') !== heads[i]) cell.setAttribute('data-label', heads[i] ?? '')
        const empty = !cell.textContent?.trim() && !cell.querySelector('img, input, button, a, .el-checkbox, .el-icon, svg')
        cell.toggleAttribute('data-empty', empty)
      })
    }
  }
}
