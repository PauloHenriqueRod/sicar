import { useRef, useState } from 'react';
import { Button, SelectField, TextField } from './ui';
import { SalaryPositionFields } from './SalaryPositionFields';
import { emptySalaryPosition } from '../utils/salaryReferences';
import type { SalaryPosition } from '../utils/salaryReferences';
import { emptyRescisaoBase, emptyRescisaoPayment, serializeRescisaoPlan } from '../utils/rescisaoReview';
import { apiBaseUrl } from '../utils/api';

type Obj = Record<string, unknown>;
type Path = (string | number)[];
const obj = (value: unknown): Obj => value && typeof value === 'object' && !Array.isArray(value) ? value as Obj : {};

export function RescisaoForm({ value, matricula, onChange, disabled, fieldErrors = {} }: { value: unknown; matricula: unknown; onChange: (path: Path, value: unknown) => void; disabled: boolean; fieldErrors?: Record<string, string> }) {
  const root = obj(value);
  const [preview, setPreview] = useState<Obj | null>(null);
  const [status, setStatus] = useState('');
  const [loading, setLoading] = useState(false);
  const version = useRef(0);
  const get = (path: Path): unknown => {
    const value = path.reduce<unknown>((v, key) => Array.isArray(v) ? v[Number(key)] : obj(v)[key], root);
    if (path.at(-1) === 'modo') {
      const parent = path.slice(0, -1).reduce<unknown>((v, key) => Array.isArray(v) ? v[Number(key)] : obj(v)[key], root);
      return obj(parent).referencia_salarial ? 'TABELA' : 'MANUAL';
    }
    return value;
  };
  const set = (path: Path, value: unknown) => {
    const update = (current: unknown, keys: Path): unknown => {
      if (!keys.length) return value;
      const [key, ...rest] = keys;
      if (Array.isArray(current)) { const next = [...current]; next[Number(key)] = update(next[Number(key)], rest); return next; }
      return { ...obj(current), [key]: update(obj(current)[key], rest) };
    };
    const next = obj(update(root, path));
    if (path[0] !== 'conferido_pelo_rh') next.conferido_pelo_rh = false;
    if (path[0] === 'regra' && path.at(-1) !== 'confirmada') next.regra = { ...obj(next.regra), confirmada: false };
    setPreview(null); setStatus(''); setLoading(false);
    onChange(['rescisao'], next);
  };
  const text = (path: Path, label: string, type = 'text') => <TextField key={JSON.stringify(path)} label={label} type={type} disabled={disabled} error={fieldErrors[JSON.stringify(['rescisao', ...path])]} value={String(get(path) ?? '')} onChange={e => set(path, e.target.value)} />;
  const select = (path: Path, label: string, choices: Obj, change?: (value: string) => void) => <SelectField label={label} disabled={disabled} value={String(get(path) ?? '')} onChange={e => change ? change(e.target.value) : set(path, e.target.value)}><option value="">Selecione</option>{Object.entries(choices).map(([key, label]) => <option key={key} value={key}>{String(label)}</option>)}</SelectField>;
  const check = (path: Path, label: string) => <label className="flex gap-2"><input type="checkbox" disabled={disabled} checked={get(path) === true} onChange={e => set(path, e.target.checked)} />{label}</label>;
  const manual = (path: Path) => <div className="form-grid">{text([...path, 'valor'], 'Valor da base')}{text([...path, 'fonte'], 'Fonte da base')}{text([...path, 'localizador'], 'Localização da base')}</div>;
  const base = (path: Path, title: string) => <fieldset className="space-y-3 border border-outline rounded-lg p-4"><legend>{title}</legend>
    {select([...path, 'modo'], 'Origem da base', { MANUAL: 'Valor manual com fonte', TABELA: 'Referência confirmada do cadastro' }, mode => set(path, { titulacao: get([...path, 'titulacao']) ?? '', ...(mode === 'TABELA' ? { referencia_salarial: { ...emptySalaryPosition(), data_referencia: '' } } : { valor_manual: { valor: '', fonte: '', localizador: '' } }) }))}
    {text([...path, 'titulacao'], 'Titulação ou N/A quando não houver RT')}
    {get([...path, 'referencia_salarial']) ? <SalaryPositionFields date value={obj(get([...path, 'referencia_salarial'])) as SalaryPosition} disabled={disabled} allowedCareers={['MAGISTERIO_SUPERIOR', 'EBTT']} onChange={position => set([...path, 'referencia_salarial'], position)} /> : manual([...path, 'valor_manual'])}
  </fieldset>;
  const collection = (key: string, title: string, create: () => unknown, render: (path: Path, row: Obj) => React.ReactNode) => <fieldset className="space-y-4 border border-outline rounded-lg p-4"><legend>{title}</legend>{((root[key] ?? []) as Obj[]).map((row, index) => <fieldset key={String(row.id ?? index)} className="space-y-3 border border-outline rounded p-3"><legend>{title} {index + 1}</legend>{render([key, index], row)}<Button variant="quiet" disabled={disabled} onClick={() => set([key], (root[key] as unknown[]).filter((_, n) => n !== index))}>Remover {title.toLowerCase()} {index + 1}</Button></fieldset>)}<Button variant="secondary" disabled={disabled} onClick={() => set([key], [...(root[key] as unknown[] ?? []), create()])}>Adicionar {title.toLowerCase()}</Button></fieldset>;
  const payment = (path: Path, holiday: boolean) => <>
    <div className="form-grid">{text([...path, 'id'], 'Identificador do pagamento')}{text([...path, 'competencia'], 'Competência', 'month')}{text([...path, 'rubrica'], 'Rubrica')}{text([...path, 'natureza_folha'], 'Natureza da folha')}{select([...path, 'natureza_rubrica'], 'Natureza da rubrica', { R: 'Rendimento', D: 'Desconto' })}{text([...path, 'identificador_folha'], 'Identificador da folha')}{text([...path, 'sequencia'], 'Sequência')}{select([...path, 'operacao'], 'Operação', { PAGAMENTO: 'Pagamento', COMPLEMENTO: 'Complemento', ESTORNO: 'Estorno' }, operation => { const row: Obj = { ...obj(get(path)), operacao: operation }; delete row.estorna_id; delete row.pagamento_original_id; set(path, row); })}{text([...path, 'valor'], 'Valor do lançamento')}{text([...path, 'origem'], 'Origem e localização do pagamento')}
    {get([...path, 'operacao']) === 'ESTORNO' && text([...path, 'estorna_id'], 'Identificador do pagamento estornado')}
    {holiday && get([...path, 'operacao']) === 'COMPLEMENTO' && text([...path, 'pagamento_original_id'], 'Identificador do pagamento complementado')}</div>
    {holiday && <>{text([...path, 'data_pagamento'], 'Data do pagamento original (quando necessária para ordenar)', 'date')}{text([...path, 'ordem_devolucao'], 'Ordem cronológica conferida (opcional; maior é mais recente)', 'number')}<div className="form-grid">{text([...path, 'periodo_aquisitivo', 'inicio'], 'Início do período aquisitivo', 'date')}{text([...path, 'periodo_aquisitivo', 'ultimo_dia_considerado'], 'Fim do período aquisitivo', 'date')}{text([...path, 'avos'], 'Avos quitados ou revertidos (complemento: zero)', 'number')}</div>
      {get([...path, 'base_terco']) ? <>{manual([...path, 'base_terco'])}<Button variant="quiet" disabled={disabled} onClick={() => { const next = { ...obj(get(path)) }; delete next.base_terco; set(path, next); }}>Remover base do terço</Button></> : <Button variant="secondary" disabled={disabled} onClick={() => set([...path, 'base_terco'], { valor: '', fonte: '', localizador: '' })}>Informar base pertinente do terço</Button>}
    </>}
  </>;
  const loadPreview = async () => {
    const requestVersion = ++version.current;
    setLoading(true); setStatus('');
    try {
      const response = await fetch(`${apiBaseUrl}/api/calculos/rescisao/previa`, { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ matricula: matricula || 'PENDENTE', rescisao: serializeRescisaoPlan(root) }) });
      const result = await response.json();
      if (requestVersion !== version.current) return;
      if (!response.ok) throw new Error(Array.isArray(result.detail) ? result.detail.map((error: Obj) => error.msg).join(' ') : 'Confira as datas e os campos da regra.');
      setPreview(result); setStatus('Sugestões calculadas. Confira antes de confirmar os dados.');
    } catch (error) { if (requestVersion === version.current) setStatus((error as Error).message); }
    finally { if (requestVersion === version.current) setLoading(false); }
  };
  return <div className="space-y-6" onChangeCapture={() => { version.current++; }} onClickCapture={event => { if ((event.target as HTMLElement).closest('button')) version.current++; }}>
    <p>Saldo das parcelas calculadas. Direito e documentos são conferidos pelo RH. Anexos opcionais; campos vazios exigem preenchimento manual. Não há OCR.</p>
    {fieldErrors[JSON.stringify(['rescisao'])] && <p role="alert">{fieldErrors[JSON.stringify(['rescisao'])]}</p>}
    <fieldset className="form-grid"><legend>Contrato e datas</legend>{select(['modalidade'], 'Modalidade da rescisão', { PROFESSOR_SUBSTITUTO: 'Professor substituto', OUTRO: 'Outra modalidade (pendente de regra)' })}{select(['motivo_termino'], 'Motivo do término', { TERMINO_CONTRATO: 'Término do contrato', RESCISAO_ANTECIPADA: 'Rescisão antecipada', OUTRO: 'Outro motivo (pendente de regra)' })}{text(['contrato_id'], 'Identificação do contrato')}{text(['natureza_folha_devida'], 'Natureza da folha devida')}{text(['inicio_exercicio'], 'Entrada em exercício', 'date')}{text(['data_termino'], 'Data do término', 'date')}{select(['sentido_termino'], 'Significado da data do término', { A_PARTIR_DE: 'Rescisão a partir de (dia excluído)', INCLUSIVO: 'Término inclusive neste dia' })}{text(['ultimo_dia_trabalhado'], 'Último dia trabalhado', 'date')}{text(['ultimo_dia_considerado'], 'Último dia considerado para as parcelas', 'date')}{text(['justificativa_ultimo_dia'], 'Justificativa de alteração do último dia')}</fieldset>
    <fieldset className="space-y-3"><legend>Regra conferida</legend><div className="form-grid">{text(['regra', 'identificador'], 'Identificação da regra')}{text(['regra', 'versao'], 'Versão da regra')}{text(['regra', 'fonte'], 'Fonte da regra')}{text(['regra', 'inicio_vigencia'], 'Início da vigência da regra', 'date')}{text(['regra', 'fim_vigencia'], 'Fim da vigência da regra', 'date')}{select(['regra', 'aniversario_meses_curtos'], 'Aniversário em meses curtos conforme regra', { LIMITAR_DIA_AO_MES: 'Dia original limitado ao último dia do mês' })}{text(['regra', 'limite_avos_ferias'], 'Limite de avos conforme regra (se houver)', 'number')}</div>
      {(['TERMINO_CONTRATO', 'RESCISAO_ANTECIPADA'] as const).map(motive => <label key={motive} className="flex gap-2"><input type="checkbox" disabled={disabled} checked={(get(['regra', 'motivos_suportados']) as string[] ?? []).includes(motive)} onChange={e => set(['regra', 'motivos_suportados'], e.target.checked ? [...(get(['regra', 'motivos_suportados']) as string[] ?? []), motive] : (get(['regra', 'motivos_suportados']) as string[]).filter(item => item !== motive))} />Regra cobre {motive === 'TERMINO_CONTRATO' ? 'término do contrato' : 'rescisão antecipada'}</label>)}
      {check(['regra', 'ferias_sem_teto_confirmada'], 'Confirmei ausência de teto de avos nesta regra')}{check(['regra', 'confirmada'], 'Conferi a regra aplicável, sua vigência e seus limites')}
    </fieldset>
    <Button variant="secondary" disabled={disabled} busy={loading} onClick={loadPreview}>Sugerir dias e avos pelas datas</Button><p role="status">{status}</p>
    {preview && <div className="space-y-3"><p>Último dia sugerido: {String(preview.ultimo_dia_sugerido)}. Competência salarial: {String(preview.competencia_salarial)}.</p>{Object.entries(obj(preview.sugestoes)).map(([key, value]) => <p key={key}>{({ dias_salariais: 'Dias salariais', avos_ferias: 'Avos de férias adquiridos', avos_13: 'Avos de 13º' } as Obj)[key] as string}: {String(value)}</p>)}<Button variant="secondary" disabled={disabled} onClick={() => set([], { ...root, ultimo_dia_considerado: preview.ultimo_dia_considerado, ultimo_dia_trabalhado: root.ultimo_dia_trabalhado || preview.ultimo_dia_considerado })}>Usar último dia sugerido após conferência</Button></div>}
    <fieldset className="space-y-3"><legend>Correções justificadas das sugestões</legend>{Object.entries({ dias_salariais: 'Dias salariais', avos_ferias: 'Avos de férias adquiridos', avos_13: 'Avos de 13º' }).map(([key, label]) => <div key={key}>{get(['correcoes', key]) ? <div className="form-grid">{text(['correcoes', key, 'valor'], label, 'number')}{text(['correcoes', key, 'justificativa'], `Justificativa: ${label}`)}<Button variant="quiet" disabled={disabled} onClick={() => { const next = { ...obj(root.correcoes) }; delete next[key]; set(['correcoes'], next); }}>Restaurar sugestão de {label.toLowerCase()}</Button></div> : <Button variant="quiet" disabled={disabled} onClick={() => set(['correcoes', key], { valor: '', justificativa: '' })}>Corrigir {label.toLowerCase()}</Button>}</div>)}</fieldset>
    {collection('salarios', 'Faixas salariais do mês final', () => ({ inicio: '', ultimo_dia_considerado: '', base: emptyRescisaoBase() }), path => <>{text([...path, 'inicio'], 'Início da faixa salarial', 'date')}{text([...path, 'ultimo_dia_considerado'], 'Fim da faixa salarial', 'date')}{base([...path, 'base'], 'Base salarial')}</>)}
    {(['base_ferias', 'base_13'] as const).map(key => <div key={key}>{root[key] ? <>{base([key], key === 'base_ferias' ? 'Base das férias indenizáveis' : 'Base do 13º')}<Button variant="quiet" disabled={disabled} onClick={() => { const next = { ...root }; delete next[key]; set([], next); }}>Remover {key === 'base_ferias' ? 'base das férias' : 'base do 13º'}</Button></> : <Button variant="secondary" disabled={disabled} onClick={() => set([key], emptyRescisaoBase())}>Informar {key === 'base_ferias' ? 'base das férias' : 'base do 13º'}</Button>}</div>)}
    {collection('pagamentos_ferias', 'Pagamentos da rubrica 750', () => emptyRescisaoPayment(true), path => payment(path, true))}
    {collection('recebidos', 'Recebimentos das parcelas finais', () => emptyRescisaoPayment(), path => payment(path, false))}
    {collection('documentos', 'Documentos do contrato', () => ({ id: crypto.randomUUID(), nome_arquivo: '', papel: '', contrato_identificado: '', vinculo_confirmado: false, candidatos: [], pagamentos_observados: [] }), (path, doc) => <>
      {text([...path, 'nome_arquivo'], 'Nome do arquivo')}{select([...path, 'papel'], 'Papel do documento', { FICHA_FINANCEIRA: 'Ficha financeira', CADASTRO: 'Cadastro funcional', TERMINO: 'Documento de término', CONTRATO_ADITIVO: 'Contrato ou aditivo', FERIAS: 'Programação de férias', OUTRO: 'Outro' })}{text([...path, 'matricula_identificada'], 'Matrícula identificada no documento')}{text([...path, 'contrato_identificado'], 'Contrato identificado no documento')}{text([...path, 'observacoes'], 'Observações do documento')}{check([...path, 'vinculo_confirmado'], 'Conferi que o documento pertence à pessoa e ao contrato')}
      {((doc.candidatos ?? []) as Obj[]).map((candidate, index) => <div key={index}>{text([...path, 'candidatos', index, 'valor'], `Dado extraído: ${candidate.campo}`)}{text([...path, 'candidatos', index, 'localizador'], 'Localização do dado extraído')}{['inicio_exercicio', 'data_termino', 'contrato_id'].includes(String(candidate.campo)) && <Button variant="quiet" disabled={disabled || doc.vinculo_confirmado !== true} onClick={() => set([String(candidate.campo)], candidate.valor)}>Usar {String(candidate.campo).replaceAll('_', ' ')} após conferir</Button>}{String(candidate.campo).includes('ferias') && <p>Programação não confirma gozo ou pagamento. Use somente após conferência do RH.</p>}</div>)}
      {((doc.pagamentos_observados ?? []) as Obj[]).map((observed, index) => <div key={index} className="space-y-2">{text([...path, 'pagamentos_observados', index, 'competencia'], 'Competência observada', 'month')}{text([...path, 'pagamentos_observados', index, 'valor_observado'], 'Valor observado')}{text([...path, 'pagamentos_observados', index, 'localizador'], 'Localização do pagamento observado')}<Button variant="quiet" disabled={disabled || doc.vinculo_confirmado !== true || doc.papel !== 'FICHA_FINANCEIRA'} onClick={() => {
        const holiday = observed.rubrica === '00750'; const key = holiday ? 'pagamentos_ferias' : 'recebidos'; const id = `${doc.id}:${index}`;
        if (((root[key] ?? []) as Obj[]).some(item => item.id === id)) { setLoading(false); setStatus('Pagamento já está em revisão. As edições foram preservadas.'); return; }
        const next = { ...emptyRescisaoPayment(holiday), id, competencia: observed.competencia ?? '', rubrica: observed.rubrica, natureza_rubrica: observed.natureza_rubrica ?? '', sequencia: observed.sequencia, valor: observed.valor_observado ?? '', origem: `${doc.nome_arquivo}: ${observed.localizador}`.slice(0, 300) };
        set([key], [...((root[key] ?? []) as Obj[]).filter(item => item.id !== id), next]);
      }}>Levar pagamento à revisão, sem presumir operação ou período</Button></div>)}
    </>)}
    {check(['conferido_pelo_rh'], 'Conferi contrato, datas, regra, bases, avos e pagamentos das parcelas calculadas')}
  </div>;
}
