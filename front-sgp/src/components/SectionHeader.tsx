import type { ReactNode } from 'react';
import type { LucideIcon } from 'lucide-react';

interface SectionHeaderProps {
  titleId?: string;
  title: string;
  icon: LucideIcon;
  description?: string;
  actions?: ReactNode;
}

export function SectionHeader({ titleId, title, icon: Icon, description, actions }: SectionHeaderProps) {
  return (
    <div className="section-header">
      <div className="flex min-w-0 flex-1 basis-56 items-start gap-3">
        <span className="section-icon" aria-hidden="true"><Icon className="h-5 w-5" /></span>
        <div className="min-w-0">
          <h2 id={titleId} className="section-title">{title}</h2>
          {description && <p className="body-text mt-2 text-muted">{description}</p>}
        </div>
      </div>
      {actions && <div className="section-header-actions">{actions}</div>}
    </div>
  );
}
