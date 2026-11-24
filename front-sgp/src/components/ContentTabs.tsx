import { useId } from 'react';
import type { ReactNode } from 'react';

interface ContentTabsProps<T extends string> {
  label: string;
  value: T;
  onChange: (value: T) => void;
  items: { id: T; label: string; content: ReactNode }[];
}

export function ContentTabs<T extends string>({ label, value, onChange, items }: ContentTabsProps<T>) {
  const prefix = useId();

  return (
    <div className="min-w-0">
      <div role="tablist" aria-label={label} className="mb-6 flex flex-wrap gap-2 border-b border-slate-200 pb-3 dark:border-slate-800">
        {items.map((item, index) => (
          <button
            key={item.id}
            id={`${prefix}-tab-${item.id}`}
            type="button"
            role="tab"
            aria-selected={value === item.id}
            aria-controls={`${prefix}-panel-${item.id}`}
            tabIndex={value === item.id ? 0 : -1}
            onClick={() => onChange(item.id)}
            onKeyDown={event => {
              let nextIndex: number;
              switch (event.key) {
                case 'ArrowRight': nextIndex = (index + 1) % items.length; break;
                case 'ArrowLeft': nextIndex = (index - 1 + items.length) % items.length; break;
                case 'Home': nextIndex = 0; break;
                case 'End': nextIndex = items.length - 1; break;
                default: return;
              }
              event.preventDefault();
              onChange(items[nextIndex].id);
              const tabs = event.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>('[role="tab"]');
              tabs?.[nextIndex].focus();
            }}
            className={`max-w-full cursor-pointer rounded-lg px-4 py-2.5 text-left text-sm font-semibold transition-colors ${value === item.id ? 'bg-accent text-on-accent' : 'text-muted hover:bg-panel'}`}
          >
            {item.label}
          </button>
        ))}
      </div>
      {items.map(item => (
        <div
          key={item.id}
          id={`${prefix}-panel-${item.id}`}
          role="tabpanel"
          aria-labelledby={`${prefix}-tab-${item.id}`}
          tabIndex={0}
          hidden={value !== item.id}
          className={value === item.id ? 'min-w-0' : 'hidden'}
        >
          {item.content}
        </div>
      ))}
    </div>
  );
}
