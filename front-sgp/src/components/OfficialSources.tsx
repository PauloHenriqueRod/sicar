import { useEffect, useRef, useState } from 'react';
import { Button, SelectField, TextField } from './ui';
import { SalaryPositionFields } from './SalaryPositionFields';
import { serializeSalaryPosition } from '../utils/salaryReferences';
import type { SalaryPosition } from '../utils/salaryReferences';
import { apiBaseUrl } from '../utils/api';
import { ActionFeedback } from './ActionFeedback';

type Source = { titulo: string; url: string; obtido_em: string; publicado_em: string };
type Line = { id: number; versao: number; dados: SalaryPosition; original: Record<string, unknown>; localizador: string; estado: string; problemas: string[]; referencia_id: number | null; funcao_id: number | null };
type Batch = Source & { id: number; arquivo: string; sha256: string; linhas: Line[]; resumo: Record<string, number>; rejeicoes: Line[] };
type Coverage = { itens: { estrutura_id: number | null; posicao: Record<string, string | number | null>; componente: string; cobertos: { inicio: string; fim: string }[]; lacunas: { inicio: string; fim: string }[] }[]; total_estruturas: number; escopo: string };
type FunctionReference = { id: number; tipo_funcao: string; codigo_funcao: string; modalidade: string; componente: string; valor: string; inicio_vigencia: string; fim_vigencia: string | null; fonte: string };
type OriginRecord = { linha_id: number; lote_id: number; titulo: string; url: string; obtido_em: string; publicado_em: string | null; localizador: string; estado: string; revisado_em: string | null; dados: SalaryPosition };
type ReadRule = { aba: string; linha_inicial?: number; linha_final?: number; colunas: Record<string, string>; contexto: Record<string, string> };
const fields = { tipo: 'Tipo de valor', carreira: 'Carreira', vinculo: 'Vínculo', jornada: 'Jornada', versao_carreira: 'Estrutura histórica', classificacao_tae: 'Classificação TAE', capacitacao_tae: 'Capacitação TAE', padrao_tae: 'Padrão TAE', classe_docente: 'Classe docente', nivel_docente: 'Nível docente', inicio_vigencia: 'Início dos efeitos', fim_vigencia: 'Fim dos efeitos', valor: 'Valor', titulacao: 'Titulação', tipo_funcao: 'CD, FG ou FCC', codigo_funcao: 'Código da função', modalidade: 'Modalidade ou opção', componente: 'Componente da função' };

async function request(path: string, init?: RequestInit) {
  const response = await fetch(`${apiBaseUrl}/api/tabelas/fontes${path}`, { ...init, credentials: 'include', headers: init?.body instanceof FormData ? undefined : { 'Content-Type': 'application/json' } });
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Confira os campos, a origem e as datas informadas.');
  return data;
}

function RecordFields({ data, onChange, disabled }: { data: SalaryPosition; onChange: (data: SalaryPosition) => void; disabled: boolean }) {
  const text = (key: string, label: string, type = 'text') => <TextField key={key} label={label} type={type} value={data[key] ?? ''} disabled={disabled} onChange={e => onChange({ ...data, [key]: e.target.value })} />;
  return <div className="space-y-4">
    <SelectField label="Tipo de valor" value={data.tipo ?? ''} disabled={disabled} onChange={e => {
      const tipo = e.target.value;
      const next: SalaryPosition = { ...data, tipo };
      for (const key of tipo === 'FUNCAO' ? ['carreira', 'vinculo', 'jornada', 'versao_carreira', 'classificacao_tae', 'capacitacao_tae', 'padrao_tae', 'classe_docente', 'nivel_docente', 'titulacao'] : ['tipo_funcao', 'codigo_funcao', 'modalidade', 'componente']) delete next[key];
      if (tipo === 'IQ') for (const key of ['carreira', 'vinculo', 'jornada', 'versao_carreira', 'classificacao_tae', 'capacitacao_tae', 'padrao_tae', 'classe_docente', 'nivel_docente']) delete next[key];
      if (tipo === 'VB') delete next.titulacao;
      onChange(next);
    }}>
      <option value="">Selecione</option><option value="VB">Vencimento básico</option><option value="RT">Retribuição por titulação</option><option value="IQ">Percentual de IQ</option><option value="FUNCAO">Componente de CD/FG/FCC</option>
    </SelectField>
    {data.tipo === 'FUNCAO' ? <div className="form-grid"><SelectField label="Tipo de função" value={data.tipo_funcao ?? ''} disabled={disabled} onChange={e => onChange({ ...data, tipo_funcao: e.target.value })}><option value="">Selecione</option>{['CD', 'FG', 'FCC'].map(v => <option key={v}>{v}</option>)}</SelectField>{text('codigo_funcao', 'Código da função')}{text('modalidade', 'Modalidade ou opção, conforme a fonte')}{text('componente', 'Componente (por exemplo, representação)')}</div> : data.tipo && data.tipo !== 'IQ' ? <SalaryPositionFields value={data} onChange={onChange} disabled={disabled} /> : null}
    <div className="form-grid">{text('inicio_vigencia', 'Início dos efeitos financeiros', 'date')}{text('fim_vigencia', 'Fim dos efeitos (opcional)', 'date')}{text('valor', 'Valor conferido (decimal com ponto)')}{data.tipo === 'RT' && text('titulacao', 'Titulação da RT')}{data.tipo === 'IQ' && text('titulacao', 'Escolaridade do IQ')}</div>
  </div>;
}

export function OfficialSources() {
  const [tab, setTab] = useState('importar');
  const [source, setSource] = useState<Source>({ titulo: '', url: '', obtido_em: '', publicado_em: '' });
  const [file, setFile] = useState<File | null>(null);
  const [rules, setRules] = useState<ReadRule[]>([]);
  const [manual, setManual] = useState<SalaryPosition | null>(null);
  const [manualRecords, setManualRecords] = useState<SalaryPosition[]>([]);
  const [location, setLocation] = useState('');
  const [batch, setBatch] = useState<Batch | null>(null);
  const [history, setHistory] = useState<{ id: number; titulo: string; obtido_em: string }[]>([]);
  const [historyPage, setHistoryPage] = useState(1);
  const [historyTotal, setHistoryTotal] = useState(0);
  const [selected, setSelected] = useState<number[]>([]);
  const [editing, setEditing] = useState<Line | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<{ tone: 'success' | 'error'; message: string } | null>(null);
  const [catalog, setCatalog] = useState<{ titulo: string; url: string; nota: string }[]>([]);
  const [functions, setFunctions] = useState<FunctionReference[]>([]);
  const [coverage, setCoverage] = useState<Coverage | null>(null);
  const coverageVersion = useRef(0);
  const [start, setStart] = useState('2020-01-01');
  const [end, setEnd] = useState('');
  const [coverageKind, setCoverageKind] = useState('SALARIO');
  const [page, setPage] = useState(1);
  const [requestedPosition, setRequestedPosition] = useState<SalaryPosition>({});
  const [requestedTitle, setRequestedTitle] = useState('');
  const [originId, setOriginId] = useState('');
  const [originKind, setOriginKind] = useState('SALARIO');
  const [origins, setOrigins] = useState<{ total: number; itens: OriginRecord[]; nota: string } | null>(null);
  const [originPage, setOriginPage] = useState(1);
  const originVersion = useRef(0);
  useEffect(() => { let active = true; request('/catalogo').then(data => { if (active && Array.isArray(data.fontes)) setCatalog(data.fontes); }).catch(() => {}); return () => { active = false; coverageVersion.current += 1; originVersion.current += 1; }; }, []);
  function invalidateCoverage() { coverageVersion.current += 1; setCoverage(null); setPage(1); }
  function invalidateOrigins() { originVersion.current += 1; setOrigins(null); setOriginPage(1); }
  function show(data: Batch) { const valid = data.linhas.filter(row => row.estado === 'PENDENTE').map(row => row.id); setSelected(current => data.id === batch?.id ? current.filter(id => valid.includes(id)) : valid); setBatch(data); setConfirmed(false); setEditing(null); }
  async function action(work: () => Promise<void>) {
    setBusy(true); setFeedback(null);
    try { await work(); } catch (error) { setFeedback({ tone: 'error', message: (error as Error).message }); } finally { setBusy(false); }
  }
  async function preview(event: React.FormEvent) {
    event.preventDefault();
    await action(async () => {
      const origin = { ...source, publicado_em: source.publicado_em || null };
      if (manual) {
        const rows = [...manualRecords, ...(manual.tipo && (manualRecords.length === 0 || String(manual.valor ?? '').trim()) ? [manual] : [])].map(serializeSalaryPosition);
        if (rows.length === 0) throw new Error('Adicione ao menos um registro manual para gerar a prévia.');
        show(await request('/manual', { method: 'POST', body: JSON.stringify({ origem: origin, linhas: rows, localizador: location }) }));
      } else {
        if (!file) throw new Error('Selecione a fonte ou use o cadastro manual.');
        const leituras = rules.map(rule => ({ ...rule, colunas: Object.fromEntries(Object.entries(rule.colunas).filter(([, value]) => value.trim())), contexto: Object.fromEntries(Object.entries(rule.contexto).filter(([key, value]) => value.trim() && !rule.colunas[key]?.trim())) }));
        const payload = new FormData(); payload.set('arquivo', file); payload.set('metadados', JSON.stringify({ ...origin, leituras }));
        show(await request('/previa', { method: 'POST', body: payload }));
      }
    });
  }
  async function loadPage(target: number) {
    if (tab !== 'funcoes') { await loadCoverage(target); return; }
    await action(async () => {
      setFunctions((await request(`/funcoes?pagina=${target}`)).itens);
      setPage(target);
    });
  }
  async function loadCoverage(target = 1, specific = false) {
    const version = ++coverageVersion.current;
    await action(async () => {
      try {
        const result: Coverage = specific
          ? await request('/cobertura/salarial', { method: 'POST', body: JSON.stringify({ posicao: serializeSalaryPosition(requestedPosition), inicio: start, fim: end, ...(requestedTitle.trim() ? { titulacao: requestedTitle.trim() } : {}) }) })
          : await request(`/cobertura?inicio=${start}&fim=${end}&tipo=${coverageKind}&pagina=${target}`);
        if (version !== coverageVersion.current) return;
        setCoverage(result); setPage(target);
      } catch (error) { if (version === coverageVersion.current) throw error; }
    });
  }
  async function loadOrigins(target: number) {
    const version = ++originVersion.current;
    await action(async () => {
      try {
        const result = await request(`/origens?referencia_id=${encodeURIComponent(originId)}&tipo=${originKind}&pagina=${target}`);
        if (version !== originVersion.current) return;
        setOrigins(result); setOriginPage(target);
      } catch (error) { if (version === originVersion.current) throw error; }
    });
  }
  function downloadRejections() {
    if (!batch) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify({ origem: sourceFromBatch(batch), rejeicoes: batch.rejeicoes }, null, 2)], { type: 'application/json' }));
    const link = document.createElement('a'); link.href = url; link.download = `rejeicoes-fonte-${batch.id}.json`; link.click(); URL.revokeObjectURL(url);
  }
  function sourceFromBatch(item: Batch) { return { titulo: item.titulo, url: item.url, obtido_em: item.obtido_em, publicado_em: item.publicado_em, sha256: item.sha256, arquivo: item.arquivo }; }
  async function activate() {
    if (!batch || !confirmed) return;
    await action(async () => {
      const result = await request(`/${batch.id}/ativar`, { method: 'POST', body: JSON.stringify({ conferido_pelo_rh: true, linhas: batch.linhas.filter(row => selected.includes(row.id)).map(({ id, versao }) => ({ id, versao })) }) });
      show(result); setFeedback({ tone: 'success', message: 'Conferência processada. Verifique ativações, duplicidades e conflitos abaixo.' });
    });
  }
  const sourceField = (key: keyof Source, label: string, type = 'text', required = true) => <TextField label={label} type={type} required={required} disabled={busy} value={source[key]} onChange={e => setSource({ ...source, [key]: e.target.value })} />;
  return <div className="space-y-6">
    <h2 className="section-title">Fontes oficiais e cobertura histórica</h2>
    <p className="help-text">As tabelas ficam no cadastro. Não é necessário anexá-las a cada cálculo. O RH confere a autenticidade, os efeitos financeiros e o direito antes da ativação.</p>
    <SelectField label="Área de fontes oficiais" value={tab} onChange={e => { setTab(e.target.value); invalidateCoverage(); invalidateOrigins(); setFunctions([]); }}><option value="importar">Importar e revisar</option><option value="historico">Prévias salvas</option><option value="origens">Origens por referência</option><option value="funcoes">CD / FG / FCC</option><option value="cobertura">Cobertura e lacunas</option></SelectField>
    {feedback && <ActionFeedback feedback={feedback} />}
    {tab === 'importar' && <>
      <details><summary>Consultar fontes e formatos</summary><p className="help-text">Prefira CSV, XLSX ou ODS equivalentes. Os três layouts PDF remuneratórios analisados têm prévia própria. Imagens e formatos desconhecidos permitem cadastro manual. Publique os dados somente após a conferência.</p>{catalog.map(item => <p key={item.url}><a href={item.url} target="_blank" rel="noreferrer" className="text-primary underline">{item.titulo}</a> — {item.nota}</p>)}<p className="help-text">Colunas reconhecidas: tipo, carreira, vinculo, jornada, versao_carreira, classificacao_tae, capacitacao_tae, padrao_tae, classe_docente, nivel_docente, inicio_vigencia, fim_vigencia, valor, titulacao, tipo_funcao, codigo_funcao, modalidade, componente. Cada linha representa VB, RT, percentual de IQ ou componente de função. O IQ cadastrado não confirma o direito individual.</p></details>
      <form onSubmit={preview} className="form-section space-y-5">
        <div className="form-grid">{sourceField('titulo', 'Identificação da fonte e edição')}{sourceField('url', 'Endereço oficial da fonte', 'url')}{sourceField('obtido_em', 'Data de obtenção', 'date')}{sourceField('publicado_em', 'Data de publicação (opcional)', 'date', false)}</div>
        <p className="help-text">A data de publicação não será usada como início dos efeitos financeiros.</p>
        <SelectField label="Entrada dos valores" disabled={busy} value={manual ? 'manual' : 'arquivo'} onChange={e => { setManual(e.target.value === 'manual' ? {} : null); setManualRecords([]); }}><option value="arquivo">Importar arquivo</option><option value="manual">Cadastro manual conferido</option></SelectField>
        {manual ? <><TextField label="Página ou aba e linha da fonte" required value={location} disabled={busy} onChange={e => setLocation(e.target.value)} /><RecordFields data={manual} onChange={setManual} disabled={busy} /><Button variant="secondary" disabled={busy || !manual.tipo || manualRecords.length >= 1999} onClick={() => { setManualRecords([...manualRecords, manual]); setManual({ ...manual, valor: '', titulacao: '' }); }}>Adicionar outro registro manual</Button>{manualRecords.map((record, index) => <p key={index}>Registro manual {index + 1}: {record.tipo} · {record.valor} <Button variant="quiet" disabled={busy} onClick={() => setManualRecords(manualRecords.filter((_, i) => i !== index))}>Remover registro manual {index + 1}</Button></p>)}</> : <>
          <TextField label="Arquivo da fonte (até 5 MB)" type="file" accept=".csv,.xlsx,.ods,.pdf" disabled={busy} onChange={e => setFile(e.target.files?.[0] ?? null)} />
          <details><summary>Configurar colunas de outra tabela ou valores em colunas distintas</summary><p className="help-text">Crie uma leitura por aba, bloco de linhas e coluna de valor, por exemplo uma para 20h e outra para 40h. Informe os nomes exatos dos cabeçalhos. Valores fixos valem somente para essa leitura e precisam ser conferidos em toda a aba; não use uma única jornada se houver jornadas diferentes nas linhas.</p>
            {rules.map((rule, index) => <fieldset key={index} className="space-y-3 border border-outline p-4"><legend>Leitura {index + 1}</legend><TextField label={`Aba da leitura ${index + 1} (CSV para arquivo CSV; PDF para contexto dos PDFs)`} required value={rule.aba} onChange={e => setRules(rules.map((v, i) => i === index ? { ...v, aba: e.target.value } : v))} />
              {(file?.name.toLowerCase().endsWith('.pdf') || ['PDF', 'anexos_tae', 'comparativo_tae_2025_2026', 'comparativo_magisterio'].includes(rule.aba)) ? <p className="help-text">PDF: o contexto vale para todos os registros do leitor selecionado. Intervalos de linhas não são suportados; ajuste diferenças por registro na prévia. Remova e recrie leituras que tenham intervalos configurados.</p> : (<div className="form-grid"><TextField label={`Primeira linha da leitura ${index + 1} (inclua o cabeçalho)`} type="number" min="1" max="1048576" value={rule.linha_inicial ?? 1} onChange={e => setRules(rules.map((v, i) => i === index ? { ...v, linha_inicial: e.target.value ? Number(e.target.value) : undefined } : v))} /><TextField label={`Última linha da leitura ${index + 1} (opcional)`} type="number" min="1" max="1048576" value={rule.linha_final ?? ''} onChange={e => setRules(rules.map((v, i) => i === index ? { ...v, linha_final: e.target.value ? Number(e.target.value) : undefined } : v))} /></div>)}
              <div className="form-grid">{Object.entries(fields).map(([key, label]) => <div key={key}><TextField label={`${label}: coluna da leitura ${index + 1}`} value={rule.colunas[key] ?? ''} onChange={e => setRules(rules.map((v, i) => i === index ? { ...v, colunas: { ...v.colunas, [key]: e.target.value } } : v))} /><TextField label={`${label}: valor fixo da leitura ${index + 1} (se não houver coluna)`} disabled={Boolean(rule.colunas[key])} value={rule.contexto[key] ?? ''} onChange={e => setRules(rules.map((v, i) => i === index ? { ...v, contexto: { ...v.contexto, [key]: e.target.value } } : v))} /></div>)}</div>
              <Button variant="quiet" onClick={() => setRules(rules.filter((_, i) => i !== index))}>Remover leitura {index + 1}</Button></fieldset>)}
            <Button variant="secondary" onClick={() => setRules([...rules, { aba: '', colunas: {}, contexto: {} }])}>Adicionar leitura de coluna</Button>
          </details>
        </>}
        <Button type="submit" disabled={busy} busy={busy}>Gerar prévia para conferência</Button>
      </form>
      {batch && <section className="space-y-4" aria-label="Prévia da fonte">
        <h3 className="subsection-title">Prévia #{batch.id}: {batch.titulo}</h3><p>Origem: <a href={batch.url} target="_blank" rel="noreferrer">{batch.url}</a> · Obtida em {batch.obtido_em} · Publicação: {batch.publicado_em || 'não informada'}</p><p className="help-text">{Object.entries(batch.resumo).map(([state, count]) => `${state}: ${count}`).join(' · ')}</p>
        <Button variant="secondary" disabled={busy} onClick={() => void action(async () => show(await request(`/${batch.id}`)))}>Atualizar prévia</Button>
        <Button variant="secondary" disabled={busy || batch.rejeicoes.length === 0} onClick={downloadRejections}>Baixar relatório de rejeições</Button><details><summary>Relatório de rejeições e conflitos ({batch.rejeicoes.length})</summary>{batch.rejeicoes.map(row => <p key={row.id}>{row.localizador}: {row.problemas.join(' · ')}</p>)}</details>
        {batch.linhas.map(row => <article key={row.id} className="border border-outline rounded-lg p-4 space-y-3">
          <label><input type="checkbox" disabled={busy || ['ATIVADA', 'DUPLICADA', 'REJEITADA'].includes(row.estado)} checked={selected.includes(row.id)} onChange={e => { setSelected(e.target.checked ? [...selected, row.id] : selected.filter(id => id !== row.id)); setConfirmed(false); }} /> Selecionar registro {row.id}</label>
          <p>{row.localizador} · {row.estado} · {row.dados.tipo ?? 'Tipo pendente'} · Valor: {row.dados.valor ?? 'não extraído'} · Efeitos: {row.dados.inicio_vigencia ?? 'não informados'} até {row.dados.fim_vigencia || 'em aberto'}</p>
          <p className="help-text">{Object.entries(row.dados).filter(([key]) => !['tipo', 'valor', 'inicio_vigencia', 'fim_vigencia'].includes(key)).map(([key, value]) => `${fields[key as keyof typeof fields] ?? key}: ${value}`).join(' · ')}</p>
          <p className="help-text">Destino: {row.referencia_id ? `referência salarial #${row.referencia_id}` : row.funcao_id ? `componente de função #${row.funcao_id}` : 'pendente de ativação'}</p>
          {row.problemas.length > 0 && <p role="status" className="text-danger">{row.problemas.join(' · ')}</p>}
          {!['ATIVADA', 'DUPLICADA'].includes(row.estado) && <Button variant="quiet" disabled={busy} onClick={() => setEditing(structuredClone(row))}>Revisar registro {row.id}</Button>}
          {editing?.id === row.id && <form className="space-y-4" onSubmit={event => { event.preventDefault(); void action(async () => show(await request(`/${batch.id}/linhas/${editing.id}`, { method: 'PUT', body: JSON.stringify({ versao: editing.versao, localizador: editing.localizador, dados: serializeSalaryPosition(editing.dados) }) }))); }}><TextField label="Localização conferida na fonte" required value={editing.localizador} onChange={e => setEditing({ ...editing, localizador: e.target.value })} /><RecordFields data={editing.dados} onChange={dados => setEditing({ ...editing, dados })} disabled={busy} /><Button type="submit" disabled={busy}>Salvar revisão do registro</Button></form>}
        </article>)}
        <label className="block"><input type="checkbox" checked={confirmed} disabled={busy} onChange={e => setConfirmed(e.target.checked)} /> Conferi origem, posição, jornada, efeitos financeiros e valores dos registros selecionados.</label>
        <Button disabled={busy || !confirmed || selected.length === 0} onClick={() => void activate()}>Ativar registros conferidos</Button>
      </section>}
    </>}
    {tab === 'historico' && <section className="space-y-4"><Button disabled={busy} onClick={() => void action(async () => { const result = await request(`?pagina=${historyPage}`); setHistory(result.itens); setHistoryTotal(result.total); })}>Consultar prévias salvas</Button>{history.map(item => <p key={item.id}>#{item.id}: {item.titulo} · {item.obtido_em} <Button variant="quiet" onClick={() => void action(async () => { show(await request(`/${item.id}`)); setTab('importar'); })}>Abrir prévia {item.id}</Button></p>)}<Button disabled={historyPage === 1 || busy} onClick={() => void action(async () => { const target = historyPage - 1; const result = await request(`?pagina=${target}`); setHistory(result.itens); setHistoryTotal(result.total); setHistoryPage(target); })}>Página anterior de prévias</Button><span> Página {historyPage} </span><Button disabled={historyPage * 20 >= historyTotal || busy} onClick={() => void action(async () => { const target = historyPage + 1; const result = await request(`?pagina=${target}`); setHistory(result.itens); setHistoryTotal(result.total); setHistoryPage(target); })}>Próxima página de prévias</Button></section>}
    {tab === 'funcoes' && <section className="space-y-4"><Button disabled={busy} onClick={() => void action(async () => setFunctions((await request(`/funcoes?pagina=${page}`)).itens))}>Consultar componentes de função</Button>{functions.map(item => <p key={item.id}>{item.tipo_funcao} {item.codigo_funcao} · {item.modalidade} · {item.componente}: R$ {item.valor} · {item.inicio_vigencia} até {item.fim_vigencia || 'em aberto'} · {item.fonte}</p>)}<Button disabled={busy || page === 1} onClick={() => void loadPage(page - 1)}>Página anterior de funções</Button><span> Página {page} </span><Button disabled={busy || functions.length < 20} onClick={() => void loadPage(page + 1)}>Próxima página de funções</Button></section>}
    {tab === 'origens' && <section className="space-y-4">
      <div className="form-grid"><TextField label="ID da referência para consultar origem" type="number" min="1" value={originId} onChange={e => { setOriginId(e.target.value); invalidateOrigins(); }} /><SelectField label="Origem de" value={originKind} onChange={e => { setOriginKind(e.target.value); invalidateOrigins(); }}><option value="SALARIO">VB / RT</option><option value="FUNCAO">Componente de CD/FG/FCC</option></SelectField></div>
      <Button disabled={busy || !originId} onClick={() => void loadOrigins(1)}>Consultar origens da referência</Button>
      {origins && <><p className="help-text">{origins.nota}</p>{origins.total === 0 && <p>Nenhuma importação vinculada. Confira a fonte do cadastro manual da referência.</p>}{origins.itens.map(item => <article key={item.linha_id} className="border border-outline p-4"><p><a href={item.url} target="_blank" rel="noreferrer">{item.titulo}</a> · Prévia #{item.lote_id} · {item.localizador}</p><p>{item.dados.tipo} {item.dados.titulacao ?? item.dados.componente ?? ''} · Valor conferido: {item.dados.valor} · {item.estado}</p><p>Obtida em {item.obtido_em} · Publicação: {item.publicado_em ?? 'não informada'} · Revisão: {item.revisado_em ?? 'pendente'}</p></article>)}<Button disabled={busy || originPage === 1} onClick={() => void loadOrigins(originPage - 1)}>Origens anteriores</Button><span> Página {originPage} </span><Button disabled={busy || originPage * 20 >= origins.total} onClick={() => void loadOrigins(originPage + 1)}>Próximas origens</Button></>}
    </section>}
    {tab === 'cobertura' && <section className="space-y-4"><div className="form-grid"><TextField label="Início da cobertura" type="date" value={start} onChange={e => { setStart(e.target.value); invalidateCoverage(); }} /><TextField label="Fim da cobertura" type="date" value={end} onChange={e => { setEnd(e.target.value); invalidateCoverage(); }} /><SelectField label="Cobertura de" value={coverageKind} onChange={e => { setCoverageKind(e.target.value); invalidateCoverage(); }}><option value="SALARIO">VB e RT</option><option value="FUNCAO">CD/FG/FCC por componente</option><option value="IQ">Percentuais de IQ</option></SelectField></div>
      <Button disabled={busy || !start || !end} onClick={() => void loadCoverage()}>Verificar cobertura histórica</Button>
      {coverageKind === 'SALARIO' && <details><summary>Conferir posição ou titulação ausente do cadastro</summary><div className="space-y-4 mt-4"><SalaryPositionFields value={requestedPosition} onChange={value => { setRequestedPosition(value); invalidateCoverage(); }} disabled={busy} /><TextField label="Titulação para conferir RT (opcional)" value={requestedTitle} onChange={e => { setRequestedTitle(e.target.value); invalidateCoverage(); }} /><Button disabled={busy || !start || !end} onClick={() => void loadCoverage(1, true)}>Conferir cobertura da posição informada</Button></div></details>}
      {coverage && <><p className="help-text">{coverage.escopo}</p>{coverage.itens.length === 0 && <p>Nenhuma estrutura cadastrada: a cobertura deste período está pendente.</p>}{coverage.itens.map(item => <article key={`${item.estrutura_id}-${item.componente}`} className="border border-outline p-4"><p>{Object.values(item.posicao).filter(v => v !== null).join(' / ')} · {item.componente}</p><p>Cobertura: {item.cobertos.map(span => `${span.inicio} até ${span.fim}`).join('; ') || 'nenhuma referência confirmada'}</p><p className={item.lacunas.length ? 'text-danger' : 'text-success'}>Lacunas: {item.lacunas.map(span => `${span.inicio} até ${span.fim}`).join('; ') || 'nenhuma neste intervalo e cadastro'}</p></article>)}<Button disabled={busy || page === 1} onClick={() => void loadPage(page - 1)}>Página anterior de cobertura</Button><span> Página {page} </span><Button disabled={busy || page * 20 >= coverage.total_estruturas} onClick={() => void loadPage(page + 1)}>Próxima página de cobertura</Button></>}
    </section>}
  </div>;
}
