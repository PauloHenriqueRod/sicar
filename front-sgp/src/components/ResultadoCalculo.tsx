import { calculationTotal, formatCalculationValue, formatCurrency, unwrapCalculationResult } from '../utils/presentation';
import { CheckCircle, Download, ChevronRight } from 'lucide-react';
import { Button } from './ui';
import type { DataState } from '../types';
import { SectionHeader } from './SectionHeader';

interface ResultadoCalculoProps {
  data: DataState;
  isExporting: boolean;
  onExportPDF: () => void;
  onReset: () => void;
}

export function ResultadoCalculo({ data, isExporting, onExportPDF, onReset }: ResultadoCalculoProps) {
  const res = unwrapCalculationResult(data.resultado_calculo);
  const entries = Object.entries(res || {}).filter(([key]) => !['politica_arredondamento', 'nota_arredondamento'].includes(key));
  const grandTotalKey = calculationTotal(res);

  return (
    <div className="surface w-full p-5 sm:p-6 lg:p-8 flex flex-col text-ink">
      <SectionHeader title="Resultado do cálculo" icon={CheckCircle} />

      {grandTotalKey && (
        <div className="mb-8 rounded-lg bg-slate-50 p-6 sm:p-8 dark:bg-slate-800/50">
          <p className="field-label mb-3 capitalize">{grandTotalKey[0].replace(/_/g, ' ')}</p>
          <p className="financial-total break-words text-ink">
            {formatCurrency(grandTotalKey[1])}
          </p>
        </div>
      )}

      {typeof res.nota_arredondamento === 'string' && <p className="mb-6 text-sm text-muted">{res.nota_arredondamento}</p>}

      <div className="mb-8 flex flex-wrap gap-3">
        <Button type="button" onClick={onExportPDF} busy={isExporting} className="w-full cursor-pointer sm:w-auto">
          <Download className="w-5 h-5 shrink-0" aria-hidden="true" />
          {isExporting ? 'Gerando PDF...' : 'Baixar PDF'}
        </Button>
        <Button variant="secondary" type="button" onClick={onReset} disabled={isExporting} className="w-full cursor-pointer sm:w-auto">Novo cálculo</Button>
      </div>

      {entries.some(([key]) => key !== grandTotalKey?.[0]) && <details className="group rounded-lg border border-slate-200 p-4 sm:p-5 dark:border-slate-800">
        <summary className="disclosure-heading"><h3 className="subsection-title flex-1">Detalhamento do cálculo</h3><ChevronRight className="disclosure-chevron" aria-hidden="true" /></summary>
        <div className="mt-5 flex flex-col gap-4">
        {(() => {
          return entries.map(([k, v]: [string, unknown]) => {
            if (grandTotalKey && k === grandTotalKey[0]) return null;

            if (typeof v === 'object' && v !== null) {
              const renderNested = (obj: unknown): React.ReactNode => {
                if (Array.isArray(obj)) {
                  return obj.map((o, i) => (
                    <div key={i} className="mb-2 p-3 bg-slate-50 dark:bg-slate-900/20 rounded-lg border border-slate-100 dark:border-slate-800/30">
                      {renderNested(o)}
                    </div>
                  ));
                } else if (typeof obj === 'object' && obj !== null) {
                  return Object.entries(obj).map(([subK, subV]) => {
                    if (typeof subV === 'object' && subV !== null) {
                      return (
                        <div key={subK} className="mt-2 mb-3">
                          <p className="field-label capitalize mb-1">{subK.replace(/_/g, ' ')}</p>
                          <div className="pl-3 border-l-2 border-slate-200 dark:border-slate-700/30">{renderNested(subV)}</div>
                        </div>
                      );
                    }
                    return (
                      <div key={subK} className="flex flex-wrap justify-between items-center gap-x-4 gap-y-2 py-3 border-b border-slate-100 dark:border-slate-800/30 last:border-0">
                        <span className="text-muted text-sm capitalize">{subK.replace(/_/g, ' ')}</span>
                        <span className="data-value">
                          {formatCalculationValue(subK, subV)}
                        </span>
                      </div>
                    );
                  });
                }
                return <span className="text-ink text-sm">{String(obj)}</span>;
              };

              return (
                <details key={k} className="group bg-slate-50 dark:bg-slate-900/20 p-5 rounded-xl border border-slate-200 dark:border-slate-800">
                  <summary className="disclosure-heading capitalize"><span className="flex-1">{k.replace(/_/g, ' ')}</span><ChevronRight className="disclosure-chevron" aria-hidden="true" /></summary>
                  <div className="mt-4 border-t border-slate-200 pt-3 dark:border-slate-700">{renderNested(v)}</div>
                </details>
              );
            }
            return (
                <div key={k} className="bg-slate-50 dark:bg-slate-900/20 p-4 sm:p-5 rounded-xl border border-slate-100 dark:border-slate-800/30 flex flex-wrap justify-between items-center gap-x-5 gap-y-2">
                <span className="text-muted capitalize text-sm">{k.replace(/_/g, ' ')}:</span>
                <span className="data-value">{typeof v === 'number' ? (k.includes('dias') || k.includes('mes') || k.includes('ano') || k.includes('multiplicador') ? v : formatCurrency(v)) : String(v)}</span>
              </div>
            );
          });
        })()}

        </div>
      </details>}

    </div>
  );
}
