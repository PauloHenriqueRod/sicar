import { Check } from 'lucide-react';

const steps = [
  { id: 'documentos', label: 'Documentos' },
  { id: 'revisao', label: 'Revisão' },
  { id: 'resultado', label: 'Resultado' },
] as const;

export function CalculationSteps({ current }: { current: typeof steps[number]['id'] }) {
  const currentIndex = steps.findIndex(step => step.id === current);
  return (
    <ol aria-label="Etapas do cálculo" className="progress-list gap-2 rounded-xl border border-slate-200 bg-white p-3 sm:gap-4 sm:p-4 dark:border-slate-800 dark:bg-slate-900">
      {steps.map((step, index) => (
        <li key={step.id} aria-current={step.id === current ? 'step' : undefined} className={`progress-step font-medium ${step.id === current ? 'text-accent-ink' : index < currentIndex ? 'text-success' : 'text-muted'}`}>
          <span aria-hidden="true" className={`grid h-7 w-7 shrink-0 place-items-center rounded-full ${step.id === current ? 'bg-accent text-on-accent' : index < currentIndex ? 'bg-success-soft' : 'bg-panel'}`}>{index < currentIndex ? <Check className="h-4 w-4" /> : index + 1}</span>
          <span className="min-w-0 max-w-full break-words">{step.label}</span>
          {index < currentIndex && <span className="sr-only">Etapa concluída</span>}
        </li>
      ))}
    </ol>
  );
}
