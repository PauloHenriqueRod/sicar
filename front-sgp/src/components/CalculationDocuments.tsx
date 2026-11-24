import { useId } from 'react';
import type { TipoCalculo } from '../types';

interface DocumentReference {
  name: string;
  purpose: string;
}

// Fontes para a revisão humana; esta lista não define os arquivos de cada lote.
const references: Record<TipoCalculo, DocumentReference[]> = {
  apuracao_periodos: [
    { name: 'Fichas financeiras', purpose: 'Competência, rubrica, natureza, folha e sequência de cada recebimento.' },
    { name: 'Atos e tabelas conferidos', purpose: 'Efeitos financeiros, mudanças de posição, jornada e percentuais.' },
    { name: 'Programação de férias', purpose: 'Intervalos de interrupção, quando aplicáveis.' },
  ],
  substituicao: [
    { name: 'Ficha financeira', purpose: 'Remuneração e função exercida.' },
    { name: 'Ato ou portaria de substituição', purpose: 'Período e função a substituir.' },
    { name: 'Afastamento do titular', purpose: 'Período em que o titular está afastado.' },
    { name: 'Programação de férias', purpose: 'Dias coincidentes com a substituição, descontados como interrupção.' },
    { name: 'Opção remuneratória e alterações', purpose: 'Composição, percentuais, função própria e efeitos financeiros conferidos.' },
  ],
  insalubridade: [
    { name: 'Ficha financeira', purpose: 'VB, RT quando aplicável, adicional e reflexos já pagos.' },
    { name: 'Concessão e alterações', purpose: 'Espécie, percentual, base, vigência e regra do adicional, conferidos pelo RH.' },
  ],
  abono: [
    { name: 'Fichas financeiras e acertos', purpose: 'Contribuição regular (98002), PSS do 13º (98004) e abono recebido por competência, rubrica, folha e sequência, conferidos separadamente.' },
    { name: 'Reconhecimento do direito ou dados conferidos pelo RH', purpose: 'Período dos efeitos financeiros; requerimento e presença de PSS não confirmam automaticamente direito.' },
  ],
  rescisao: [
    { name: 'Ficha financeira', purpose: 'Salário do último mês e adicionais de férias pagos, rubrica 750.' },
    { name: 'Cadastro do servidor', purpose: 'Entrada em exercício, campo “EXERCICIO”.' },
    { name: 'Documento de rescisão ou contrato', purpose: 'Data da rescisão ou término do contrato.' },
    { name: 'Fichas de anos anteriores e acertos', purpose: 'Vincular rubrica 750, base do terço, período aquisitivo, complementos e estornos ao mesmo contrato.' },
    { name: 'Programação de férias, quando pertinente', purpose: 'Períodos para conferência; não comprova sozinha gozo ou pagamento.' },
    { name: 'Referências MGI/RT cadastradas', purpose: 'Bases por vigência, jornada e vínculo; não exigem upload a cada cálculo.' },
  ],
  progressao: [
    { name: 'Ficha financeira', purpose: 'Cargo, nível e remuneração atual.' },
    { name: 'Atos ou portarias de progressão e IQ/RT', purpose: 'Posições e datas de efeitos financeiros de cada mudança, conferidas separadamente.' },
    { name: 'Referências confirmadas da carreira', purpose: 'Origem, destino, jornada, titulação e valores vigentes em cada período.' },
    { name: 'Documentos de férias e 13º', purpose: 'Data-base, avos e componentes de cada reflexo, quando devido.' },
  ],
  exercicio_anterior: [
    { name: 'Fichas financeiras e acertos do período', purpose: 'Competência, rubrica, natureza, folha e sequência dos pagamentos, complementos e estornos.' },
    { name: 'Atos ou portarias do processo e memória do devido', purpose: 'Origem do direito, efeitos financeiros, regra confirmada e valor devido de cada parcela.' },
    { name: 'Comprovantes administrativos ou judiciais, quando fornecidos', purpose: 'Identificação do pagamento e processo, data e vinculação à parcela conferidos pelo RH.' },
  ],
};

export function CalculationDocuments({ tipoCalculo }: { tipoCalculo: TipoCalculo | null }) {
  const titleId = useId();
  if (!tipoCalculo) return null;

  return (
    <section aria-labelledby={titleId} className="mt-5 border-l-2 border-outline pl-4">
      <h3 id={titleId} className="field-label">Documentos para conferência</h3>
      <p className="help-text mt-1">Tenha estas fontes à mão na revisão dos dados.</p>
      <ul className="help-text mt-3 space-y-2">
        {references[tipoCalculo].map(document => (
          <li key={document.name}>
            <span className="font-semibold text-ink">{document.name}:</span> {document.purpose}
          </li>
        ))}
      </ul>
    </section>
  );
}
