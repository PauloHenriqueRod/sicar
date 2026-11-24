interface ReviewField {
  label: string;
  help?: string;
  inputMode?: 'decimal' | 'numeric';
  placeholder?: string;
}

const money = (label: string): ReviewField => ({ label: `${label} (R$)`, inputMode: 'decimal', placeholder: 'Ex.: 1234,56 ou 1234.56' });
const percentage = (label: string): ReviewField => ({ label: `${label} (%)`, inputMode: 'decimal', placeholder: 'Ex.: 20' });
const month = (label: string): ReviewField => ({ label, inputMode: 'numeric', help: 'Informe de 1 (janeiro) a 12 (dezembro).' });
const year = (label: string): ReviewField => ({ label, inputMode: 'numeric', placeholder: 'Ex.: 2026' });

const fields: Record<string, ReviewField> = {
  inicio_exercicio: { label: 'Entrada em exercício no cargo' },
  jornada_observada: { label: 'Jornada observada no cadastro' },
  regime_juridico: { label: 'Regime jurídico observado' },
  percentual_iq: percentage('IQ explicitamente informado'),
  percentual_adicional_sugerido: percentage('Percentual sugerido do adicional'),
  codigo_cargo: { label: 'Código do cargo' },
  classe_origem: { label: 'Classe de origem' },
  nivel_origem: { label: 'Nível de origem' },
  identificador_ato: { label: 'Identificador do ato ou portaria' },
  data_publicacao: { label: 'Data de publicação', help: 'Não substitui a data dos efeitos financeiros.' },
  inicio_designacao: { label: 'Início da designação' },
  fim_designacao: { label: 'Fim da designação' },
  codigo_funcao_substituida: { label: 'Código da função substituída' },
  tipo_funcao_substituida: { label: 'Tipo da função substituída' },
  funcao_substituida: { label: 'Denominação da função substituída' },
  classe_destino: { label: 'Classe de destino' },
  nivel_destino: { label: 'Nível de destino' },
  denominacao_destino: { label: 'Denominação de destino' },
  posicao_destino: { label: 'Posição de destino' },
  posicao_origem: { label: 'Posição de origem' },
  titulacao_destino: { label: 'Titulação de destino' },
  nome: { label: 'Nome do servidor' },
  matricula: { label: 'Matrícula SIAPE' },
  cargo_lotacao: { label: 'Cargo e lotação' },
  funcao_exercida: { label: 'Função ou cargo de direção', help: 'Confira o campo “Função/Exerc.” da ficha financeira.' },
  classe: { label: 'Classe na carreira' },
  nivel: { label: 'Nível na carreira', inputMode: 'numeric' },
  titulacao: { label: 'Titulação ou escolaridade', help: 'Na consulta docente, informe a titulação da RT ou N/A quando não houver RT. Para TAE, informe N/A e revise o IQ separadamente.' },
  classe_antiga: { label: 'Classe antes da progressão' },
  nivel_antigo: { label: 'Nível antes da progressão', inputMode: 'numeric' },
  classe_atual: { label: 'Classe após a progressão', help: 'Confira a classe concedida no ato ou na portaria.' },
  nivel_atual: { label: 'Nível após a progressão', inputMode: 'numeric', help: 'Confira o novo nível no ato ou na portaria.' },
  salario_substituta: money('Remuneração da função substituída'),
  salario_propria: money('Remuneração da função própria'),
  salario_mensal: money('Salário mensal do contrato revisado'),
  salario_antigo: money('Vencimento antes da progressão'),
  salario_novo: money('Vencimento após a progressão'),
  vencimento_basico: money('Vencimento básico'),
  dias_substituidos: { label: 'Dias do período de substituição', inputMode: 'numeric' },
  dias_substituicao: { label: 'Dias do período de substituição', inputMode: 'numeric' },
  dias_interrupcao: { label: 'Dias de interrupção', inputMode: 'numeric', help: 'Confira na programação de férias os dias coincidentes com a substituição. Esses dias serão descontados.' },
  mes: month('Mês de referência'),
  ano: year('Ano de referência'),
  mes_rescisao: month('Mês da rescisão'),
  ano_rescisao: year('Ano da rescisão'),
  mes_proporcao: month('Mês do período proporcional'),
  ano_proporcao: year('Ano da progressão'),
  data_exercicio: { label: 'Data de início do exercício', help: 'Confira o campo “EXERCICIO” do cadastro. Use DD/MM/AAAA ou AAAA-MM-DD.', placeholder: 'Ex.: 16/01/2025' },
  data_rescisao: { label: 'Data da rescisão ou fim do contrato', help: 'Confira a data no documento de rescisão. Use DD/MM/AAAA ou AAAA-MM-DD.', placeholder: 'Ex.: 31/08/2026' },
  meses_ferias: { label: 'Avos de férias não gozadas', inputMode: 'decimal', help: 'Se as datas de exercício e rescisão estiverem preenchidas, o sistema calcula os avos a partir delas.' },
  meses_13: { label: 'Avos de 13º salário', inputMode: 'numeric' },
  dias_trabalhados: { label: 'Dias trabalhados no último mês', inputMode: 'numeric' },
  ocorrencias_adicional_ferias: { label: 'Pagamentos anteriores do adicional de férias', inputMode: 'numeric', help: 'Quantidade de ocorrências da rubrica 750 — Férias — Adicional 1/3 CDT no contrato.' },
  quantidade_anuenios: { label: 'Quantidade de anuênios', inputMode: 'numeric', help: 'Confira “T. serv.” no canto superior direito da ficha financeira.' },
  anuenio: percentage('Anuênio'),
  percentual_anuenio: percentage('Anuênio'),
  insalubridade: percentage('Insalubridade'),
  percentual_insalubridade: percentage('Insalubridade'),
  valor_insalubridade: money('Insalubridade recebida'),
  incentivo: percentage('Incentivo à qualificação'),
  percentual_incentivo: percentage('Incentivo à qualificação'),
  incentivo_antigo: { ...percentage('Incentivo antes da progressão'), help: 'Se ficar em branco, será usado o percentual de incentivo à qualificação.' },
  incentivo_novo: { ...percentage('Incentivo após a progressão'), help: 'Se ficar em branco, será usado o percentual de incentivo à qualificação.' },
  meses_diferenca: { label: 'Meses completos com diferença a pagar', inputMode: 'decimal' },
  dias_proporcionais: { label: 'Dias do período proporcional', inputMode: 'numeric' },
  quantidade_reflexos_ferias: { label: 'Quantidade de reflexos no adicional de férias', inputMode: 'decimal' },
  quantidade_reflexos_13: { label: 'Quantidade de reflexos no 13º salário', inputMode: 'decimal' },
  valores_mensais: { label: 'Valores por mês' },
  valores_anuais: { label: 'Contribuições previdenciárias por ano', help: 'Confira os valores da rubrica 98002 — Cont. Plano Seguridade Social na ficha financeira.' },
  valores_recebidos: { label: 'Valores já recebidos', help: 'Confira na ficha financeira o que foi pago no último mês do contrato.' },
  fluxo: { label: 'Diferenças por período' },
  fluxo_mensal: { label: 'Diferenças por período' },
  periodo: { label: 'Período de referência', help: 'Informe a competência em MM/AAAA ou AAAA-MM.', placeholder: 'Ex.: 01/2026' },
  v_dev: money('Valor devido'),
  v_rec: money('Valor recebido'),
  v_abono: money('Abono'),
  v_13: money('13º salário'),
  ab_ferias: money('Adicional de férias'),
  '13_sal': money('13º salário'),
  '742_salario': money('Salário recebido — rubrica 742'),
  '772_ferias': money('Férias recebidas — rubrica 772'),
  '82696_terco_ferias': money('Adicional de férias recebido — rubrica 82696'),
  '82407_decimo_terceiro': money('13º salário recebido — rubrica 82407'),
};

export function reviewField(key: string | number, path: (string | number)[]): ReviewField {
  if (typeof key === 'number') {
    return path[0] === 'valores_anuais' ? money(`Valor ${key + 1} de ${path[1]}`) : { label: `Valor ${key + 1}` };
  }
  const fallback = key.replace(/_/g, ' ');
  const label = fallback.charAt(0).toLocaleUpperCase('pt-BR') + fallback.slice(1);
  if (path[0] === 'valores_mensais' || path[0] === 'valores_recebidos') return money(fields[key]?.label.replace(/ \(R\$\)$/, '') || label);
  return fields[key] || { label };
}
