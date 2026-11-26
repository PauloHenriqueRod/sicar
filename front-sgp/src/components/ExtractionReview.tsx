import { useState } from 'react';
import { Button, SelectField, TextField } from './ui';
import { reviewField } from '../utils/reviewFields';
import { applyField, appendFinancialCandidate, appendVacation, suggestProgressionIdentification, suggestProgressionOrder, object, fieldTargets, getAt } from '../utils/documentExtraction';
import type { ExtractedDocument, ExtractedField, ExtractionReview as Review, Obj, Path } from '../utils/documentExtraction';

const readerLabels: Record<string, string> = {
  siape_tae: 'Ficha financeira TAE', siape_docente: 'Ficha financeira docente', siape_substituto: 'Ficha financeira de substituto',
  siape_cd: 'Ficha financeira com CD', siape_fg: 'Ficha financeira com FG', siape_financeira: 'Ficha financeira SIAPE',
  cadastro_siapecad_colunas: 'Cadastro funcional SIAPECAD', cadastro_rotulado: 'Cadastro funcional rotulado',
  cacoferias_formulario: 'Programação de férias CACOFERIAS', cacoferias_tabular: 'Programação de férias em tabela',
  portaria_docente_progressao: 'Portaria de progressão docente', portaria_docente_titulacao: 'Portaria de titulação docente',
  portaria_tae_anexo: 'Portaria de mérito TAE com anexo', ato_substituicao: 'Ato de substituição', nao_suportado: 'Formato não reconhecido',
};

export function ExtractionReview({ data, disabled, onChange, linkError }: { linkError?: string; data: Obj; disabled: boolean; onChange: (path: Path, value: unknown) => void }) {
  const review = data.revisao_extracao as Review;
  const identification = suggestProgressionIdentification(data);
  const progressionOrder = suggestProgressionOrder(data);
  const [error, setError] = useState('');
  const [destinations, setDestinations] = useState<Record<string, string>>({});
  const [values, setValues] = useState<Record<string, string>>({});
  const [opened, setOpened] = useState<Record<string, boolean>>({});
  const [offsets, setOffsets] = useState<Record<string, number>>({});
  const [ends, setEnds] = useState<Record<string, string>>({});
  const [reasons, setReasons] = useState<Record<string, string>>({});
  const [groups, setGroups] = useState<Record<string, string>>({});
  const visibleFields = (doc: ExtractedDocument, block: string) => doc.campos.filter(field => {
    if (field.bloco_id !== block) return false;
    const key = field.campo;
    switch (groups[block]) {
      case 'identificacao': return ['nome', 'matricula', 'vinculo', 'regime_juridico', 'jornada', 'jornada_observada'].includes(key);
      case 'posicao': return /cargo|posicao|classe|nivel|titulacao|funcao/.test(key);
      case 'financeiro': return /rubrica|percentual|anuenio/.test(key);
      case 'datas': return /data|inicio|fim|periodo|efeitos|ferias/.test(key);
      default: return true;
    }
  });
  const change = (path: Path, value: unknown) => {
    const next = structuredClone(review);
    let target: unknown = next;
    for (const key of path.slice(0, -1)) target = Array.isArray(target) ? target[Number(key)] : object(target)[key];
    (target as Obj)[String(path.at(-1))] = value;
    if (path[0] !== 'confirmado') next.confirmado = false;
    if (path[0] === 'associacoes' && path.at(-1) !== 'confirmado') next.associacoes[Number(path[1])].confirmado = false;
    onChange(['revisao_extracao'], next);
  };
  const run = (action: () => Obj) => { try { const next = action(); setError(''); onChange([], next); } catch (error) { setError((error as Error).message); } };
  const fieldView = (doc: ExtractedDocument, field: ExtractedField) => {
    const targets = fieldTargets(data, doc, field);
    const selected = targets.find(path => JSON.stringify(path) === destinations[field.id]);
    const current = selected ? getAt(data, selected) : undefined;
    const conflict = selected && ((current !== '' && current != null && String(current) !== (values[field.id] ?? field.correcao?.valor ?? field.valor)) || review.aplicacoes.some(a => JSON.stringify(a.destino) === JSON.stringify(selected)));
    const association = review.associacoes.find(a => a.documento_id === doc.id && a.bloco_id === field.bloco_id);
    const ready = association?.confirmado && association.pessoa !== 'DESCARTADO';
    const fieldLabel = `campo ${doc.campos.findIndex(item => item.id === field.id) + 1} — ${doc.nome_arquivo}`;
    const applied = review.aplicacoes.some(a => a.documento_id === doc.id && a.campo_id === field.id);
    return <div key={field.id} className="border-t border-outline py-3 space-y-2">
      <p className="font-medium">{field.campo === 'rubrica' ? `Rubrica ${field.rubrica} · ${field.competencia ?? 'competência desconhecida'} · ${field.natureza ?? 'natureza desconhecida'} · sequência ${field.sequencia ?? '?'}` : reviewField(field.campo, [field.campo]).label}: {field.valor ?? 'Não encontrado ou ilegível'} <span className="help-text">({field.estado})</span></p>
      <p className="help-text">{field.pagina ? `${doc.nome_arquivo} · página ${field.pagina} · ${field.localizador}` : `Ausência nas páginas ${field.paginas_analisadas?.join(', ') || 'analisadas'}; sem página de origem atribuída.`}</p>
      {field.observado != null && <p className="help-text">Observado: {field.observado}</p>}
      {field.ano_referencia && <p className="help-text">Ano da ficha: {field.ano_referencia}. A data de uma mudança funcional exige confirmação própria.</p>}
      {field.descricao_rubrica && <p className="help-text">Descrição: {field.descricao_rubrica}{field.natureza_origem === 'GRUPO' ? ' · Natureza lida do agrupamento SIAPE.' : ''}</p>}
      {field.sugestao && <p className="help-text">Sugestão derivada; confirme a base e a regra antes de utilizar.</p>}
      {field.parcela && <p className="help-text">Parcela {field.parcela} · Cancelada: {field.cancelada == null ? 'não informado' : field.cancelada ? 'sim' : 'não'}{field.continuacao ? ' · Continuação por interrupção' : ''}{field.data_interrupcao ? ` · Interrupção: ${field.data_interrupcao}` : ''}{field.reinicio ? ` · Reinício informado: ${field.reinicio}` : ''}{field.dias_restantes ? ` · Dias restantes: ${field.dias_restantes}` : ''}. Confira o período efetivamente aplicável.</p>}
      {!!field.candidatos?.length && <p className="help-text">Candidatos para revisão: {field.candidatos.join(' | ')}. O valor permanece vazio até sua decisão.</p>}
      {field.inicio && <p>Programação: {field.inicio} a {field.fim ?? 'fim a confirmar'}. Não comprova gozo ou pagamento.</p>}
      {(field.fim_informado || field.fim_calculado) && <p className="help-text">Fim informado: {field.fim_informado ?? 'ausente ou ilegível'}; fim pelos dias: {field.fim_calculado ?? 'não calculável'}.</p>}
      {field.campo === 'periodo_ferias' && !field.fim && <SelectField label={`Fim escolhido para o ${fieldLabel}`} disabled={disabled || !ready} value={ends[field.id] ?? ''} onChange={e => setEnds({ ...ends, [field.id]: e.target.value })}><option value="">Confira e escolha um candidato</option>{field.fim_informado && <option value={field.fim_informado}>Fim informado: {field.fim_informado}</option>}{field.fim_calculado && field.fim_calculado !== field.fim_informado && <option value={field.fim_calculado}>Fim pelos dias: {field.fim_calculado}</option>}</SelectField>}
      {(field.correcao || field.valor != null || (field.pagina != null && field.estado !== 'AUSENTE' && field.campo !== 'rubrica' && field.campo !== 'periodo_ferias')) && <>
        {field.campo === 'rubrica' && <Button variant="secondary" disabled={disabled || !ready || applied || association?.pessoa === 'TITULAR'} onClick={() => run(() => appendFinancialCandidate(data, doc, field))}>Adicionar rubrica à revisão financeira</Button>}
        {field.campo === 'periodo_ferias' && data.substituicao != null && <Button variant="secondary" disabled={disabled || !ready || applied || field.cancelada === true || !field.inicio || (!field.fim && !ends[field.id])} onClick={() => run(() => appendVacation(data, doc, field, association?.pessoa === 'TITULAR', ends[field.id]))}>Adicionar período para conferir sua aplicação</Button>}
        <div className="form-grid">
          <SelectField label={`Destino do ${fieldLabel}`} value={destinations[field.id] ?? ''} disabled={disabled || !ready} onChange={e => setDestinations({ ...destinations, [field.id]: e.target.value })}>
            <option value="">Escolha o campo do formulário</option>{targets.map(path => <option key={JSON.stringify(path)} value={JSON.stringify(path)}>{path.slice(0, -1).filter(k => typeof k !== 'number').map(k => String(k).replaceAll('_', ' ')).join(' / ')} — {reviewField(path.at(-1)!, path).label}{path.some(k => typeof k === 'number') ? ` (item ${Number(path.find(k => typeof k === 'number')) + 1})` : ''}</option>)}
          </SelectField>
          <TextField label={`Valor a aplicar no ${fieldLabel}`} disabled={disabled || !ready} value={values[field.id] ?? field.correcao?.valor ?? field.valor ?? ''} onChange={e => setValues({ ...values, [field.id]: e.target.value })} />
        </div>
        {conflict && <div className="space-y-2" role="group" aria-label={`Conflito no ${fieldLabel}`}>
          <p>Valor atual: {String(current ?? '')}. Sugestão da fonte: {field.valor ?? 'a revisar'}. Manter o valor atual não exige ação.</p>
          <TextField label={`Justificativa da substituição no ${fieldLabel}`} disabled={disabled || !ready} value={reasons[field.id] ?? ''} onChange={e => setReasons({ ...reasons, [field.id]: e.target.value })} />
          <Button variant="secondary" disabled={disabled || !ready || !reasons[field.id]?.trim() || !(values[field.id] ?? field.correcao?.valor ?? field.valor)} onClick={() => run(() => applyField(data, doc, field, selected!, values[field.id] ?? field.correcao?.valor ?? field.valor ?? '', reasons[field.id], true))}>Substituir valor ou fonte após conferência</Button>
        </div>}
        <Button variant="quiet" disabled={disabled || !ready || !!conflict || !targets.some(path => JSON.stringify(path) === destinations[field.id]) || !(values[field.id] ?? field.correcao?.valor ?? field.valor)} onClick={() => run(() => applyField(data, doc, field, JSON.parse(destinations[field.id]), values[field.id] ?? field.correcao?.valor ?? field.valor ?? ''))}>Aplicar ao campo escolhido</Button>
      </>}
    </div>;
  };
  return <section className="space-y-5 border-t border-outline pt-6" aria-label="Fontes e associação dos documentos">
    <h3 className="subsection-title">Fontes e associação dos documentos</h3>
    <p className="help-text">Confira a pessoa e o vínculo de cada documento antes de usar os valores.</p>
    <details className="text-sm"><summary>Orientações de conferência</summary><p className="help-text mt-2">Campos ausentes podem ser preenchidos manualmente. Portarias são opcionais e limitadas aos formatos suportados. Confira separadamente publicação, data do ato e efeitos financeiros. Rubricas observadas não confirmam concessão nem quitação.</p>{data.progressao != null && <p className="help-text mt-2">Nome e matrícula podem ser sugeridos pela ficha. Complete datas, posição e parcelas com a ata e as referências conferidas; sugestões não confirmam a revisão.</p>}</details>
    {identification !== data && <Button variant="secondary" disabled={disabled} onClick={() => onChange([], identification)}>Preencher identificação a partir da ficha</Button>}
    {progressionOrder !== data && <Button variant="secondary" disabled={disabled} onClick={() => onChange([], progressionOrder)}>Usar sugestões da portaria de progressão</Button>}
    {error && <p role="alert">{error}</p>}
    {!!review.historico_aplicacoes?.length && <details><summary>Histórico de fontes substituídas</summary>{review.historico_aplicacoes.map((item, index) => <p key={index}>{review.documentos.find(doc => doc.id === item.documento_id)?.nome_arquivo} · {item.destino.join(' / ')} · valor anterior aplicado: {item.valor_revisado}</p>)}</details>}
    <TextField label="Vínculo ou contrato deste cálculo" error={linkError} disabled={disabled} value={review.vinculo_calculo} onChange={e => change(['vinculo_calculo'], e.target.value)} />
    {data.substituicao != null && <TextField label="Vínculo do titular" disabled={disabled} value={review.vinculo_titular} onChange={e => change(['vinculo_titular'], e.target.value)} />}
    {review.documentos.map(doc => <details key={doc.id} open className="border-t border-outline py-4 min-w-0">
      <summary className="font-medium break-words">{doc.nome_arquivo}<span className="block help-text">{doc.total_paginas} páginas · {({ CONCLUIDO: 'Leitura concluída', PARCIAL: 'Leitura parcial — confira as pendências', SEM_TEXTO: 'Sem texto para extrair — preencha manualmente', NAO_SUPORTADO: 'Formato sem leitor — preencha manualmente' })[doc.situacao]}</span></summary>
      <details className="mt-3 text-sm"><summary>Detalhes da leitura</summary><p className="help-text">Formato: {doc.layout}. Valores observados: {doc.campos.filter(field => field.valor != null).length}. Ocorrências de rubricas: {doc.campos.filter(field => field.campo === 'rubrica' && field.valor != null).length}.</p>{doc.leitores?.map((reader, index) => <p key={index} className="help-text">{readerLabels[reader.identificador] ?? 'Formato identificado'} · versão {reader.versao} · páginas {reader.paginas.join(', ')}.</p>)}</details>
      {!!doc.avisos.length && <div className="feedback-warning rounded-lg p-3 mt-3" role="note"><p className="font-medium text-sm">Pendências deste documento</p><ul className="list-disc pl-5 text-sm">{doc.avisos.map((warning, index) => <li key={index}>{warning}</li>)}</ul></div>}
      {doc.blocos.map(block => { const index = review.associacoes.findIndex(a => a.documento_id === doc.id && a.bloco_id === block.id); const association = review.associacoes[index]; if (!association) return null; const suffix = `(${doc.nome_arquivo}, bloco ${doc.blocos.indexOf(block) + 1})`; return <fieldset key={block.id} className="space-y-4 mt-5 min-w-0"><legend className="font-medium break-words">{block.nome ?? 'Nome não identificado'}<span className="block help-text">Matrícula {block.matricula ?? 'não identificada'}{block.vinculo ? ` · vínculo ${block.vinculo}` : ''}</span></legend>
        <div className="form-grid"><SelectField label="Pessoa no cálculo" aria-label={`Pessoa no cálculo ${suffix}`} disabled={disabled} value={association.pessoa} onChange={e => change(['associacoes', index, 'pessoa'], e.target.value)}><option value="SERVIDOR">Servidor do cálculo</option>{data.substituicao != null && <option value="TITULAR">Titular da função</option>}<option value="DESCARTADO">Desconsiderar com justificativa</option></SelectField><TextField label="Matrícula associada" aria-label={`Matrícula associada ${suffix}`} disabled={disabled} value={association.matricula} onChange={e => change(['associacoes', index, 'matricula'], e.target.value)} /><TextField label="Vínculo associado" aria-label={`Vínculo associado ${suffix}`} disabled={disabled} value={association.vinculo} onChange={e => change(['associacoes', index, 'vinculo'], e.target.value)} /></div>
        <TextField label="Justificativa da associação ou descarte" aria-label={`Justificativa da associação ou descarte ${suffix}`} disabled={disabled} value={association.justificativa} onChange={e => change(['associacoes', index, 'justificativa'], e.target.value)} />
        <label className="flex gap-2"><input type="checkbox" disabled={disabled} checked={association.confirmado} onChange={e => change(['associacoes', index, 'confirmado'], e.target.checked)} />Conferi pessoa, vínculo e papel deste bloco</label>
        <details open={opened[block.id] ?? false} onToggle={e => { const open = e.currentTarget.open; setOpened(previous => ({ ...previous, [block.id]: open })); }}><summary>Dados observados e campos não encontrados</summary>{opened[block.id] && <>
          <SelectField label={`Grupo de campos (${doc.nome_arquivo}, bloco ${doc.blocos.indexOf(block) + 1})`} value={groups[block.id] ?? 'todos'} onChange={e => { setGroups({ ...groups, [block.id]: e.target.value }); setOffsets({ ...offsets, [block.id]: 0 }); }}><option value="todos">Todos os campos</option><option value="identificacao">Identificação e vínculo</option><option value="posicao">Cargo e posição</option><option value="financeiro">Rubricas e percentuais</option><option value="datas">Datas e períodos</option></SelectField>
          {visibleFields(doc, block.id).slice(offsets[block.id] ?? 0, (offsets[block.id] ?? 0) + 25).map(field => fieldView(doc, field))}
          <div className="flex gap-3 items-center"><Button variant="quiet" disabled={(offsets[block.id] ?? 0) === 0} onClick={() => setOffsets({ ...offsets, [block.id]: Math.max(0, (offsets[block.id] ?? 0) - 25) })}>Campos anteriores</Button><span className="help-text">Campos {visibleFields(doc, block.id).length ? (offsets[block.id] ?? 0) + 1 : 0} a {Math.min((offsets[block.id] ?? 0) + 25, visibleFields(doc, block.id).length)}</span><Button variant="quiet" disabled={(offsets[block.id] ?? 0) + 25 >= visibleFields(doc, block.id).length} onClick={() => setOffsets({ ...offsets, [block.id]: (offsets[block.id] ?? 0) + 25 })}>Próximos campos</Button></div>
        </>}</details>
      </fieldset>; })}
    </details>)}
    {review.aplicacoes.length > 0 && <details><summary>Valores aplicados e correções</summary>{review.aplicacoes.map((application, index) => { const source = review.documentos.find(d => d.id === application.documento_id); const field = source?.campos.find(f => f.id === application.campo_id); return <div key={index} className="space-y-2 border-t py-3"><p className="text-sm break-words">{source?.nome_arquivo} · página {field?.pagina} · {field?.campo}: observado {field?.valor} → utilizado {application.valor_revisado}{application.valor_anterior != null ? ` · valor substituído: ${application.valor_anterior}` : ''}</p><TextField label={`Justificativa da correção ${index + 1}`} disabled={disabled} value={application.justificativa} onChange={e => change(['aplicacoes', index, 'justificativa'], e.target.value)} /><Button variant="quiet" disabled={disabled} onClick={() => change(['aplicacoes'], review.aplicacoes.filter((_, n) => n !== index))}>Remover vínculo com o campo {index + 1}</Button></div>; })}</details>}
    <label className="flex gap-2"><input type="checkbox" disabled={disabled} checked={review.confirmado} onChange={e => change(['confirmado'], e.target.checked)} />Conferi as associações, as fontes e os valores finais aplicados</label>
  </section>;
}
