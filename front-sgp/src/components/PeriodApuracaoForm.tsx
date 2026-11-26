import { Button, SelectField, TextField } from './ui';
import { DocentePositionLookup } from './DocentePositionLookup';
import { emptyDocenteEvent, setAt } from '../utils/documentExtraction';
import { SalaryPositionFields } from './SalaryPositionFields';
import { AdditionalConcessionFields } from './AdditionalConcessionFields';
import { emptyAdditional, emptyManualValue, emptyRule } from '../utils/periodReviewData';
import { emptySalaryPosition } from '../utils/salaryReferences';
import type { SalaryPosition } from '../utils/salaryReferences';
import { useEffect, useId, useRef } from 'react';

type Path = (string | number)[];
const object = (value: unknown): Record<string, unknown> => value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
const formulas = { VB: 'Vencimento básico', RT: 'Retribuição por titulação', VB_RT: 'VB e RT', IQ_SOBRE_VB: 'IQ sobre o VB', ADICIONAL_SOBRE_VB: 'Adicional legado sobre o VB', ADICIONAL_CONFIRMADO: 'Adicional com concessão confirmada', ANUENIO_SOBRE_VB: 'Anuênio sobre o VB', VALOR_MENSAL: 'Valor mensal conferido' };
const changes = { posicao: 'Posição ou jornada', titulacao: 'Titulação', vb_manual: 'VB manual ou retorno à tabela', rt_manual: 'RT manual ou retorno à tabela', percentual_iq: 'Percentual de IQ', percentual_adicional: 'Percentual de adicional', percentual_anuenio: 'Percentual de anuênio' };

function PeriodCollection({ label, initiallyOpen, hasError, children }: {
  label: string; initiallyOpen: boolean; hasError: boolean; children: React.ReactNode;
}) {
  const details = useRef<HTMLDetailsElement>(null);
  useEffect(() => {
    // Abre o grupo inválido sem fechá-lo quando a primeira edição limpa os erros.
    if (hasError && details.current) details.current.open = true;
  }, [hasError]);
  return <details ref={details} open={initiallyOpen || undefined} className="border border-outline rounded-lg p-4 space-y-4">
    <summary className="subsection-title">{label}</summary>{children}
  </details>;
}

export function PeriodApuracaoForm({ value, onChange, disabled, fieldErrors = {}, progression = false, additional = false, monthly = false, destinationSource, originBase, children }: { value: unknown; onChange: (path: Path, value: unknown) => void; disabled: boolean; fieldErrors?: Record<string, string>; progression?: boolean; additional?: boolean; monthly?: boolean; destinationSource?: string; originBase?: string; children?: React.ReactNode }) {
  const root = object(value);
  const rubricRows = Array.isArray(root.rubricas) ? root.rubricas : [];
  const hasAnnuity = Number(String(object(root.estado_inicial).percentual_anuenio ?? '').replace(',', '.')) > 0;
  const salaryComponents = hasAnnuity ? ['VB', 'RT', 'ANUENIO_SOBRE_VB'] : ['VB', 'RT'];
  const missingSalaryComponents = salaryComponents.filter(formula => !rubricRows.some(row => object(row).formula === formula));
  const rootKey = additional ? 'adicionais' : progression ? 'progressao' : 'apuracao';
  const structured = progression || additional;
  const isTAE = root.modalidade === 'TAE';
  const availableFormulas = additional ? { ADICIONAL_CONFIRMADO: formulas.ADICIONAL_CONFIRMADO } : progression ? Object.fromEntries(Object.entries(formulas).filter(([key]) => !['VB_RT', 'VALOR_MENSAL', 'ADICIONAL_SOBRE_VB', ...(isTAE ? ['RT'] : ['IQ_SOBRE_VB'])].includes(key))) : formulas;
  const formId = useId();
  const errorKey = (path: Path) => JSON.stringify([rootKey, ...path]);
  const errorFor = (path: Path) => fieldErrors[errorKey(path)];
  const errorId = (path: Path) => `${formId}-${encodeURIComponent(errorKey(path))}`;
  const groupError = (path: Path) => errorFor(path) ? <p id={errorId(path)} role="alert" className="feedback-error rounded-lg p-3">{errorFor(path)}</p> : null;
  const hasError = (path: Path) => Object.keys(fieldErrors).some(key => key === errorKey(path) || key.startsWith(`${errorKey(path).slice(0, -1)},`));
  const get = (path: Path): unknown => path.reduce<unknown>((current, key) => Array.isArray(current) ? current[Number(key)] : object(current)[key], root);
  const set = (path: Path, value: unknown) => {
    const update = (current: unknown, keys: Path): unknown => {
      if (!keys.length) return value;
      const [key, ...rest] = keys;
      if (Array.isArray(current)) { const next = [...current]; next[Number(key)] = update(next[Number(key)], rest); return next; }
      return { ...object(current), [key]: update(object(current)[key], rest) };
    };
    const next = object(update(root, path));
    if (path[0] !== 'conferido_pelo_rh') next.conferido_pelo_rh = false;
    if (path[0] === 'bases_mensais_origem' && typeof path[1] === 'number' && path.at(-1) !== 'base_mensal_integral_confirmada') {
      const rows = next.bases_mensais_origem as Record<string, unknown>[];
      if (rows?.[path[1]]) rows[path[1]].base_mensal_integral_confirmada = false;
    }
    onChange([rootKey], next);
  };
  const text = (path: Path, label: string, type = 'text') => <TextField key={JSON.stringify(path)} label={label} type={type} disabled={disabled} error={errorFor(path)} value={String(get(path) ?? '')} onChange={e => set(path, e.target.value)} />;
  const choose = (path: Path, value: string) => {
    if (progression && path.length === 1 && path[0] === 'modalidade') {
      const state = { ...object(root.estado_inicial) };
      if (value === 'DOCENTE') delete state.percentual_iq;
      set([], { ...root, modalidade: value, estado_inicial: state });
      return;
    }
    const field = path.at(-1);
    const obsolete = field === 'formula' && value !== 'VALOR_MENSAL' ? 'valor_mensal'
      : field === 'operacao' && value !== 'ESTORNO' ? 'estorna_id' : null;
    if (!obsolete) { set(path, value); return; }
    const parent = path.slice(0, -1);
    const next = Object.fromEntries(Object.entries(object(get(parent))).filter(([key]) => key !== obsolete));
    set(parent, { ...next, [String(field)]: value });
  };
  const select = (path: Path, label: string, options: Record<string, string>) => <SelectField label={label} disabled={disabled} error={errorFor(path)} value={String(get(path) ?? '')} onChange={e => choose(path, e.target.value)}><option value="">Selecione</option>{Object.entries(options).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</SelectField>;
  const rule = (path: Path) => <>{groupError(path)}<div className="form-grid">{text([...path, 'identificador'], 'Regra ou ato de referência')}{text([...path, 'versao'], 'Versão da regra ou ato')}{text([...path, 'fonte'], 'Fonte da regra')}{structured && <>{text([...path, 'inicio_vigencia'], 'Início da vigência da regra', 'date')}{text([...path, 'fim_vigencia'], 'Fim da vigência da regra (opcional)', 'date')}</>}</div></>;
  const concession = (path: Path) => <>{groupError(path)}<AdditionalConcessionFields value={get(path)} onChange={value => set(path, value)} disabled={disabled} getError={keys => errorFor([...path, ...keys])} /></>;
  const manual = (path: Path, label: string) => <div className="space-y-3"><label><input type="checkbox" checked={Boolean(get(path))} disabled={disabled} aria-invalid={Boolean(errorFor(path)) || undefined} aria-describedby={errorFor(path) ? errorId(path) : undefined} onChange={e => set(path, e.target.checked ? emptyManualValue() : null)} /> {label}</label>{groupError(path)}{Boolean(get(path)) && <div className="form-grid">{text([...path, 'valor'], 'Valor mensal conferido')}{text([...path, 'fonte'], 'Fonte do valor mensal')}{text([...path, 'localizador'], 'Página, aba ou linha da tabela')}{progression && text([...path, 'justificativa'], 'Justificativa da correção individual')}</div>}</div>;
  const position = (path: Path) => <>{groupError(path)}<SalaryPositionFields value={object(get(path)) as SalaryPosition} onChange={value => set(path, value)} disabled={disabled} getError={key => errorFor([...path, key])} allowedCareers={progression ? isTAE ? ['TAE'] : ['MAGISTERIO_SUPERIOR', 'EBTT'] : undefined} /></>;
  const dates = (path: Path) => <div className="form-grid">{text([...path, 'data_documento'], 'Data do documento (opcional)', 'date')}{text([...path, 'data_implantacao'], 'Data de implantação (opcional)', 'date')}</div>;
  const payroll = (path: Path) => <div className="form-grid">{text([...path, 'rubrica'], 'Código da rubrica')}{text([...path, 'natureza_folha'], 'Natureza da folha (conforme a fonte)')}{select([...path, 'natureza_rubrica'], 'Natureza da rubrica', { R: 'Rendimento', D: 'Desconto' })}</div>;
  const salaryShortcut = progression && !isTAE && <Button variant="secondary" disabled={disabled || rubricRows.length + missingSalaryComponents.length > 5 || missingSalaryComponents.length === 0} onClick={() => {
      set(['rubricas'], [...rubricRows, ...missingSalaryComponents.map(formula => ({ rubrica: '', natureza_folha: '', natureza_rubrica: '', formula, regra: emptyRule() }))]);
    }}>{hasAnnuity ? 'Incluir VB, RT e anuênio na diferença' : 'Incluir VB e RT na diferença'}</Button>;
  const eventShortcut = progression && !isTAE && <section className="space-y-3" aria-label="Nova progressão docente">
      <h3 className="subsection-title">Novo enquadramento e data de efeito</h3>
      <p className="help-text">Informe classe e nível de destino e a data dos efeitos financeiros conforme a ata ou portaria. Sem documento, preencha manualmente. A leitura de atas ainda depende de um layout suportado.</p>
      <Button variant="secondary" disabled={disabled || (Array.isArray(root.eventos) && root.eventos.length >= 100)} onClick={() => {
        const origin = object(get(['estado_inicial', 'posicao']));
        const posicao = { ...Object.fromEntries(Object.entries(origin).filter(([key]) => ['carreira', 'vinculo', 'jornada', 'versao_carreira'].includes(key))), classe_docente: '', nivel_docente: '' };
        set([], { ...root, modalidade: 'DOCENTE', eventos: [...(Array.isArray(root.eventos) ? root.eventos : []), { id: crypto.randomUUID(), tipo: 'PROGRESSAO', efeitos_financeiros: '', alteracoes: { posicao }, regra: emptyRule() }] });
      }}>Adicionar novo enquadramento docente</Button>
    </section>;
  const collection = (name: string, label: string, create: () => Record<string, unknown>, render: (path: Path) => React.ReactNode) => {
    const rows = Array.isArray(root[name]) ? root[name] as unknown[] : [];
    return <PeriodCollection label={`${label} (${rows.length})`} initiallyOpen={(!monthly && name === 'rubricas') || (progression && rows.length > 0 && (name === 'reflexos' || (!monthly && name === 'eventos')))} hasError={hasError([name])}>{groupError([name])}
      {rows.map((_, index) => <fieldset key={index} className="space-y-4 border border-outline rounded-lg p-4"><legend>{label}: registro {index + 1}</legend>{groupError([name, index])}{render([name, index])}<Button variant="quiet" disabled={disabled} onClick={() => set([name], rows.filter((_, i) => i !== index))}>Remover {label.toLowerCase()} {index + 1}</Button></fieldset>)}
      {(!monthly || name !== 'reflexos') && <Button variant="secondary" disabled={disabled || rows.length >= (name === 'recebidos' ? 2000 : name === 'rubricas' ? additional ? 1 : progression ? 5 : 20 : 100)} onClick={() => set([name], [...rows, create()])}>Adicionar {label.toLowerCase()}</Button>}
    </PeriodCollection>;
  };
  const modality = select(['modalidade'], 'Modalidade da progressão', { TAE: 'Técnico-administrativo (TAE)', DOCENTE: 'Docente' });
  const destinationField = (path: Path, label: string, type = 'text') => {
    const fullPath = ['eventos', 0, ...path];
    return <TextField label={label} type={type} disabled={disabled} error={errorFor(fullPath)} value={String(get(fullPath) ?? '')}
      onChange={e => set(['eventos'], [setAt(get(['eventos', 0]) ?? emptyDocenteEvent(), path, e.target.value)])} />;
  };
  const annuityPath = ['estado_inicial', 'percentual_anuenio'];
  const annuity = <TextField label="Percentual inicial de anuênio" inputMode="decimal" value={String(get(annuityPath) ?? '')}
    hint={monthly ? 'Informe o percentual. Use 0 quando confirmar que não há anuênio.' : undefined}
    disabled={disabled} error={errorFor(annuityPath)} onChange={e => set(annuityPath, e.target.value)} />;
  const bonus = <>
    {progression && !isTAE && <section className="space-y-3" aria-label="13º e férias da progressão">
      <h3 className="subsection-title">{monthly ? '13º salário' : '13º salário e adicional de férias'}</h3>
      {!monthly && <p className="help-text">Confira data-base, avos e componentes de cada reflexo. Valores observados na ficha aparecem acima; não comprovam o pagamento da diferença.</p>}
      <div className="flex flex-wrap gap-3">{[['DECIMO_TERCEIRO', 'Incluir 13º salário'], ['FERIAS_UM_TERCO', 'Incluir 1/3 de férias']].filter(([tipo]) => !monthly || tipo === 'DECIMO_TERCEIRO').map(([tipo, label]) => <Button key={tipo} variant="secondary" disabled={disabled || (Array.isArray(root.reflexos) && root.reflexos.length >= 100)} onClick={() => set(['reflexos'], [...(Array.isArray(root.reflexos) ? root.reflexos : []), { id: crypto.randomUUID(), tipo, data_base: '', competencia: '', avos: '', rubrica: '', natureza_folha: '', natureza_rubrica: '', formulas_base: [], pagamentos_anteriores: [], regra: emptyRule() }])}>{label}</Button>)}</div>
    </section>}
    {structured && (!monthly || (Array.isArray(root.reflexos) && root.reflexos.length > 0)) && collection('reflexos', 'Reflexos', () => ({ id: crypto.randomUUID(), tipo: '', data_base: '', competencia: '', avos: '', rubrica: '', natureza_folha: '', natureza_rubrica: '', formulas_base: [], pagamentos_anteriores: [], regra: emptyRule() }), path => <>
      <p className="help-text">Componentes distintos podem ter avos próprios. Para a mesma data-base, competência, rubrica, tipo e naturezas, cada componente deve aparecer em uma única parcela.</p>
      {(!monthly || get([...path, 'tipo']) !== 'DECIMO_TERCEIRO') && select([...path, 'tipo'], 'Tipo de reflexo', { FERIAS_UM_TERCO: 'Adicional de 1/3 de férias', DECIMO_TERCEIRO: '13º salário' })}
      <div className="form-grid">{text([...path, 'data_base'], 'Data-base do reflexo', 'date')}{text([...path, 'competencia'], 'Competência do reflexo', 'month')}{text([...path, 'avos'], 'Avos do reflexo (1 a 12)', 'number')}</div>{payroll(path)}
      {(get([...path, 'formulas_base']) as string[] ?? []).includes('ADICIONAL_CONFIRMADO') && <>
        <p className="help-text">Informe os avos conferidos, sem deduzi-los do nome da competência. A origem deve ser a identificação da concessão. Marque os pagamentos anteriores deste reflexo ou confirme a lista vazia na conferência final.</p>
        {text([...path, 'origem'], 'Concessão de origem do reflexo')}
        <div className="form-grid">{text([...path, 'periodo_referencia', 'inicio'], 'Início do período de referência do reflexo', 'date')}{text([...path, 'periodo_referencia', 'ultimo_dia_considerado'], 'Último dia do período de referência do reflexo', 'date')}</div>
        {groupError([...path, 'pagamentos_anteriores'])}
        {(Array.isArray(root.recebidos) ? root.recebidos : []).map((v, index) => { const receipt = object(v); const id = String(receipt.id ?? ''); const selected = (get([...path, 'pagamentos_anteriores']) ?? []) as string[]; return <label className="block" key={index}><input type="checkbox" disabled={disabled} checked={selected.includes(id)} onChange={e => set([...path, 'pagamentos_anteriores'], e.target.checked ? [...selected, id] : selected.filter(v => v !== id))} /> Pagamento anterior {id}: {String(receipt.competencia ?? '')}, rubrica {String(receipt.rubrica ?? '')}, valor {String(receipt.valor ?? '')}</label>; })}
      </>}
      <fieldset className="space-y-2"><legend>Componentes da base do reflexo</legend>{groupError([...path, 'formulas_base'])}{Object.entries(availableFormulas).map(([key, label]) => <label key={key} className="block"><input type="checkbox" disabled={disabled} checked={Array.isArray(get([...path, 'formulas_base'])) && (get([...path, 'formulas_base']) as string[]).includes(key)} onChange={e => { const selected = (get([...path, 'formulas_base']) ?? []) as string[]; set([...path, 'formulas_base'], e.target.checked ? [...selected, key] : selected.filter(item => item !== key)); }} /> {label} na base do reflexo</label>)}</fieldset>{rule([...path, 'regra'])}
    </>)}
  </>;
  return <div className="space-y-6">
    {groupError([])}{groupError(['periodo'])}
    {!monthly && progression && <>{modality}<p className="help-text">A diferença compara a situação após cada evento com a posição de origem e suas referências vigentes. Registre apenas diferenças já pagas nos recebimentos. Complete as posições, datas e regras a partir dos documentos conferidos.</p></>}
    {!monthly && <p className="help-text">Informe o primeiro e o último dia incluídos. Datas de documento e implantação servem à rastreabilidade; cada mudança vale a partir dos efeitos financeiros conferidos pelo RH.</p>}
    <div className="form-grid">{text(['periodo', 'inicio'], 'Início da apuração', 'date')}{text(['periodo', 'ultimo_dia_considerado'], 'Último dia considerado (incluído)', 'date')}{monthly && annuity}</div>
    {monthly && bonus}
    {monthly && <fieldset className="space-y-3"><legend className="subsection-title">Novo enquadramento docente</legend>
      <p className="help-text">Confira a classe, o nível e a data dos efeitos indicados na ata ou portaria. Complete os campos em branco.</p>
      {destinationSource && <p className="help-text">{destinationSource}</p>}
      <fieldset className="space-y-2"><legend className="field-label">Posição de origem</legend>
        {groupError(['estado_inicial', 'posicao'])}
        <p>{[get(['estado_inicial', 'posicao', 'classe_docente']) && `Classe ${get(['estado_inicial', 'posicao', 'classe_docente'])}`,
          get(['estado_inicial', 'posicao', 'nivel_docente']) && `nível ${get(['estado_inicial', 'posicao', 'nivel_docente'])}`,
          get(['estado_inicial', 'posicao', 'jornada'])].filter(Boolean).join(' · ') || 'A identificar'}</p>
        <DocentePositionLookup key={String(get(['periodo', 'inicio']) ?? '')} date={String(get(['periodo', 'inicio']) ?? '')}
          disabled={disabled} position={object(get(['estado_inicial', 'posicao'])) as SalaryPosition} base={originBase}
          title={String(get(['estado_inicial', 'titulacao']) ?? '')} onApply={(posicao, titulacao, automatic) => {
            const estado_inicial = { ...object(root.estado_inicial), posicao, titulacao };
            const original = object(get(['estado_inicial', 'posicao']));
            const next = { ...root, estado_inicial, modalidade: 'DOCENTE' };
            if (automatic) Object.assign(next, { origem_automatica: { data: get(['periodo', 'inicio']), posicao_observada: original,
              ...(original.classe_docente && original.nivel_docente ? {} : { vb: originBase }) } });
            else Reflect.deleteProperty(next, 'origem_automatica');
            set([], next);
          }} />
      </fieldset>
      <div className="form-grid">
        {destinationField(['alteracoes', 'posicao', 'classe_docente'], 'Nova classe')}
        {destinationField(['alteracoes', 'posicao', 'nivel_docente'], 'Novo nível', 'number')}
        {destinationField(['efeitos_financeiros'], 'Início dos efeitos financeiros', 'date')}
      </div>
      <TextField label="Titulação inicial (RT)" hint="Informe o título que servia de base à retribuição no início da apuração. Exemplo: Doutorado."
        disabled={disabled} error={errorFor(['estado_inicial', 'titulacao'])} value={String(get(['estado_inicial', 'titulacao']) ?? '')}
        onChange={e => set(['estado_inicial', 'titulacao'], e.target.value)} />
      <DocentePositionLookup destination key={String(get(['eventos', 0, 'efeitos_financeiros']) ?? '')}
        date={String(get(['eventos', 0, 'efeitos_financeiros']) ?? '')} disabled={disabled}
        position={{ ...object(get(['estado_inicial', 'posicao'])), ...object(get(['eventos', 0, 'alteracoes', 'posicao'])),
          classe_docente: get(['eventos', 0, 'alteracoes', 'posicao', 'classe_docente']), nivel_docente: get(['eventos', 0, 'alteracoes', 'posicao', 'nivel_docente']) } as SalaryPosition}
        title={String(get(['estado_inicial', 'titulacao']) ?? '')}
        onApply={posicao => set(['eventos', 0, 'alteracoes', 'posicao'], posicao)} />
    </fieldset>}
    {children}
    {!monthly && <>
    {progression ? <details><summary className="text-sm">Datas do documento e da implantação (opcionais)</summary>{dates([])}</details> : dates([])}
    {progression && !isTAE && <section className="space-y-4" aria-label="VB da ficha por competência">
      <h3 className="subsection-title">VB da ficha por competência</h3>
      <p className="help-text">Use a base mensal integral da posição paga em cada mês, a partir dos efeitos da progressão. Parcelas proporcionais, estornos ou pagamentos mistos exigem conferência manual. Neste modo, informe todas as competências da apuração, inclusive quando a diferença for zero. RT permanece separada.</p>
      {(Array.isArray(root.bases_mensais_origem) ? root.bases_mensais_origem : []).map((_, index) => <fieldset key={index} className="border border-outline rounded-lg p-4 space-y-3"><legend>Base da ficha: registro {index + 1}</legend>
        {groupError(['bases_mensais_origem', index])}
        <div className="form-grid">{text(['bases_mensais_origem', index, 'competencia'], 'Competência da base mensal', 'month')}{text(['bases_mensais_origem', index, 'vb', 'valor'], 'VB mensal integral conferido (R$)')}{text(['bases_mensais_origem', index, 'vb', 'justificativa'], 'Conferência da base mensal')}</div><details><summary className="text-sm">Fonte da base mensal</summary><div className="form-grid">{text(['bases_mensais_origem', index, 'vb', 'fonte'], 'Fonte da base mensal')}{text(['bases_mensais_origem', index, 'vb', 'localizador'], 'Página ou linha da base mensal')}</div></details>
        <label className="block"><input type="checkbox" disabled={disabled} checked={get(['bases_mensais_origem', index, 'base_mensal_integral_confirmada']) === true} onChange={e => set(['bases_mensais_origem', index, 'base_mensal_integral_confirmada'], e.target.checked)} /> Confirmei que este valor representa a base mensal integral da competência.</label>
        <Button variant="quiet" disabled={disabled} onClick={() => set(['bases_mensais_origem'], (root.bases_mensais_origem as unknown[]).filter((_, i) => i !== index))}>Remover base mensal {index + 1}</Button>
      </fieldset>)}
      <Button variant="secondary" disabled={disabled || (Array.isArray(root.bases_mensais_origem) && root.bases_mensais_origem.length >= 120)} onClick={() => set(['bases_mensais_origem'], [...(Array.isArray(root.bases_mensais_origem) ? root.bases_mensais_origem : []), { id: crypto.randomUUID(), competencia: '', vb: { valor: '', fonte: '', localizador: '', justificativa: '' }, base_mensal_integral_confirmada: false }])}>Adicionar VB por competência manualmente</Button>
    </section>}
    <fieldset className="space-y-4"><legend className="subsection-title">{progression ? 'Posição de origem' : 'Situação no início do período'}</legend>
      {groupError(['estado_inicial'])}
      {position(['estado_inicial', 'posicao'])}
      {text(['estado_inicial', 'titulacao'], progression ? isTAE ? 'Escolaridade inicial' : 'Titulação inicial (RT)' : 'Titulação inicial (N/A quando não houver RT)')}
      {(!structured || progression) && <>{manual(['estado_inicial', 'vb_manual'], 'Informar VB manualmente com fonte conferida')}{(!progression || !isTAE || Boolean(get(['estado_inicial', 'rt_manual']))) && manual(['estado_inicial', 'rt_manual'], 'Informar RT manualmente com fonte conferida')}{progression && <p className="help-text">Correção individual: a referência confirmada e seu valor original serão preservados. Mudança de posição ou titulação exige nova conferência da base.</p>}</>}
      {!additional && <div className="form-grid">{(!progression || isTAE) && text(['estado_inicial', 'percentual_iq'], 'Percentual inicial de IQ')}{!progression && text(['estado_inicial', 'percentual_adicional'], 'Percentual inicial de adicional')}{!monthly && annuity}</div>}
      {!monthly && (progression && !get(['estado_inicial', 'adicional']) ? <details><summary className="text-sm">Adicional com repercussão na progressão (se houver)</summary>{concession(['estado_inicial', 'adicional'])}</details> : concession(['estado_inicial', 'adicional']))}
    </fieldset>
    </>}
    {!monthly && salaryShortcut}
    {!monthly && collection('rubricas', 'Rubricas devidas', () => ({ rubrica: '', natureza_folha: '', natureza_rubrica: '', formula: '', regra: emptyRule() }), path => <>
      {payroll(path)}{select([...path, 'formula'], 'Base de cálculo da rubrica', availableFormulas)}
      {structured && get([...path, 'formula']) === 'ADICIONAL_CONFIRMADO' && <label className="block"><input type="checkbox" checked={get([...path, 'apurar_principal']) !== false} disabled={disabled} onChange={e => set([...path, 'apurar_principal'], e.target.checked)} /> Incluir principal do adicional neste cálculo (desmarque para apurar somente reflexos)</label>}
      {get([...path, 'formula']) === 'VALOR_MENSAL' && manual([...path, 'valor_mensal'], 'Informar o valor mensal e sua fonte')}{rule([...path, 'regra'])}
    </>)}
    {!monthly && eventShortcut}
    {!monthly && collection('eventos', 'Mudanças no período', () => ({ id: crypto.randomUUID(), efeitos_financeiros: '', alteracoes: {}, regra: emptyRule() }), path => {
      if (structured) {
        const kind = String(get([...path, 'tipo']) ?? '');
        const eventTypes = additional ? { POSICAO: 'Mudança de posição ou jornada', RT: 'Mudança de RT', ADICIONAL: 'Mudança de adicional' } : { PROGRESSAO: 'Progressão na carreira', JORNADA: 'Mudança de jornada', ...(isTAE ? { IQ: 'Mudança de IQ' } : { RT: 'Mudança de RT' }), ADICIONAL: 'Mudança de adicional', ANUENIO: 'Mudança de anuênio', BASE: 'Correção individual de VB/RT' };
        return <>{text([...path, 'efeitos_financeiros'], 'Início dos efeitos financeiros', 'date')}{dates(path)}{groupError([...path, 'alteracoes'])}
          <SelectField label="Tipo de mudança" disabled={disabled} error={errorFor([...path, 'tipo'])} value={kind} onChange={e => {
            const tipo = e.target.value;
            const alteracoes = ['PROGRESSAO', 'JORNADA', 'POSICAO'].includes(tipo) ? { posicao: emptySalaryPosition() }
              : tipo === 'IQ' ? { percentual_iq: '', titulacao: '' } : tipo === 'RT' ? { titulacao: '' }
                : tipo === 'ADICIONAL' ? { adicional: emptyAdditional() } : tipo === 'ANUENIO' ? { percentual_anuenio: '' } : {};
            set(path, { ...object(get(path)), tipo, alteracoes });
          }}><option value="">Selecione</option>{Object.entries(eventTypes).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</SelectField>
          {['PROGRESSAO', 'JORNADA', 'POSICAO'].includes(kind) && <fieldset className="space-y-4"><legend>Posição de destino</legend>{position([...path, 'alteracoes', 'posicao'])}{progression && !isTAE && <p className="help-text">VB e RT de destino serão obtidos da referência confirmada vigente nesta data. Uma correção individual exige uma mudança de base explícita.</p>}</fieldset>}
          {kind === 'BASE' && <><p className="help-text">Componentes não alterados mantêm a base anterior. Selecione uma correção ou retorne explicitamente à tabela.</p>{(['vb_manual', ...(!isTAE || get([...path, 'alteracoes', 'rt_manual']) ? ['rt_manual'] : [])]).map(component => <div key={component}>{manual([...path, 'alteracoes', component], `Corrigir ${component === 'vb_manual' ? 'VB' : 'RT'} neste evento`)}<Button variant="quiet" disabled={disabled} onClick={() => set([...path, 'alteracoes', component], null)}>Retornar {component === 'vb_manual' ? 'VB' : 'RT'} à tabela neste evento</Button></div>)}</>}
          {kind === 'IQ' && <>{text([...path, 'alteracoes', 'percentual_iq'], 'Novo percentual de IQ')}{text([...path, 'alteracoes', 'titulacao'], 'Nova escolaridade')}</>}
          {kind === 'RT' && text([...path, 'alteracoes', 'titulacao'], 'Nova titulação (RT)')}
          {kind === 'ADICIONAL' && concession([...path, 'alteracoes', 'adicional'])}
          {kind === 'ANUENIO' && text([...path, 'alteracoes', 'percentual_anuenio'], 'Novo percentual de anuênio')}{rule([...path, 'regra'])}</>;
      }
      const field = Object.keys(object(get([...path, 'alteracoes'])))[0] ?? '';
      return <>{text([...path, 'efeitos_financeiros'], 'Início dos efeitos financeiros', 'date')}{dates(path)}
        {groupError([...path, 'alteracoes'])}
        <SelectField label="Informação alterada" disabled={disabled} value={field} onChange={e => { const field = e.target.value; set([...path, 'alteracoes'], { [field]: field === 'posicao' ? emptySalaryPosition() : ['vb_manual', 'rt_manual'].includes(field) ? null : '' }); }}><option value="">Selecione</option>{Object.entries(changes).map(([key, label]) => <option value={key} key={key}>{label}</option>)}</SelectField>
        {field === 'posicao' ? <>{position([...path, 'alteracoes', field])}<p className="help-text">A nova posição invalida bases manuais anteriores. Informe novos valores em mudanças com a mesma data ou use as referências confirmadas do cadastro.</p></> : ['vb_manual', 'rt_manual'].includes(field) ? manual([...path, 'alteracoes', field], 'Usar valor manual; desmarcado consulta a tabela') : field ? text([...path, 'alteracoes', field], changes[field as keyof typeof changes]) : null}
        {rule([...path, 'regra'])}</>;
    })}
    {!monthly && <>
    {collection('interrupcoes', 'Interrupções', () => ({ id: crypto.randomUUID(), inicio: '', ultimo_dia_considerado: '', regra: emptyRule() }), path => <>
      <div className="form-grid">{text([...path, 'inicio'], 'Primeiro dia da interrupção', 'date')}{text([...path, 'ultimo_dia_considerado'], 'Último dia da interrupção (incluído)', 'date')}</div>{rule([...path, 'regra'])}
    </>)}
    {!monthly && bonus}
    {collection('recebidos', 'Recebimentos', () => ({ id: crypto.randomUUID(), competencia: '', rubrica: '', natureza_folha: '', natureza_rubrica: '', identificador_folha: '', sequencia: '', operacao: '', valor: '', origem: '' }), path => <>
      <p className="help-text">Identificador do lançamento: {String(get([...path, 'id']))}. Em um estorno, use o identificador do pagamento original.</p>
      {text([...path, 'id'], 'Identificador do lançamento')}{text([...path, 'competencia'], 'Competência do recebimento (AAAA-MM)', 'month')}{payroll(path)}
      <div className="form-grid">{text([...path, 'identificador_folha'], 'Identificação da folha')}{text([...path, 'sequencia'], 'Sequência do lançamento')}{select([...path, 'operacao'], 'Tipo do lançamento', { PAGAMENTO: 'Pagamento', COMPLEMENTO: 'Complementação', ESTORNO: 'Estorno' })}{text([...path, 'valor'], 'Valor recebido ou estornado (positivo)')}{text([...path, 'origem'], 'Documento, página ou linha de origem')}</div>
      {get([...path, 'operacao']) === 'ESTORNO' && text([...path, 'estorna_id'], 'Identificador do pagamento estornado')}
    </>)}
    <p className="help-text">{progression ? 'Os recebimentos devem identificar somente diferenças já pagas. Férias e 13º precisam de eventos explícitos; rótulos de meses não geram reflexos.' : 'Sem registros de recebimento, será considerado que nenhum pagamento foi identificado para as competências selecionadas. Confira as fichas antes de confirmar.'}</p>
    </>}
    <label className="block"><input type="checkbox" disabled={disabled} aria-invalid={Boolean(errorFor(['conferido_pelo_rh'])) || undefined} aria-describedby={errorFor(['conferido_pelo_rh']) ? errorId(['conferido_pelo_rh']) : undefined} checked={root.conferido_pelo_rh === true} onChange={e => set(['conferido_pelo_rh'], e.target.checked)} /> Conferi períodos, fontes, parcelas recebidas e regras aplicáveis.{monthly && ' Confirmei o VB e a RT mensais integrais de cada competência e que os documentos utilizados pertencem ao mesmo docente e vínculo.'} A análise do direito foi realizada pelo RH.</label>{groupError(['conferido_pelo_rh'])}
  </div>;
}
