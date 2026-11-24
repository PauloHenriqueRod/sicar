import { useId } from 'react';
import type { ComponentProps } from 'react';

export interface SelectFieldProps extends ComponentProps<'select'> {
  label: string;
  hint?: string;
  error?: string;
}

export function SelectField({ id, label, hint, error, className = '', children, ...props }: SelectFieldProps) {
  const generatedId = useId();
  const fieldId = id || generatedId;
  const describedBy = [props['aria-describedby'], hint && `${fieldId}-hint`, error && `${fieldId}-error`].filter(Boolean).join(' ') || undefined;
  return (
    <div className="flex min-w-0 flex-col gap-2.5">
      <label htmlFor={fieldId} className="field-label">{label}</label>
      <select {...props} id={fieldId} aria-describedby={describedBy} aria-invalid={error ? true : props['aria-invalid']} className={`field-control text-field ${error ? 'border-danger' : ''} ${className}`}>{children}</select>
      {hint && <p id={`${fieldId}-hint`} className="help-text">{hint}</p>}
      {error && <p id={`${fieldId}-error`} className="help-text text-danger">{error}</p>}
    </div>
  );
}
