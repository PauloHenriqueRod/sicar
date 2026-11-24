import { useRef, useState } from 'react';
import { Button, SelectField, TextField } from './ui';
import { apiBaseUrl } from '../utils/api';
import { emptyFunction, emptyFunctionComponent, emptySourcePeriod, emptySubstitutionState } from '../utils/substitutionReview';

type Path = (string | number)[];
type Obj = Record<string, unknown>;
const obj = (v: unknown): Obj => v && typeof v === 'object' && !Array.isArray(v) ? v as Obj : {};

export function SubstituicaoForm({ value, onChange, disabled, fieldErrors = {} }: { value: unknown; onChange: (path: Path, value: unknown) => void; disabled: boolean; fieldErrors?: Record<string, string> }) {
  const root = obj(value);
  const [references, setReferences] = useState<Obj[]>([]);
  const [lookupStatus, setLookupStatus] = useState('');
  const [loading, setLoading] = useState(false);
  const lookupVersion = useRef(0);
  const get = (path: Path): unknown => path.reduce<unknown>((v, key) => Array.isArray(v) ? v[Number(key)] : obj(v)[key], root);
  const error = (path: Path) => fieldErrors[JSON.stringify(['substituicao', ...path])];
  const set = (path: Path, val: unknown) => {
    const update = (v: unknown, keys: Path): unknown => {
      if (!keys.length) return val;
      const [key, ...rest] = keys;
      if (Array.isArray(v)) { const next = [...v]; next[Number(key)] = update(next[Number(key)], rest); return next; }
      return { ...obj(v), [key]: update(obj(v)[key], rest) };
    };
    const next = obj(update(root, path));
    if (path[0] !== 'conferido_pelo_rh') next.conferido_pelo_rh = false;
    const statePath = path[0] === 'estado_inicial' ? ['estado_inicial'] : path[0] === 'eventos' && path[2] === 'estado' ? ['eventos', path[1], 'estado'] : null;
    if (statePath && path.at(-1) !== 'confirmada') {
      const state = statePath[0] === 'estado_inicial' ? obj(next.estado_inicial) : obj((next.eventos as Obj[])[Number(path[1])].estado);
      state.opcao = { ...obj(state.opcao), confirmada: false };
    }
    onChange(['substituicao'], next);
  };
  const text = (path: Path, label: string, type = 'text') => <TextField key={JSON.stringify(path)} label={label} type={type} disabled={disabled} value={String(get(path) ?? '')} error={error(path)} onChange={e => { if (path[0] === 'periodo') { lookupVersion.current++; setReferences([]); setLookupStatus(''); setLoading(false); } set(path, e.target.value); }} />;
  const select = (path: Path, label: string, options: Record<string, string>, custom?: (v: string) => void) => <SelectField label={label} disabled={disabled} value={String(get(path) ?? '')} error={error(path)} onChange={e => custom ? custom(e.target.value) : set(path, e.target.value)}><option value="">Selecione</option>{Object.entries(options).map(([key, title]) => <option key={key} value={key}>{title}</option>)}</SelectField>;
  const groupError = (path: Path) => error(path) ? <p role="alert" className="feedback-error p-3 rounded-lg">{error(path)}</p> : null;
  const period = (path: Path) => <>{groupError(path)}<div className="form-grid">{text([...path, 'inicio'], 'Primeiro dia (incluído)', 'date')}{text([...path, 'ultimo_dia_considerado'], 'Último dia (incluído)', 'date')}{text([...path, 'motivo'], 'Motivo')}{text([...path, 'origem'], 'Documento de origem')}{text([...path, 'localizador'], 'Página, aba ou linha')}</div></>;
  const collection = (path: Path, title: string, create: () => Obj, render: (row: Path) => React.ReactNode, max = 100) => {
    const rows = Array.isArray(get(path)) ? get(path) as unknown[] : [];
    return <fieldset className="space-y-4 border border-outline rounded-lg p-4"><legend className="subsection-title">{title} ({rows.length})</legend>{groupError(path)}
      {rows.map((_, index) => <fieldset key={index} className="space-y-4 border border-outline rounded-lg p-4"><legend>{title}: registro {index + 1}</legend>{groupError([...path, index])}{render([...path, index])}<Button variant="quiet" disabled={disabled} onClick={() => set(path, rows.filter((_, n) => n !== index))}>Remover {title.toLowerCase()} {index + 1}</Button></fieldset>)}
      <Button variant="secondary" disabled={disabled || rows.length >= max} onClick={() => set(path, [...rows, create()])}>Adicionar {title.toLowerCase()}</Button>
    </fieldset>;
  };
  const fn = (path: Path, title: string) => <fieldset className="space-y-4"><legend className="subsection-title">{title}</legend>{groupError(path)}
    <div className="form-grid">{select([...path, 'tipo_funcao'], 'Tipo de função', { CD: 'CD', FG: 'FG', FCC: 'FCC' })}{text([...path, 'codigo_funcao'], 'Código da função')}{text([...path, 'modalidade'], 'Modalidade conforme a fonte')}</div>
    {references.length > 0 && <SelectField label="Usar componente do cadastro confirmado" disabled={disabled} value="" onChange={e => {
      const ref = references.find(r => String(r.id) === e.target.value);
      if (ref) {
      const previous = obj(get(path));
      const same = ['tipo_funcao', 'codigo_funcao', 'modalidade'].every(key => String(previous[key] ?? '').trim().toUpperCase() === String(ref[key]).trim().toUpperCase());
      const components = same && Array.isArray(previous.componentes) ? (previous.componentes as Obj[]).filter(row => String(row.componente ?? '').trim() && String(row.componente).toUpperCase() !== String(ref.componente).toUpperCase()) : [];
      set(path, { tipo_funcao: ref.tipo_funcao, codigo_funcao: ref.codigo_funcao, modalidade: ref.modalidade, componentes: [...components, { componente: ref.componente, percentual_utilizado: '', origem: 'TABELA' }] });
    }
    }}><option value="">Selecione uma referência; confirme os percentuais separadamente</option>{references.map(ref => <option key={String(ref.id)} value={String(ref.id)}>{String(ref.tipo_funcao)} {String(ref.codigo_funcao)} · {String(ref.modalidade)} · {String(ref.componente)} · {String(ref.inicio_vigencia)} a {String(ref.fim_vigencia ?? 'vigente')} · {String(ref.valor)}</option>)}</SelectField>}
    {collection([...path, 'componentes'], 'Componentes', emptyFunctionComponent, row => <>
      <div className="form-grid">{text([...row, 'componente'], 'Componente da função')}{text([...row, 'percentual_utilizado'], 'Percentual utilizado do componente (%)')}{select([...row, 'origem'], 'Origem do valor', { TABELA: 'Referência confirmada por vigência', MANUAL: 'Valor manual com fonte' }, v => {
        const current = Object.fromEntries(Object.entries(obj(get(row))).filter(([key]) => !['valor_manual', 'inicio_vigencia', 'fim_vigencia'].includes(key)));
        set(row, { ...current, origem: v, ...(v === 'MANUAL' ? { valor_manual: { valor: '', fonte: '', localizador: '' }, inicio_vigencia: '', fim_vigencia: '' } : {}) });
      })}</div>
      {get([...row, 'origem']) === 'MANUAL' && <div className="form-grid">{text([...row, 'valor_manual', 'valor'], 'Valor manual do componente')}{text([...row, 'valor_manual', 'fonte'], 'Fonte do valor manual')}{text([...row, 'valor_manual', 'localizador'], 'Localizador do valor manual')}{text([...row, 'inicio_vigencia'], 'Início da vigência do valor', 'date')}{text([...row, 'fim_vigencia'], 'Fim da vigência do valor (opcional)', 'date')}</div>}
    </>, 10)}
  </fieldset>;
  const state = (path: Path) => <>{groupError(path)}{fn([...path, 'substituida'], 'Função substituída')}
    {select([...path, 'propria', 'situacao'], 'Situação da função própria', { SEM_FUNCAO_CONFIRMADA: 'Ausência de função própria confirmada', COM_FUNCAO: 'Possui função própria' }, v => set([...path, 'propria'], { situacao: v, ...(v === 'COM_FUNCAO' ? { funcao: emptyFunction() } : {}) }))}
    {get([...path, 'propria', 'situacao']) === 'COM_FUNCAO' && fn([...path, 'propria', 'funcao'], 'Função própria')}
    <fieldset className="space-y-4"><legend className="subsection-title">Opção remuneratória e regra conferida</legend>{groupError([...path, 'opcao'])}<p className="help-text">As operações abaixo não concedem uma opção legal. Confirme a modalidade, os componentes e os percentuais na regra aplicável. Não some o TOTAL aos seus componentes.</p>
      <div className="form-grid">{text([...path, 'opcao', 'identificador'], 'Identificação da regra')}{text([...path, 'opcao', 'versao'], 'Versão da regra')}{text([...path, 'opcao', 'fonte'], 'Fonte da regra')}{text([...path, 'opcao', 'inicio_vigencia'], 'Início dos efeitos da regra', 'date')}{text([...path, 'opcao', 'fim_vigencia'], 'Fim dos efeitos da regra (opcional)', 'date')}
      {select([...path, 'opcao', 'calculo'], 'Composição confirmada da opção', { DIFERENCA_FUNCOES: 'Base substituída menos função própria', BASE_SUBSTITUIDA: 'Somente base substituída' })}{select([...path, 'opcao', 'diferenca_negativa'], 'Tratamento de diferença mensal negativa conforme regra', { ZERAR: 'Limitar o devido mensal a zero', PERMITIR: 'Preservar diferença mensal negativa' })}</div>
      <label className="block"><input type="checkbox" checked={get([...path, 'opcao', 'confirmada']) === true} disabled={disabled} onChange={e => set([...path, 'opcao', 'confirmada'], e.target.checked)} /> Conferi a opção, os componentes e os percentuais conforme a regra.</label>
    </fieldset>
  </>;
  const payroll = (path: Path) => <div className="form-grid">{text([...path, 'rubrica'], 'Código da rubrica')}{text([...path, 'natureza_folha'], 'Natureza da folha')}{select([...path, 'natureza_rubrica'], 'Natureza da rubrica', { R: 'Rendimento', D: 'Desconto' })}</div>;
  return <div className="space-y-6">{groupError([])}
    <p className="help-text">Cruze a designação com o afastamento do titular e exclua férias ou impedimentos do substituto. Intervalos sobrepostos são contados uma única vez. Todos os dados podem ser preenchidos manualmente.</p>
    <div className="form-grid">{text(['periodo', 'inicio'], 'Início da apuração', 'date')}{text(['periodo', 'ultimo_dia_considerado'], 'Último dia considerado', 'date')}{text(['titular_matricula'], 'Matrícula do titular')}{text(['data_documento'], 'Data do documento (opcional)', 'date')}{text(['data_implantacao'], 'Data de implantação (opcional)', 'date')}</div>{groupError(['periodo'])}
    <fieldset className="space-y-4"><legend className="subsection-title">Designação</legend>{period(['designacao'])}</fieldset>
    {collection(['afastamentos_titular'], 'Afastamentos do titular', emptySourcePeriod, period)}
    {collection(['impedimentos_substituto'], 'Impedimentos do substituto', emptySourcePeriod, period)}
    <Button variant="secondary" disabled={disabled || loading || !get(['periodo', 'inicio']) || !get(['periodo', 'ultimo_dia_considerado'])} onClick={async () => {
      const version = ++lookupVersion.current;
      setLoading(true); setReferences([]); setLookupStatus('Consultando referências...');
      try {
        let page = 1, rows: Obj[] = [], total = 0;
        do {
          const params = new URLSearchParams({ inicio: String(get(['periodo', 'inicio'])), fim: String(get(['periodo', 'ultimo_dia_considerado'])), pagina: String(page) });
          const response = await fetch(`${apiBaseUrl}/api/calculos/referencias-funcao?${params}`, { credentials: 'include' });
          if (!response.ok) throw new Error();
          const data = await response.json();
          if (!Array.isArray(data.itens) || !Number.isInteger(data.total) || data.total < 0 || (!data.itens.length && rows.length < data.total)) throw new Error();
          rows = [...rows, ...data.itens]; total = data.total; page++;
          if (version !== lookupVersion.current) return;
        } while (rows.length < total && rows.length < 2000);
        setReferences(rows); setLookupStatus(rows.length ? `${rows.length} referências disponíveis. A cobertura de todo o período será validada no cálculo.` : 'Nenhuma referência encontrada. Solicite o cadastro de uma referência ou informe valor manual com fonte.');
      } catch { if (version === lookupVersion.current) setLookupStatus('Não foi possível consultar as referências. Tente novamente ou informe os valores manualmente com fonte.'); }
      finally { if (version === lookupVersion.current) setLoading(false); }
    }}>Consultar referências confirmadas</Button>{lookupStatus && <p role="status" className="help-text">{lookupStatus}</p>}
    <fieldset className="space-y-4"><legend className="subsection-title">Situação no início da apuração</legend>{state(['estado_inicial'])}</fieldset>
    {collection(['eventos'], 'Mudanças de função ou opção', () => ({ id: crypto.randomUUID(), efeitos_financeiros: '', data_documento: '', data_implantacao: '', origem: '', estado: emptySubstitutionState() }), row => <>{text([...row, 'efeitos_financeiros'], 'Início dos efeitos financeiros', 'date')}{text([...row, 'data_documento'], 'Data do documento da mudança (opcional)', 'date')}{text([...row, 'data_implantacao'], 'Data de implantação da mudança (opcional)', 'date')}{text([...row, 'origem'], 'Origem da mudança')}{state([...row, 'estado'])}</>)}
    <fieldset className="space-y-4"><legend className="subsection-title">Rubrica devida</legend>{payroll(['rubrica'])}</fieldset>
    {collection(['recebidos'], 'Pagamentos anteriores', () => ({ id: crypto.randomUUID(), competencia: '', rubrica: '', natureza_folha: '', natureza_rubrica: '', identificador_folha: '', sequencia: '', operacao: '', valor: '', origem: '' }), row => <>
      {text([...row, 'id'], 'Identificação do lançamento')}{text([...row, 'competencia'], 'Competência do pagamento', 'month')}{payroll(row)}<div className="form-grid">{text([...row, 'identificador_folha'], 'Identificação da folha')}{text([...row, 'sequencia'], 'Sequência')}{select([...row, 'operacao'], 'Operação', { PAGAMENTO: 'Pagamento', COMPLEMENTO: 'Complementação', ESTORNO: 'Estorno' }, v => { const next: Obj = { ...obj(get(row)), operacao: v }; if (v !== 'ESTORNO') delete next.estorna_id; set(row, next); })}{text([...row, 'valor'], 'Valor pago ou estornado (positivo)')}{text([...row, 'origem'], 'Origem do pagamento')}</div>{get([...row, 'operacao']) === 'ESTORNO' && text([...row, 'estorna_id'], 'Identificação do pagamento original')}
    </>, 2000)}
    <fieldset className="space-y-4"><legend className="subsection-title">Documentos do mesmo processo</legend>
      {(Array.isArray(root.documentos) ? root.documentos : []).map((_, index) => { const path: Path = ['documentos', index]; return <fieldset key={index} className="space-y-3 border border-outline p-4 rounded-lg"><legend>{String(get([...path, 'nome_arquivo']))}</legend>
        {text([...path, 'nome_arquivo'], 'Identificação do documento')}
        {select([...path, 'papel'], 'Papel do documento', { DESIGNACAO: 'Designação', AFASTAMENTO_TITULAR: 'Afastamento do titular', IMPEDIMENTO_SUBSTITUTO: 'Férias ou impedimento do substituto', FICHA_FINANCEIRA: 'Ficha financeira', OPCAO: 'Opção remuneratória', OUTRO: 'Outro' })}
        {select([...path, 'pessoa'], 'Pessoa identificada no documento', { TITULAR: 'Titular', SUBSTITUTO: 'Substituto', NAO_SE_APLICA: 'Não se aplica à identificação capturada' })}{text([...path, 'nome_identificado'], 'Nome identificado (confira a pessoa)')}{text([...path, 'matricula_identificada'], 'Matrícula identificada (confira a pessoa)')}
        {((get([...path, 'candidatos']) ?? []) as Obj[]).map((candidate, n) => <div key={n} className="space-y-3">{text([...path, 'candidatos', n, 'inicio'], 'Início extraído', 'date')}{text([...path, 'candidatos', n, 'ultimo_dia_considerado'], 'Último dia extraído', 'date')}{text([...path, 'candidatos', n, 'localizador'], 'Localização no texto extraído')}
          <Button variant="secondary" disabled={disabled || get([...path, 'papel']) !== candidate.campo} onClick={() => {
            const source = { id: `${String(get([...path, 'id']))}:${n}`, inicio: candidate.inicio, ultimo_dia_considerado: candidate.ultimo_dia_considerado, motivo: ({ DESIGNACAO: 'Designação', AFASTAMENTO_TITULAR: 'Afastamento', IMPEDIMENTO_SUBSTITUTO: 'Impedimento' } as Record<string, string>)[String(candidate.campo)], origem: get([...path, 'nome_arquivo']), localizador: candidate.localizador };
            const key = candidate.campo === 'DESIGNACAO' ? 'designacao' : candidate.campo === 'AFASTAMENTO_TITULAR' ? 'afastamentos_titular' : 'impedimentos_substituto';
            set([key], key === 'designacao' ? source : [...((root[key] ?? []) as Obj[]).filter(r => r.id !== source.id), source]);
          }}>Usar período extraído após conferir o papel do documento</Button>
        </div>)}
        {((get([...path, 'pagamentos_observados']) ?? []) as Obj[]).map((payment, n) => <div key={n} className="space-y-3 border-t border-outline pt-3">
          <p className="help-text">Pagamento observado na rubrica 83185. Confirme competência, folha, natureza e operação; valor negativo exige revisão do estorno, sem conversão automática.</p>
          {text([...path, 'pagamentos_observados', n, 'competencia'], 'Competência observada', 'month')}{text([...path, 'pagamentos_observados', n, 'valor_observado'], 'Valor observado na ficha')}{text([...path, 'pagamentos_observados', n, 'sequencia'], 'Sequência observada')}{text([...path, 'pagamentos_observados', n, 'localizador'], 'Origem do valor observado')}
          <Button variant="secondary" disabled={disabled || get([...path, 'papel']) !== 'FICHA_FINANCEIRA' || get([...path, 'pessoa']) !== 'SUBSTITUTO' || ((root.recebidos ?? []) as unknown[]).length >= 2000} onClick={() => {
            const id = `${String(get([...path, 'id']))}:P${n}`;
            set(['recebidos'], [...((root.recebidos ?? []) as Obj[]).filter(row => row.id !== id), { id, competencia: payment.competencia ?? '', rubrica: payment.rubrica, natureza_rubrica: payment.natureza_rubrica ?? '', natureza_folha: '', identificador_folha: '', sequencia: payment.sequencia, operacao: '', valor: payment.valor_observado ?? '', origem: `${String(get([...path, 'nome_arquivo']))}: ${String(payment.localizador)}` }]);
          }}>Levar pagamento observado para conferência</Button>
        </div>)}
        <Button variant="quiet" disabled={disabled} onClick={() => set(['documentos'], (root.documentos as unknown[]).filter((_, n) => n !== index))}>Remover documento do processo</Button>
      </fieldset>; })}
      <p className="help-text">Documentos sem leitura suportada permitem preenchimento manual. Não há OCR automático. Sem registros de impedimentos ou pagamentos, a confirmação abaixo declara que nenhum foi identificado para este processo.</p>
    </fieldset>
    <label className="block"><input type="checkbox" checked={root.conferido_pelo_rh === true} disabled={disabled} onChange={e => set(['conferido_pelo_rh'], e.target.checked)} /> Conferi os envolvidos, períodos, impedimentos, fontes, funções, opção e pagamentos. O direito foi verificado pelo RH.</label>{groupError(['conferido_pelo_rh'])}
  </div>;
}
