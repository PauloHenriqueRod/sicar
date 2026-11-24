import type { ReactNode } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { Button } from './Button';

interface PaginationProps {
  page: number;
  pageCount: number;
  onPageChange: (page: number) => void;
  label: string;
  summary?: ReactNode;
  disabled?: boolean;
}

export function Pagination({ page, pageCount, onPageChange, label, summary, disabled = false }: PaginationProps) {
  if (pageCount <= 1) return null;
  return (
    <nav aria-label={`Paginação ${label}`} className="mt-6 flex flex-wrap items-center justify-between gap-4 border-t border-outline pt-4">
      {summary && <p className="text-sm text-muted">{summary}</p>}
      <div className="flex max-w-full flex-wrap items-center gap-3">
        <Button variant="secondary" aria-label={`Página anterior ${label}`} disabled={disabled || page <= 1} onClick={() => onPageChange(Math.max(1, page - 1))} className="px-3"><ChevronLeft className="h-4 w-4" aria-hidden="true" /><span className="hidden sm:inline">Anterior</span></Button>
        <span aria-live="polite" aria-atomic="true" className="text-sm font-medium text-ink tabular-nums">Página {page} de {pageCount}</span>
        <Button variant="secondary" aria-label={`Próxima página ${label}`} disabled={disabled || page >= pageCount} onClick={() => onPageChange(Math.min(pageCount, page + 1))} className="px-3"><span className="hidden sm:inline">Próxima</span><ChevronRight className="h-4 w-4" aria-hidden="true" /></Button>
      </div>
    </nav>
  );
}
