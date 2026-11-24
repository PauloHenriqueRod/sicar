import { useId } from 'react';
import type { ReactNode } from 'react';
import type { LucideIcon } from 'lucide-react';
import { SectionHeader } from '../SectionHeader';
import { ActionFeedback } from '../ActionFeedback';
import type { Feedback } from '../ActionFeedback';

interface PagePanelProps {
  title: string;
  icon: LucideIcon;
  description?: string;
  actions?: ReactNode;
  feedback?: Feedback | null;
  children: ReactNode;
}

/** Estrutura comum para páginas de consulta e gestão. */
export function PagePanel({ title, icon, description, actions, feedback, children }: PagePanelProps) {
  const titleId = useId();
  return (
    <section aria-labelledby={titleId} className="page-panel">
      <SectionHeader titleId={titleId} title={title} icon={icon} description={description} actions={actions} />
      {feedback !== undefined && <div className={feedback ? 'mb-6' : undefined}><ActionFeedback feedback={feedback} /></div>}
      {children}
    </section>
  );
}

export function FilterBar({ children }: { children: ReactNode }) {
  return <div role="group" aria-label="Filtros de consulta" className="filter-bar">{children}</div>;
}

/** A tabela preserva todas as colunas; a rolagem fica restrita a esta região. */
export function TableViewport({ label, children }: { label: string; children: ReactNode }) {
  return <div role="region" aria-label={label} tabIndex={0} className="table-viewport">{children}</div>;
}
