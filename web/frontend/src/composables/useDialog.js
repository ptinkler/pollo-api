import { reactive } from 'vue'

// App-wide replacements for the browser's confirm()/prompt() popups. One
// dialog is shown at a time (AppDialog.vue, mounted in App.vue); each call
// returns a promise.
//
//   const r = await confirmDialog({ title, message, confirmLabel, danger,
//                                   checkbox: { label, checked } })
//   if (!r) return              // cancelled
//   r.checked                   // the checkbox's state, when there is one
//
//   const name = await promptDialog({ title, label, value, confirmLabel })
//   if (name == null) return    // cancelled
export const dialog = reactive({
  open: false,
  kind: 'confirm',
  title: '',
  message: '',
  label: '',
  value: '',
  confirmLabel: 'OK',
  danger: false,
  checkbox: null, // { label, checked }
  resolve: null,
})

function show(kind, opts) {
  // A second dialog while one is open cancels the first
  dialog.resolve?.(null)
  return new Promise(resolve => {
    Object.assign(dialog, {
      open: true,
      kind,
      title: '',
      message: '',
      label: '',
      value: '',
      confirmLabel: 'OK',
      danger: false,
      checkbox: opts.checkbox ? { ...opts.checkbox } : null,
      ...opts,
      resolve,
    })
  })
}

export const confirmDialog = opts =>
  show('confirm', opts).then(r => (r ? { checked: !!dialog.checkbox?.checked } : false))
export const promptDialog = opts => show('prompt', opts)

// Called by AppDialog: the button pressed (or null for cancel)
export function settleDialog(result) {
  const resolve = dialog.resolve
  dialog.open = false
  dialog.resolve = null
  resolve?.(result)
}
