import { createContext, useCallback, useContext, useRef, useState } from 'react'
import type { ReactNode } from 'react'

type ConfirmOptions = {
  title?: string
  message: string
  confirmLabel?: string
  tone?: 'danger' | 'primary'
}

type ConfirmDialogContextValue = {
  confirm: (options: ConfirmOptions) => Promise<boolean>
}

const ConfirmDialogContext = createContext<ConfirmDialogContextValue | null>(null)

export function ConfirmDialogProvider({ children }: { children: ReactNode }) {
  const [options, setOptions] = useState<ConfirmOptions | null>(null)
  const resolver = useRef<((value: boolean) => void) | null>(null)

  const confirm = useCallback((nextOptions: ConfirmOptions) => new Promise<boolean>((resolve) => {
    resolver.current = resolve
    setOptions(nextOptions)
  }), [])

  const close = useCallback((value: boolean) => {
    resolver.current?.(value)
    resolver.current = null
    setOptions(null)
  }, [])

  return (
    <ConfirmDialogContext.Provider value={{ confirm }}>
      {children}
      {options && (
        <div className="ui-modal-backdrop" role="presentation" onMouseDown={() => close(false)}>
          <section
            aria-describedby="confirm-dialog-description"
            aria-labelledby="confirm-dialog-title"
            aria-modal="true"
            className="ui-confirm-dialog"
            role="dialog"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <h2 id="confirm-dialog-title">{options.title ?? 'Xác nhận thao tác'}</h2>
            <p id="confirm-dialog-description">{options.message}</p>
            <div className="ui-dialog-actions">
              <button autoFocus className="ui-button ui-button-secondary" type="button" onClick={() => close(false)}>Hủy</button>
              <button className={`ui-button ${options.tone === 'danger' ? 'ui-button-danger' : 'ui-button-primary'}`} type="button" onClick={() => close(true)}>
                {options.confirmLabel ?? 'Xác nhận'}
              </button>
            </div>
          </section>
        </div>
      )}
    </ConfirmDialogContext.Provider>
  )
}

export function useConfirmDialog() {
  const context = useContext(ConfirmDialogContext)
  if (!context) throw new Error('useConfirmDialog phải được dùng bên trong ConfirmDialogProvider')
  return context.confirm
}
