import { nextTick, onBeforeUnmount, onDeactivated, onMounted, watch } from 'vue'

export function useDialog(isOpen, close, focusSelector) {
  let returnFocus = null

  watch(isOpen, async (open) => {
    if (open) {
      returnFocus = document.activeElement
      document.body.style.overflow = 'hidden'
      await nextTick()
      if (isOpen.value) document.querySelector(focusSelector)?.focus()
    } else {
      document.body.style.overflow = ''
      await nextTick()
      returnFocus?.focus()
      returnFocus = null
    }
  })

  function keyHandler(event) {
    if (!isOpen.value) return
    if (event.key === 'Escape') close()
    if (event.key !== 'Tab') return
    const dialog = document.querySelector('[role="dialog"]')
    const controls = dialog?.querySelectorAll(
      'button:not(:disabled), a[href], input, select, textarea, [tabindex="0"]',
    )
    if (!controls?.length) return
    const first = controls[0],
      last = controls[controls.length - 1]
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault()
      last.focus()
    }
    if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault()
      first.focus()
    }
  }

  onMounted(() => document.addEventListener('keydown', keyHandler))
  onDeactivated(() => {
    if (isOpen.value) close()
  })
  onBeforeUnmount(() => {
    document.removeEventListener('keydown', keyHandler)
    if (isOpen.value) document.body.style.overflow = ''
  })
}
