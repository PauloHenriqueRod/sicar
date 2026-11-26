import { SalaryReferenceReview } from './SalaryReferenceReview';
import { salaryContextKeys } from '../utils/salaryReferences';
import { useId } from 'react';
import { Button, TextField } from './ui';
import { FileText, ChevronRight, Calculator } from 'lucide-react';
import type { DataState } from '../types';
import { reviewField } from '../utils/reviewFields';
import { emptyPeriod } from '../utils/reviewData';
import { ReviewCollection } from './ReviewCollection';
import { PeriodApuracaoForm } from './PeriodApuracaoForm';
import { SubstituicaoForm } from './SubstituicaoForm';
import { RescisaoForm } from './RescisaoForm';
import { AbonoForm } from './AbonoForm';
import { ExerciciosForm } from './ExerciciosForm';
import { ExtractionReview } from './ExtractionReview';
import { docenteDestinationSource, docenteInitialBase, isMonthlyProgression } from '../utils/progressionReviewValidation';
import { type ExtractionReview as DocumentReview } from '../utils/documentExtraction';
import { ProgressionFinancialReview } from './ProgressionFinancialReview';
import { DocentePayrollReview } from './DocentePayrollReview';

interface RevisaoDadosFormProps {
  data: DataState;
  isCalculated: boolean;
  isUploading: boolean;
  onCalculate: () => void;
  handleChangeData: (path: (string | number)[], val: unknown) => void;
  fieldErrors?: Record<string, string>;
}

export function RevisaoDadosForm({ data, isCalculated, isUploading, onCalculate, handleChangeData, fieldErrors = {} }: RevisaoDadosFormProps) {
  const formId = useId();
  const entries = data.dados_extraidos ?? {};
  const monthly = isMonthlyProgression(entries);
  const review = entries.revisao_extracao as DocumentReview | undefined;
  const linkError = fieldErrors[JSON.stringify(['revisao_extracao', 'vinculo_calculo'])];
  const renderField = (value: unknown, path: (string | number)[]) => {
    const field = reviewField(path[path.length - 1], path);
    const id = `${formId}-${encodeURIComponent(JSON.stringify(path))}`;
    return (
      <TextField key={id}
          label={field.label}
          hint={field.help}
          error={fieldErrors[JSON.stringify(path)]}
          id={id}
          type="text"
          inputMode={field.inputMode}
          placeholder={field.placeholder}
          disabled={isUploading}
          value={value == null ? '' : String(value)}
          onChange={(e) => handleChangeData(path, e.target.value)}
      />
    );
  };

  const renderEditableObj = (obj: Record<string, unknown> | unknown, path: (string | number)[] = []): React.ReactNode => {
    if (Array.isArray(obj)) {
      const isFlow = path[0] === 'fluxo' || path[0] === 'fluxo_mensal';
      const editable = isFlow || path[0] === 'valores_anuais';
      return <div className="space-y-4">
        {obj.map((item, index) => <div key={index} className="form-section space-y-4 p-4 border border-outline rounded-lg">
          {typeof item === 'object' && item !== null ? <><p className="field-label">Período {index + 1}</p>{renderEditableObj(item, [...path, index])}</> : renderField(item, [...path, index])}
          {editable && <Button variant="quiet" disabled={isUploading} onClick={() => handleChangeData(path, obj.filter((_, i) => i !== index))}>Remover {isFlow ? 'período' : 'contribuição'} {index + 1}</Button>}
        </div>)}
        {editable && <Button variant="secondary" disabled={isUploading} onClick={() => handleChangeData(path, [...obj, isFlow ? emptyPeriod() : ''])}>Adicionar {isFlow ? 'período' : `contribuição de ${path[1]}`}</Button>}
      </div>;
    } else if (typeof obj === 'object' && obj !== null) {
      const collection = path.length === 1 ? path[0] : null;
      if (collection === 'valores_anuais' || collection === 'valores_mensais' || collection === 'valores_recebidos') {
        return <ReviewCollection kind={collection} value={obj as Record<string, unknown>} disabled={isUploading} onChange={value => handleChangeData(path, value)} renderEntry={(key, value) => Array.isArray(value) ? <><p className="field-label">Ano {key}</p>{renderEditableObj(value, [...path, key])}</> : renderField(value, [...path, key])} />;
      }
      if (Object.keys(obj).length === 0) return <p className="text-sm text-muted">Nenhum valor foi identificado neste grupo. Confira o documento de origem.</p>;
      return (
        <div className="form-grid">
          {Object.entries(obj).map(([k, v]) => {
            if (path.length === 0 && k === 'revisao_extracao') return <div key={k} className="col-span-full min-w-0"><ExtractionReview linkError={linkError} data={obj as Record<string, unknown>} disabled={isUploading} onChange={handleChangeData} /></div>;
            if (path.length === 0 && k === 'exercicios') return <div key={k} className="form-section"><ExerciciosForm value={v} onChange={handleChangeData} disabled={isUploading} fieldErrors={fieldErrors} /></div>;
            if (path.length === 0 && k === 'abono') return <div key={k} className="form-section"><AbonoForm value={v} onChange={handleChangeData} disabled={isUploading} fieldErrors={fieldErrors} /></div>;
            if (path.length === 0 && k === 'rescisao') return <div key={k} className="form-section"><RescisaoForm value={v} matricula={data.dados_extraidos?.matricula} onChange={handleChangeData} disabled={isUploading} fieldErrors={fieldErrors} /></div>;
            if (path.length === 0 && k === 'substituicao') return <div key={k} className="form-section"><SubstituicaoForm value={v} onChange={handleChangeData} disabled={isUploading} fieldErrors={fieldErrors} /></div>;
            if (path.length === 0 && k === 'apuracao') return <div key={k} className="form-section"><PeriodApuracaoForm value={v} onChange={handleChangeData} disabled={isUploading} fieldErrors={fieldErrors} /></div>;
            if (path.length === 0 && k === 'progressao') return <div key={k} className="form-section col-span-full min-w-0"><ProgressionFinancialReview data={obj as Record<string, unknown>} onChange={handleChangeData} disabled={isUploading} /><PeriodApuracaoForm value={v} onChange={handleChangeData} disabled={isUploading} fieldErrors={fieldErrors} progression /></div>;
            if (path.length === 0 && k === 'adicionais') return <div key={k} className="form-section"><PeriodApuracaoForm value={v} onChange={handleChangeData} disabled={isUploading} fieldErrors={fieldErrors} additional /></div>;
            if (path.length === 0 && (k === 'substitui_historico_id' || k === 'revisao_docente_detalhada')) return null;
            if (path.length === 0 && salaryContextKeys.includes(k)) return null;
            if (k === 'alertas_extracao') return Array.isArray(v) && v.length > 0 ? <div key={k} role="note" className="form-section feedback-warning rounded-lg p-4"><p className="field-label">Confira a extração</p><ul className="mt-2 list-disc pl-5">{v.map((message, index) => <li key={index}>{String(message)}</li>)}</ul></div> : null;
            if (typeof v === 'object' && v !== null) {
              const field = reviewField(k, [...path, k]);
              return (
                <details key={k} open className="form-section group p-4 sm:p-5 bg-panel/20 rounded-lg border border-slate-200 dark:border-slate-700">
                  <summary className="disclosure-heading"><span className="flex-1">{field.label}</span><ChevronRight className="disclosure-chevron" aria-hidden="true" /></summary>
                  {field.help && <p className="help-text mt-3">{field.help}</p>}
                  <div className="mt-5">{renderEditableObj(v, [...path, k])}</div>
                </details>
              );
            }
            return renderField(v, [...path, k]);
          })}
        </div>
      );
    }
    return String(obj);
  };

  return (
    <div className="surface w-full p-5 sm:p-6 lg:p-8 flex flex-col">
      <details open={!isCalculated} className="group">
        <summary className="disclosure-heading gap-3">
          <span className="section-icon" aria-hidden="true"><FileText className="h-5 w-5" /></span>
          <h2 className="section-title min-w-0 flex-1">{isCalculated ? 'Dados usados no cálculo' : 'Confira os dados do cálculo'}</h2>
          <ChevronRight className="disclosure-chevron" aria-hidden="true" />
        </summary>

        {!monthly && <p className="body-text mb-6 mt-4 text-muted">Confira os valores nos documentos e complete os campos em branco. Após uma correção, calcule novamente.</p>}


      <div className="mb-8">
        {monthly ? <div className="mt-5 space-y-6">
          <DocentePayrollReview data={entries} onChange={handleChangeData} disabled={isUploading} showErrors={!!fieldErrors[JSON.stringify(['progressao', 'bases_mensais_origem'])]} />
          <PeriodApuracaoForm value={entries.progressao} progression monthly originBase={docenteInitialBase(entries)} destinationSource={docenteDestinationSource(entries)} onChange={handleChangeData} disabled={isUploading} fieldErrors={fieldErrors}>
            <div className="form-grid">{renderField(entries.nome, ['nome'])}{renderField(entries.matricula, ['matricula'])}</div>
            {review?.aplicacoes.map((a, index) => {
              const source = review.documentos.find(d => d.id === a.documento_id)?.campos.find(f => f.id === a.campo_id);
              if (!source || source.campo === 'rubrica' || source.valor === a.valor_revisado) return null;
              return <TextField key={index} label={`Motivo da correção de ${source.campo.replaceAll('_', ' ')}`}
                hint={`Valor do documento: ${source.valor ?? 'ausente'} · Valor utilizado: ${a.valor_revisado}`}
                disabled={isUploading} value={a.justificativa} onChange={e => handleChangeData(['revisao_extracao', 'aplicacoes', index, 'justificativa'], e.target.value)} />;
            })}
            {!isCalculated && <Button variant="quiet" disabled={isUploading} onClick={() => handleChangeData(['revisao_docente_detalhada'], true)}>Usar apuração com eventos independentes</Button>}
          </PeriodApuracaoForm>
        </div> : <>
        {renderEditableObj(data.dados_extraidos)}
        <SalaryReferenceReview data={data.dados_extraidos ?? {}} disabled={isUploading} onChange={handleChangeData} />
        {(data.dados_extraidos?.adicionais || data.dados_extraidos?.progressao || data.dados_extraidos?.apuracao || data.dados_extraidos?.substituicao) != null && <details className="mt-6 text-sm"><summary>Vincular a um cálculo anterior (opcional)</summary><div className="mt-3"><TextField label="Histórico a substituir (opcional, somente revisão)" type="number" disabled={isUploading} value={String(data.dados_extraidos?.substitui_historico_id ?? '')} onChange={e => handleChangeData(['substitui_historico_id'], e.target.value)} /></div></details>}
        </>}
      </div>

      {monthly && !isCalculated && Object.keys(fieldErrors).length > 0 && <div role="alert" className="feedback-error rounded-lg p-3 mb-3">
        <strong>Pendências para calcular a progressão</strong>
        <ul className="list-disc ps-5">{[...new Set(Object.values(fieldErrors))].map(message => <li key={message}>{message}</li>)}</ul>
      </div>}
      {!isCalculated && (
        <Button
          onClick={onCalculate}
          busy={isUploading}
          disabled={isUploading || (!monthly && data.dados_extraidos?.revisao_extracao != null && (data.dados_extraidos.revisao_extracao as { confirmado?: boolean }).confirmado !== true) || ['apuracao', 'progressao', 'adicionais', 'substituicao', 'rescisao', 'abono', 'exercicios'].some(key => data.dados_extraidos?.[key] && (data.dados_extraidos[key] as { conferido_pelo_rh?: boolean }).conferido_pelo_rh !== true)}
          className="w-full mt-auto shrink-0 cursor-pointer"
        >
          {!isUploading && <Calculator className="w-5 h-5 shrink-0" aria-hidden="true" />}
          {isUploading ? 'Calculando...' : 'Confirmar e Calcular'}
        </Button>
      )}
      </details>
      {isCalculated && <p className="help-text mt-3">Abra para conferir ou corrigir os dados.</p>}
    </div>
  );
}
