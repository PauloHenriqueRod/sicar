import type { ComponentProps } from 'react';
import { LoaderCircle } from 'lucide-react';

const variants = {
  primary: 'action-primary',
  secondary: 'action-secondary',
  quiet: 'action-quiet',
  icon: 'action-icon',
  link: 'action-link',
} as const;

export interface ButtonProps extends ComponentProps<'button'> {
  variant?: keyof typeof variants;
  busy?: boolean;
}

export function Button({ variant = 'primary', busy = false, disabled, type = 'button', className = '', children, ...props }: ButtonProps) {
  return (
    <button {...props} type={type} disabled={disabled || busy} aria-busy={busy || undefined} className={`${variants[variant]} ${className}`}>
      {busy && <LoaderCircle className="h-4 w-4 shrink-0 animate-spin motion-reduce:animate-none" aria-hidden="true" />}
      {children}
    </button>
  );
}
