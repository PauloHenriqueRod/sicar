import { useEffect, useId, useRef } from 'react';
import type { ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';
import { Button } from './Button';

interface ModalProps {
  title: string;
  description?: string;
  onClose: () => void;
  busy?: boolean;
  size?: 'small' | 'medium';
  children: ReactNode;
}

const focusableSelector = 'button:not(:disabled), input:not(:disabled):not([type="hidden"]), select:not(:disabled), textarea:not(:disabled), a[href], [tabindex="0"]';

export function Modal({ title, description, onClose, busy = false, size = 'small', children }: ModalProps) {
  const titleId = useId();
  const backdropRef = useRef<HTMLDivElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const previousOverflow = document.body.style.overflow;
    const siblings = Array.from(document.body.children).filter((element): element is HTMLElement => element instanceof HTMLElement && element !== backdropRef.current);
    const inertStates = siblings.map(element => ({ element, inert: element.inert }));
    siblings.forEach(element => { element.inert = true; });
    document.body.style.overflow = 'hidden';
    const firstField = dialogRef.current?.querySelector<HTMLElement>('input:not(:disabled), select:not(:disabled), textarea:not(:disabled)');
    (firstField || dialogRef.current)?.focus();
    return () => {
      inertStates.forEach(({ element, inert }) => { element.inert = inert; });
      document.body.style.overflow = previousOverflow;
      if (previousFocus?.isConnected) previousFocus.focus();
    };
  }, []);

  useEffect(() => {
    if (!dialogRef.current?.contains(document.activeElement)) dialogRef.current?.focus();
  }, [children]);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        if (!busy) onClose();
      } else if (event.key === 'Tab') {
        const controls = Array.from(dialogRef.current?.querySelectorAll<HTMLElement>(focusableSelector) || [])
          .filter(element => !element.closest('[hidden]'))
          .sort((first, second) => first.compareDocumentPosition(second) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1);
        const first = controls[0];
        const last = controls[controls.length - 1];
        if (!first) {
          event.preventDefault();
          dialogRef.current?.focus();
        } else if (event.shiftKey && (document.activeElement === first || !controls.includes(document.activeElement as HTMLElement))) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && (document.activeElement === last || !controls.includes(document.activeElement as HTMLElement))) {
          event.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [busy, onClose]);

  return createPortal(
    <div ref={backdropRef} className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/50 p-4">
      <div ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby={titleId} aria-describedby={description ? `${titleId}-description` : undefined} aria-busy={busy || undefined} tabIndex={-1} className={`surface max-h-[calc(100dvh-2rem)] w-full overflow-y-auto shadow-lg ${size === 'medium' ? 'max-w-lg' : 'max-w-md'}`}>
        <div className="flex items-start justify-between gap-4 border-b border-outline p-6">
          <div className="min-w-0"><h2 id={titleId} className="subsection-title">{title}</h2>{description && <p id={`${titleId}-description`} className="help-text mt-1">{description}</p>}</div>
          <Button variant="icon" aria-label="Fechar janela" disabled={busy} onClick={onClose}><X className="h-5 w-5" aria-hidden="true" /></Button>
        </div>
        {children}
      </div>
    </div>, document.body,
  );
}
