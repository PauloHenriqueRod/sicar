import { useId } from 'react';
import type { ComponentProps, ReactNode } from 'react';

export interface TextFieldProps extends Omit<ComponentProps<'input'>, 'children'> {
  label: string;
  hint?: string;
  error?: string;
  trailing?: ReactNode;
}

export function TextField({ id, label, hint, error, trailing, className = '', ...props }: TextFieldProps) {
  const generatedId = useId();
  const fieldId = id || generatedId;
  const describedBy = [props['aria-describedby'], hint && `${fieldId}-hint`, error && `${fieldId}-error`].filter(Boolean).join(' ') || undefined;
  return (
    <div className="flex min-w-0 flex-col gap-2.5">
      <label htmlFor={fieldId} className="field-label">{label}</label>
      <div className="relative">
        <input {...props} id={fieldId} aria-describedby={describedBy} aria-invalid={error ? true : props['aria-invalid']} className={`field-control text-field ${trailing ? 'pr-14' : ''} ${error ? 'border-danger' : ''} ${className}`} />
        {trailing && <div className="absolute inset-y-0 right-1 flex items-center">{trailing}</div>}
      </div>
      {hint && <p id={`${fieldId}-hint`} className="help-text">{hint}</p>}
      {error && <p id={`${fieldId}-error`} className="help-text text-danger">{error}</p>}
    </div>
  );
}
