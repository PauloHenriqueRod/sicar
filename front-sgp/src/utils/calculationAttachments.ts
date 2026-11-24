import type { TipoCalculo } from '../types';

export interface CalculationAttachment { category: string; file: File }
export interface AttachmentSection { id: string; title: string; description: string }

const financial: AttachmentSection = { id: 'financeira', title: 'Ficha Financeira', description: 'Remuneração, rubricas e pagamentos. Inclua as fichas dos anos necessários do mesmo servidor e vínculo.' };
const act: AttachmentSection = { id: 'ato', title: 'Ato ou portaria', description: 'Concessão, alterações e datas dos efeitos financeiros, quando informadas no documento.' };
const registration: AttachmentSection = { id: 'cadastro', title: 'Cadastro funcional', description: 'Identificação, cargo, vínculo e entrada em exercício.' };
const vacations: AttachmentSection = { id: 'ferias', title: 'Programação de férias', description: 'Períodos para conferência pelo RH; não comprova, por si só, gozo ou pagamento.' };
const other: AttachmentSection = { id: 'outros', title: 'Ata ou outro documento de apoio', description: 'Fonte complementar opcional. Layouts sem leitor suportado exigem preenchimento manual.' };

// As categorias organizam os anexos; não confirmam o conteúdo nem o direito.
export const attachmentSections: Record<TipoCalculo, AttachmentSection[]> = {
  apuracao_periodos: [financial, registration, act, vacations, other],
  progressao: [financial, { id: 'ata', title: 'Ata de progressão', description: 'Informações deliberadas e datas expressamente registradas. A data da reunião não define, por si só, os efeitos financeiros. Layouts sem leitor suportado exigem preenchimento manual.' }, { ...act, title: 'Ato ou portaria de progressão e IQ/RT' }, { id: 'reflexos', title: 'Férias e 13º', description: 'Datas, avos e componentes dos reflexos, quando pertinentes.' }, { ...other, title: 'Outros documentos de apoio' }],
  insalubridade: [financial, { ...act, title: 'Ato ou portaria de concessão do adicional' }, other],
  substituicao: [financial, { ...act, title: 'Ato ou portaria de substituição' }, { id: 'afastamento', title: 'Afastamento do titular', description: 'Documento de apoio com o período de afastamento do titular.' }, { ...vacations, title: 'Férias ou impedimentos do substituto' }, { id: 'opcao', title: 'Opção remuneratória', description: 'Opção, função própria e alterações confirmadas pelo RH.' }, other],
  rescisao: [financial, registration, { id: 'contrato', title: 'Contrato ou documento de rescisão', description: 'Contrato, término, último dia trabalhado e rescisão a partir de, conforme a fonte.' }, vacations, other],
  abono: [financial, { ...act, title: 'Reconhecimento do direito ao abono' }, other],
  exercicio_anterior: [financial, act, { id: 'pagamentos', title: 'Comprovantes e memória do devido', description: 'Pagamentos administrativos ou judiciais e memória do devido, quando fornecidos.' }, other],
};
