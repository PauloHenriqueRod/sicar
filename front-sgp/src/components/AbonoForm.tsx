import { Button, SelectField, TextField } from './ui';
import { useState } from 'react';
import { emptyAbonoMapping, emptyAbonoParcel, emptyAbonoRecord } from '../utils/abonoReview';

type Obj = Record<string, unknown>;
type Path = (string | number)[];
const obj = (value: unknown): Obj => value && typeof value === 'object' && !Array.isArray(value) ? value as Obj : {};
const categories = { REGULAR: 'Regular', DECIMO_TERCEIRO: '13º' };
const roles = { CONTRIBUICAO: 'Contribuição descontada', ABONO: 'Abono recebido' };
const collections = ['mapeamentos', 'parcelas', 'cobertura_13', 'lancamentos', 'documentos'];

export function AbonoForm({ value, disabled, onChange, fieldErrors = {} }: { value: unknown; disabled: boolean; onChange: (path: Path, value: unknown) => void; fieldErrors?: Record<string, string> }) {
  const root = obj(value);
  const [rowKeys, setRowKeys] = useState<Record<string, string[]>>(() => Object.fromEntries(collections.map(key => [key, ((root[key] ?? []) as unknown[]).map(() => crypto.randomUUID())])));
  const get = (path: Path): unknown => path.reduce<unknown>((value, key) => Array.isArray(value) ? value[Number(key)] : obj(value)[key], root);
  const set = (path: Path, value: unknown, removedIndex?: number) => {
    const update = (current: unknown, keys: Path): unknown => {
      if (!keys.length) return value;
      const [key, ...rest] = keys;
      if (Array.isArray(current)) { const next = [...current]; next[Number(key)] = update(next[Number(key)], rest); return next; }
      return { ...obj(current), [key]: update(obj(current)[key], rest) };
    };
    const next = obj(update(root, path));
    if (path[0] !== 'conferido_pelo_rh') next.conferido_pelo_rh = false;
    if (path[0] === 'regra' && path.at(-1) !== 'confirmada') next.regra = { ...obj(next.regra), confirmada: false };
    if (path[0] === 'mapeamentos' && path.length > 2 && path.at(-1) !== 'confirmado') (next.mapeamentos as Obj[])[Number(path[1])].confirmado = false;
    if (path[0] === 'lancamentos' && path.length > 2 && path.at(-1) !== 'conferido') (next.lancamentos as Obj[])[Number(path[1])].conferido = false;
    if (path[0] === 'documentos' && path[2] === 'observacoes' && ['valor_observado', 'rubrica', 'natureza_rubrica', 'competencia', 'sequencia'].includes(String(path.at(-1)))) {
      const observations = (next.documentos as Obj[])[Number(path[1])].observacoes as Obj[];
      observations[Number(path[3])].correcao_sinal_confirmada = false;
    }
    const nextKeys = { ...rowKeys };
    for (const key of collections) {
      const current = ((root[key] ?? []) as unknown[]).map((_, index) => rowKeys[key]?.[index] ?? `${key}:${index}`);
      const keys = path[0] === key && removedIndex !== undefined ? current.filter((_, index) => index !== removedIndex) : current;
      const length = ((next[key] ?? []) as unknown[]).length;
      while (keys.length < length) keys.push(crypto.randomUUID());
      nextKeys[key] = keys.slice(0, length);
    }
    setRowKeys(nextKeys);
    onChange(['abono'], next);
  };
  const error = (path: Path) => fieldErrors[JSON.stringify(['abono', ...path])];
  const text = (path: Path, label: string, type = 'text') => <TextField key={JSON.stringify(path.filter(key => typeof key !== 'number'))} label={label} type={type} disabled={disabled} error={error(path)} value={String(get(path) ?? '')} onChange={e => set(path, e.target.value)} />;
  const select = (path: Path, label: string, choices: Obj, change?: (value: string) => void) => <SelectField label={label} disabled={disabled} error={error(path)} value={String(get(path) ?? '')} onChange={e => change ? change(e.target.value) : set(path, e.target.value)}><option value="">Selecione</option>{Object.entries(choices).map(([key, label]) => <option key={key} value={key}>{String(label)}</option>)}</SelectField>;
  const check = (path: Path, label: string) => <label className="flex gap-2"><input type="checkbox" disabled={disabled} checked={get(path) === true} onChange={e => set(path, e.target.checked)} />{label}</label>;
  const collection = (key: string, title: string, create: () => unknown, render: (path: Path, row: Obj) => React.ReactNode) => <fieldset className="space-y-4 rounded-lg border border-outline p-4"><legend>{title}</legend>{error([key]) && <p role="alert">{error([key])}</p>}{((root[key] ?? []) as Obj[]).map((row, index) => <fieldset key={rowKeys[key]?.[index] ?? `${key}:${index}`} className="space-y-3 border border-outline rounded p-3"><legend>{title} {index + 1}</legend>{render([key, index], row)}<Button variant="quiet" disabled={disabled} onClick={() => set([key], (root[key] as unknown[]).filter((_, n) => n !== index), index)}>Remover {title.toLowerCase()} {index + 1}</Button></fieldset>)}<Button variant="secondary" disabled={disabled} onClick={() => set([key], [...(root[key] as unknown[] ?? []), create()])}>Adicionar {title.toLowerCase()}</Button></fieldset>;
  const parcelChoices = Object.fromEntries(((root.parcelas ?? []) as Obj[]).map(row => [String(row.id), `${row.categoria === 'DECIMO_TERCEIRO' ? '13º' : 'Regular'} ${row.competencia_direito || row.exercicio_13 || '(referência pendente)'} — ${row.id}`]));
  const recordChoices = Object.fromEntries(((root.lancamentos ?? []) as Obj[]).map(row => [String(row.id), `${row.rubrica || 'Rubrica pendente'} / ${row.competencia || 'competência pendente'} — ${row.id}`]));
  return <div className="space-y-6">
    <p>Contribuição descontada não comprova direito ao abono. Confira o período reconhecido pelo RH, cada desconto e cada pagamento. Anexos opcionais; campos ausentes ficam para preenchimento manual.</p>
    {error([]) && <p role="alert" className="feedback-error p-3 rounded">{error([])}</p>}
    <fieldset className="form-grid"><legend>Direito confirmado</legend>{text(['vinculo_id'], 'Identificação do vínculo')}{text(['periodo_direito', 'inicio'], 'Início dos efeitos financeiros', 'date')}{text(['periodo_direito', 'ultimo_dia_considerado'], 'Último dia do direito considerado', 'date')}{text(['data_documento'], 'Data do documento de reconhecimento (opcional)', 'date')}{text(['data_requerimento'], 'Data do requerimento (opcional)', 'date')}</fieldset>
    <fieldset className="space-y-3"><legend>Regra aplicável</legend><div className="form-grid">{text(['regra', 'identificador'], 'Identificação da regra')}{text(['regra', 'versao'], 'Versão da regra')}{text(['regra', 'fonte'], 'Fonte da regra')}{text(['regra', 'inicio_vigencia'], 'Início da vigência da regra', 'date')}{text(['regra', 'fim_vigencia'], 'Fim da vigência da regra (opcional)', 'date')}</div>{check(['regra', 'confirmada'], 'Conferi o direito, a regra e sua vigência')}</fieldset>
    {collection('mapeamentos', 'Mapeamentos de rubricas', emptyAbonoMapping, path => <><div className="form-grid">{text([...path, 'rubrica'], 'Código da rubrica mapeada')}{select([...path, 'papel'], 'Papel da rubrica', roles)}{select([...path, 'categoria'], 'Categoria da rubrica', categories)}{text([...path, 'fonte'], 'Fonte do mapeamento')}</div>{check([...path, 'confirmado'], 'Conferi o papel e a categoria desta rubrica')}</>)}
    <p className="help-text">98002 é candidata a contribuição regular; 98004 a contribuição do 13º. Confirme seus usos e informe as rubricas efetivas de pagamento do abono. Não use essas contribuições como abono recebido.</p>
    {collection('parcelas', 'Parcelas de direito', emptyAbonoParcel, (path, row) => <>
      <div className="form-grid">{text([...path, 'id'], 'Identificador da parcela')}{select([...path, 'categoria'], 'Categoria da parcela', categories, category => { const next: Obj = { ...row, categoria: category }; delete next.competencia_direito; delete next.exercicio_13; set(path, next); })}
      {row.categoria === 'REGULAR' ? text([...path, 'competencia_direito'], 'Competência de direito', 'month') : row.categoria === 'DECIMO_TERCEIRO' ? text([...path, 'exercicio_13'], 'Exercício de referência do 13º', 'number') : null}
      {text([...path, 'periodo_referencia', 'inicio'], 'Início do período de referência', 'date')}{text([...path, 'periodo_referencia', 'ultimo_dia_considerado'], 'Fim do período de referência', 'date')}{text([...path, 'rubrica_abono'], 'Rubrica do abono devido')}{text([...path, 'natureza_folha_devida'], 'Natureza da folha devida')}{select([...path, 'contribuicao'], 'Estado da contribuição', { PENDENTE: 'Não apurada', IDENTIFICADA: 'Lançamentos identificados', ZERO_CONFIRMADO: 'Zero confirmado pelo RH' })}{select([...path, 'recebimento'], 'Estado da pesquisa de pagamentos', { PENDENTE: 'Pesquisa incompleta', IDENTIFICADO: 'Pagamentos identificados', NAO_HOUVE_CONFIRMADO: 'Não houve pagamento, conferido pelo RH' })}{text([...path, 'fonte_conferencia'], 'Fonte da conferência da parcela')}</div>
      {row.valor_elegivel ? <><div className="form-grid">{text([...path, 'valor_elegivel', 'valor'], 'Contribuição elegível conferida')}{text([...path, 'valor_elegivel', 'fonte'], 'Fonte do valor elegível')}{text([...path, 'valor_elegivel', 'localizador'], 'Localização do valor elegível')}{text([...path, 'justificativa_elegivel'], 'Justificativa do valor elegível')}</div><Button variant="quiet" disabled={disabled} onClick={() => { const next = { ...row }; delete next.valor_elegivel; delete next.justificativa_elegivel; set(path, next); }}>Remover valor elegível manual</Button></> : <Button variant="secondary" disabled={disabled} onClick={() => set(path, { ...row, valor_elegivel: { valor: '', fonte: '', localizador: '' }, justificativa_elegivel: '' })}>Informar contribuição elegível, sem rateio automático</Button>}
    </>)}
    {collection('cobertura_13', 'Cobertura do 13º por exercício', () => ({ exercicio: '', situacao: 'PENDENTE', justificativa: '' }), path => <div className="form-grid">{text([...path, 'exercicio'], 'Exercício conferido', 'number')}{select([...path, 'situacao'], 'Situação do 13º', { PENDENTE: 'Ainda não apurado', INCLUIDO: 'Parcela incluída e conferida', NAO_APLICAVEL_CONFIRMADO: 'Não aplicável, confirmado pelo RH' })}{text([...path, 'justificativa'], 'Justificativa da cobertura')}</div>)}
    {collection('lancamentos', 'Lançamentos de folha', emptyAbonoRecord, (path, row) => <><div className="form-grid">{text([...path, 'id'], 'Identificador do lançamento')}{select([...path, 'papel'], 'Papel do lançamento', roles)}{select([...path, 'categoria'], 'Categoria do lançamento', categories)}{select([...path, 'parcela_id'], 'Parcela de direito vinculada', parcelChoices)}{text([...path, 'competencia'], 'Competência da folha de origem', 'month')}{text([...path, 'rubrica'], 'Rubrica do lançamento')}{text([...path, 'natureza_folha'], 'Natureza da folha de origem')}{select([...path, 'natureza_rubrica'], 'Natureza da rubrica observada', { R: 'Rendimento', D: 'Desconto' })}{text([...path, 'identificador_folha'], 'Identificador da folha')}{text([...path, 'sequencia'], 'Sequência')}{select([...path, 'operacao'], 'Operação confirmada', { LANCAMENTO: 'Lançamento original', COMPLEMENTO: 'Complemento', ESTORNO: 'Estorno ou restituição vinculada' }, operation => { const next: Obj = { ...row, operacao: operation, conferido: false }; delete next.estorna_id; delete next.complementa_id; set(path, next); })}{text([...path, 'valor'], 'Valor do lançamento, inclusive zero confirmado')}{text([...path, 'origem'], 'Origem e localização do lançamento')}
      {row.operacao === 'COMPLEMENTO' && select([...path, 'complementa_id'], 'Lançamento complementado', recordChoices)}{row.operacao === 'ESTORNO' && select([...path, 'estorna_id'], 'Lançamento estornado', recordChoices)}</div>{check([...path, 'conferido'], 'Conferi valor, identidade da folha, operação e associação deste lançamento')}</>)}
    {collection('documentos', 'Documentos do vínculo', () => ({ id: crypto.randomUUID(), nome_arquivo: '', vinculo_identificado: '', vinculo_confirmado: false, observacoes: [] }), (path, doc) => <>
      {text([...path, 'nome_arquivo'], 'Nome do documento')}{text([...path, 'matricula_identificada'], 'Matrícula identificada no documento')}{text([...path, 'vinculo_identificado'], 'Vínculo identificado no documento')}{check([...path, 'vinculo_confirmado'], 'Conferi a pessoa e o vínculo deste documento')}
      {((doc.observacoes ?? []) as Obj[]).map((observation, index) => { const p = [...path, 'observacoes', index]; return <fieldset key={index} className="space-y-3 border-t border-outline pt-3"><legend>Observação {index + 1}</legend><div className="form-grid">{text([...p, 'rubrica'], 'Rubrica observada')}{text([...p, 'descricao'], 'Descrição observada')}{text([...p, 'competencia'], 'Competência observada', 'month')}{select([...p, 'natureza_rubrica'], 'Natureza observada', { R: 'Rendimento', D: 'Desconto' })}{text([...p, 'sequencia'], 'Sequência observada')}{text([...p, 'valor_observado'], 'Valor observado na ficha')}{text([...p, 'localizador'], 'Localização na ficha')}{select([...p, 'decisao'], 'Decisão sobre a observação', { PENDENTE: 'Pendente de revisão', UTILIZADO: 'Vinculada a lançamento', DESCARTADO: 'Excluída com justificativa' })}{select([...p, 'lancamento_id'], 'Lançamento associado à observação', recordChoices)}{text([...p, 'justificativa'], 'Justificativa de exclusão ou correção')}</div>{String(observation.valor_observado ?? '').trim().startsWith('-') && <div className="space-y-2 feedback-warning p-3 rounded"><p>Valor negativo observado. Confira se representa estorno; uma inversão de sinal exige justificativa e confirmação específica.</p>{check([...p, 'correcao_sinal_confirmada'], 'Confirmei a correção do sinal observado conforme a justificativa')}</div>}
        <Button variant="secondary" disabled={disabled || doc.vinculo_confirmado !== true} onClick={() => {
          const id = `${doc.id}:${index}`; const existing = ((root.lancamentos ?? []) as Obj[]).find(row => row.id === id);
          if (existing) return;
          const raw = String(observation.valor_observado ?? '');
          const record = { ...emptyAbonoRecord(), id, competencia: observation.competencia ?? '', rubrica: observation.rubrica, natureza_rubrica: observation.natureza_rubrica ?? '', sequencia: observation.sequencia, valor: raw.replace(/^[+-]/, ''), origem: `${doc.nome_arquivo}: ${observation.localizador}`.slice(0, 300) };
          const documents = structuredClone(root.documentos) as Obj[];
          (documents[Number(path[1])].observacoes as Obj[])[index] = { ...observation, decisao: 'UTILIZADO', lancamento_id: id };
          set([], { ...root, documentos: documents, lancamentos: [...(root.lancamentos as Obj[] ?? []), record] });
        }}>Levar à revisão sem presumir papel, categoria ou operação</Button>
      </fieldset>; })}
    </>)}
    {check(['conferido_pelo_rh'], 'Conferi direito, vínculo, rubricas, cobertura, descontos e abonos recebidos de todas as parcelas')}
  </div>;
}
