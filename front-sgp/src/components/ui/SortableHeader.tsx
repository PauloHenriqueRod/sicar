import type { ReactNode } from 'react';
import { ArrowDown, ArrowUp, ArrowUpDown } from 'lucide-react';

interface SortableHeaderProps {
  children: ReactNode;
  direction?: 'asc' | 'desc';
  onSort: () => void;
  align?: 'left' | 'right';
}

export function SortableHeader({ children, direction, onSort, align = 'left' }: SortableHeaderProps) {
  const Icon = direction === 'asc' ? ArrowUp : direction === 'desc' ? ArrowDown : ArrowUpDown;
  return <th scope="col" aria-sort={direction === 'asc' ? 'ascending' : direction === 'desc' ? 'descending' : 'none'}>
    <button type="button" onClick={onSort} className={`flex w-full items-center gap-2 p-4 text-left font-semibold hover:bg-panel focus-visible:outline-2 focus-visible:outline-accent ${align === 'right' ? 'justify-end' : ''}`}>
      {children}<Icon className="h-3 w-3 shrink-0" aria-hidden="true" />
    </button>
  </th>;
}
