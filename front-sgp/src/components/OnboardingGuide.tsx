import { useEffect, useId, useRef, useState } from 'react';
import { Button } from './ui';
import { ArrowLeft, ArrowRight } from 'lucide-react';

const steps = [
  {
    label: 'Documentos',
    title: 'Prepare os documentos',
    description: 'Escolha o cálculo e anexe os PDFs nas seções correspondentes.',
    tips: [
      'Fichas financeiras: matrícula, remuneração e rubricas.',
      'Atos ou portarias: datas, concessões e períodos.',
      'Atenda um servidor e vínculo por cálculo. Os anexos são opcionais.',
    ],
  },
  {
    label: 'Conferência',
    title: 'Confira antes de calcular',
    description: 'Revise os dados e preencha os campos em branco.',
    tips: [
      'Confira servidor, valores, mês e ano nos documentos.',
      'Se corrigir os dados após o resultado, calcule novamente.',
    ],
  },
  {
    label: 'Resultado',
    title: 'Guarde o resultado',
    description: 'Confira o resultado e baixe o PDF.',
    tips: [
      'Baixe o PDF do cálculo revisado.',
      'Consulte os registros em Processos calculados.',
    ],
  },
];

interface OnboardingGuideProps {
  userRole: string | null;
  hasActiveCalculation: boolean;
  onDismiss: () => void;
  onStart: () => void;
  focusOnOpen?: boolean;
}

export function OnboardingGuide({ userRole, hasActiveCalculation, onDismiss, onStart, focusOnOpen = false }: OnboardingGuideProps) {
  const [current, setCurrent] = useState(0);
  const titleId = useId();
  const headingRef = useRef<HTMLHeadingElement>(null);
  const step = steps[current];
  const isLast = current === steps.length - 1;
  const isManager = userRole === 'admin' || userRole === 'dev';

  useEffect(() => {
    if (focusOnOpen || current > 0) headingRef.current?.focus();
  }, [current, focusOnOpen]);

  const move = (index: number) => {
    setCurrent(index);
    // Também direciona o foco ao voltar para a primeira etapa.
    headingRef.current?.focus();
  };

  return (
    <section aria-labelledby={titleId} className="surface p-6 sm:p-8">
      <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 id={titleId} className="section-title">Primeiros passos no SICAR</h2>
          <p className="help-text mt-2">Reabra este guia pelo botão Guia rápido.</p>
        </div>
        <button type="button" onClick={onDismiss} className="rounded-lg px-3 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800">Pular guia</button>
      </div>

      <ol aria-label="Etapas do guia" className="progress-list mb-6 gap-3 border-b border-slate-200 pb-5 dark:border-slate-800">
        {steps.map((item, index) => <li key={item.label} aria-current={index === current ? 'step' : undefined} className={`progress-step ${index === current ? 'font-semibold text-accent-ink' : 'text-muted'}`}>
          <span aria-hidden="true" className={`grid h-7 w-7 shrink-0 place-items-center rounded-full ${index === current ? 'bg-accent text-on-accent' : 'bg-panel'}`}>{index + 1}</span>
          <span className="min-w-0 max-w-full break-words">{item.label}</span>
        </li>)}
      </ol>

      <div className="max-w-3xl" aria-live="polite" aria-atomic="true">
        <p className="caption-text mb-2">Etapa {current + 1} de {steps.length}</p>
        <h3 ref={headingRef} tabIndex={-1} className="subsection-title mb-3 rounded focus-visible:outline-2 focus-visible:outline-blue-600 focus-visible:outline-offset-4">{step.title}</h3>
        <p className="body-text text-muted">{step.description}</p>
        <ul className="help-text mt-4 list-disc pl-5 space-y-2">
          {step.tips.map(tip => <li key={tip}>{tip}</li>)}
        </ul>
        {isLast && isManager && <p className="help-text mt-4">Na área Administração, consulte tabelas remuneratórias e usuários.</p>}
      </div>

      <div className="mt-6 flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 pt-5 dark:border-slate-800">
        <Button variant="secondary" disabled={current === 0} onClick={() => move(current - 1)}><ArrowLeft aria-hidden="true" className="h-4 w-4" />Voltar</Button>
        <Button type="button" onClick={isLast ? onStart : () => move(current + 1)} className="text-sm">
          {isLast ? hasActiveCalculation ? 'Retomar cálculo' : 'Começar cálculo' : 'Próxima etapa'}<ArrowRight aria-hidden="true" className="h-4 w-4" />
        </Button>
      </div>
    </section>
  );
}
