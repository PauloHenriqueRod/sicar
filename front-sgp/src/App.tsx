import { apiBaseUrl } from './utils/api';
import { useState, useRef, useEffect } from 'react';
import { Sidebar } from './components/Sidebar';
import { Header } from './components/Header';
import { Historico } from './components/Historico';
import { Login } from './components/Login';
import { GestaoUsuarios } from './components/GestaoUsuarios';
import { AuditoriaLogs } from './components/AuditoriaLogs';
import { GestaoTabelas } from './components/GestaoTabelas';
import { FileUpload } from './components/FileUpload';
import { RevisaoDadosForm } from './components/RevisaoDadosForm';
import { ResultadoCalculo } from './components/ResultadoCalculo';
import { AlterarSenhaModal } from './components/AlterarSenhaModal';
import { LandingPage } from './components/LandingPage';
import { Dashboard } from './components/Dashboard';
import { CalculationSteps } from './components/CalculationSteps';
import { DocumentAttachments } from './components/DocumentAttachments';
import type { CalculationAttachment } from './utils/calculationAttachments';
import { OnboardingGuide } from './components/OnboardingGuide';
import { ActionFeedback } from './components/ActionFeedback';
import type { Feedback } from './components/ActionFeedback';
import type { TipoCalculo, CalculationItem } from './types';
import { prepareReviewData, serializeReviewData } from './utils/reviewData';
import { Button, Modal } from './components/ui';
import { invalidateDocenteOrigin, missingProgressionInputs } from './utils/progressionReviewValidation';
import { apiErrorDetails } from './utils/apiErrors';
import { mergeExtractions, suggestFinancialOrigin, suggestProgressionIdentification, suggestProgressionOrder, syncApplications, onlyGlobalApprovalChanged } from './utils/documentExtraction';
import type { ExtractedDocument, ExtractionReview } from './utils/documentExtraction';

const updateIn = (obj: unknown, path: (string | number)[], value: unknown): unknown => {
  if (path.length === 0) return value;
  const key = path[0];
  const rest = path.slice(1);
  if (Array.isArray(obj)) {
    const newArr = [...obj];
    newArr[key as number] = updateIn(newArr[key as number], rest, value);
    return newArr;
  }
  const newObj: Record<string, unknown> = { ...(obj && typeof obj === 'object' ? obj : {}) };
  newObj[key as string] = updateIn(newObj[key as string], rest, value);
  return newObj;
};


const guideStorageKey = (username: string) => `sgp:guide:v1:${encodeURIComponent(username)}`;
const sessionEventKey = 'sgp:session-event';
const sessionFingerprint = () => JSON.stringify(['isLoggedIn', 'username', 'role', 'sgp:logout-pending', sessionEventKey].map(key => localStorage.getItem(key)));

export default function App() {
  const [isLoggedIn, setIsLoggedIn] = useState(localStorage.getItem('isLoggedIn') === 'true');
  const [userRole, setUserRole] = useState<string | null>(localStorage.getItem('role'));
  const [showLanding, setShowLanding] = useState(true);
  const [showGuide, setShowGuide] = useState(() => localStorage.getItem(guideStorageKey(localStorage.getItem('username') || '')) !== 'seen');
  const [focusGuide, setFocusGuide] = useState(false);
  const [guideOpenCount, setGuideOpenCount] = useState(0);
  const guideTriggerRef = useRef<HTMLButtonElement>(null);
  const [activeTab, setActiveTab] = useState<'dashboard' | 'calculo' | 'historico' | 'usuarios' | 'auditoria' | 'tabelas'>('dashboard');
  const [isSidebarOpen, setIsSidebarOpen] = useState(() => window.innerWidth >= 768);
  const [tipoCalculo, setTipoCalculo] = useState<TipoCalculo | null>(null);
  const [attachments, setAttachments] = useState<CalculationAttachment[]>([]);
  const files = attachments.map(item => item.file);
  const [fileProgress, setFileProgress] = useState<{ filename: string; status: string }[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [currentItem, setCurrentItem] = useState<CalculationItem | null>(null);
  const hasReview = currentItem !== null;
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [showDiscardConfirmation, setShowDiscardConfirmation] = useState(false);
  const [sessionSyncing, setSessionSyncing] = useState(false);
  const sessionMarker = useRef(sessionFingerprint());
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const workspaceRef = useRef<HTMLElement>(null);
  const [isExporting, setIsExporting] = useState(false);
  const [isDarkMode, setIsDarkMode] = useState(() => {
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme) {
      return savedTheme === 'dark';
    }
    // Caso não tenha preferência salva, verifica o tema do sistema/navegador
    return window.matchMedia('(prefers-color-scheme: dark)').matches;
  });
  const [showAlterarSenha, setShowAlterarSenha] = useState(false);
  const sessionVersion = useRef(0);
  const pendingRequests = useRef(new Set<AbortController>());
  const [logoutState, setLogoutState] = useState<'idle' | 'pending' | 'error'>(() => localStorage.getItem('sgp:logout-pending') === 'true' ? 'error' : 'idle');
  const [logoutError, setLogoutError] = useState('O encerramento da sessão ainda não foi confirmado. Tente novamente.');
  const logoutRequest = useRef<AbortController | null>(null);
  const publishSessionChange = () => {
    localStorage.setItem(sessionEventKey, crypto.randomUUID());
    sessionMarker.current = sessionFingerprint();
  };

  const invalidateOperations = () => {
    sessionVersion.current += 1;
    pendingRequests.current.forEach(controller => controller.abort());
    pendingRequests.current.clear();
  };
  const beginOperation = () => {
    const version = sessionVersion.current;
    const controller = new AbortController();
    pendingRequests.current.add(controller);
    return { controller, isCurrent: () => version === sessionVersion.current && !controller.signal.aborted };
  };

  useEffect(() => {
    const requests = pendingRequests.current;
    return () => {
      sessionVersion.current += 1;
      requests.forEach(controller => controller.abort());
      requests.clear();
    };
  }, []);

  useEffect(() => {
    if (workspaceRef.current) workspaceRef.current.scrollTop = 0;
  }, [activeTab, hasReview]);

  useEffect(() => {
    if (isDarkMode) {
      document.documentElement.classList.add('dark');
      localStorage.setItem('theme', 'dark');
    } else {
      document.documentElement.classList.remove('dark');
      localStorage.setItem('theme', 'light');
    }
  }, [isDarkMode]);

  // Listener para mudar o tema caso a preferência do sistema mude e o usuário não tenha definido manualmente
  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    const handleChange = (e: MediaQueryListEvent) => {
      // Só muda automaticamente se o usuário não tiver salvo uma preferência manual ainda
      if (!localStorage.getItem('theme')) {
        setIsDarkMode(e.matches);
      }
    };

    mediaQuery.addEventListener('change', handleChange);
    return () => mediaQuery.removeEventListener('change', handleChange);
  }, []);

  // Listener de inatividade (10 minutos)
  useEffect(() => {
    if (!isLoggedIn) return;

    let timeoutId: number;

    const resetTimer = () => {
      clearTimeout(timeoutId);
      // 45 minutos
      timeoutId = window.setTimeout(() => {
        void handleLogout();
      }, 45 * 60 * 1000);
    };

    const events = ['mousemove', 'keydown', 'scroll', 'click'];
    events.forEach(event => window.addEventListener(event, resetTimer));
    resetTimer();

    return () => {
      clearTimeout(timeoutId);
      events.forEach(event => window.removeEventListener(event, resetTimer));
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isLoggedIn]);

  // Interceptador Global de Fetch para Erros 401 (Sessão Expirada)
  useEffect(() => {
    if (!isLoggedIn) return;
    
    const originalFetch = window.fetch;
    window.fetch = async (...args) => {
      const version = sessionVersion.current;
      const response = await originalFetch(...args);
      
      if (response.status === 401) {
        const url = typeof args[0] === 'string' ? args[0] : args[0] instanceof Request ? args[0].url : '';
        // Evita loop infinito se o próprio logout retornar 401
        if (version === sessionVersion.current && !url.includes('/api/auth/login') && !url.includes('/api/auth/logout') && !url.endsWith('/api/auth/me')) {
          void handleLogout();
        }
      }
      return response;
    };

    return () => {
      window.fetch = originalFetch;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isLoggedIn]);

  const handleExportPDF = async () => {
    if (!currentItem || !tipoCalculo) return;
    if (!currentItem.resultado_calculo || !currentItem.historico_id) return;
    const operation = beginOperation();

    setIsExporting(true);
    setError(null);
    setFeedback({ tone: 'loading', message: 'Gerando relatório em PDF...', detail: 'Aguarde. O download será solicitado ao navegador.' });

    try {
      const response = await fetch(`${apiBaseUrl}/api/exportar-pdf`, {
        signal: operation.controller.signal,
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json'
        },
        credentials: 'include',
        body: JSON.stringify({
          historico_id: currentItem.historico_id
        }),
      });

      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(typeof body?.detail === 'string' ? body.detail : 'Tente baixar novamente.');
      }

      const blob = await response.blob();
      if (!operation.isCurrent()) return;
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `Relatorio_Oficial_${currentItem.filename.replace('.pdf', '')}_${new Date().getTime()}.pdf`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      a.remove();
      setFeedback({ tone: 'success', message: 'PDF gerado. Download solicitado ao navegador.', detail: 'Confira o aviso do navegador ou a pasta de downloads.' });
    } catch (err: unknown) {
      if (!operation.isCurrent()) return;
      setFeedback(null);
      setError('Não foi possível gerar o PDF. ' + (err instanceof Error ? err.message : 'Tente baixar novamente.'));
    } finally {
      pendingRequests.current.delete(operation.controller);
      if (operation.isCurrent()) setIsExporting(false);
    }
  };

  const startManualReview = () => {
    if (currentItem) return;
    setAttachments([]);
    if (tipoCalculo) {
      setFileProgress([]);
      setCurrentItem({ filename: tipoCalculo === 'substituicao' ? 'Processo de substituição' : tipoCalculo === 'exercicio_anterior' ? 'Exercícios anteriores por parcelas' : tipoCalculo === 'abono' ? 'Processo de abono de permanência' : tipoCalculo === 'rescisao' ? 'Processo de rescisão' : tipoCalculo === 'insalubridade' ? 'Adicionais por concessão' : tipoCalculo === 'progressao' ? 'Progressão por eventos' : 'Apuração por períodos', dados_extraidos: prepareReviewData(tipoCalculo, {}), historico_id: null, resultado_calculo: null });
      setError(null); setFieldErrors({});
      setFeedback({ tone: 'success', message: 'Preencha os períodos, eventos e recebimentos para conferência.' });
      return;
    }
  };

  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (tipoCalculo && files.length === 0) { startManualReview(); return; }
    if (files.length === 0 || !tipoCalculo) return;
    const operation = beginOperation();
    setIsUploading(true);
    setError(null);
    setFeedback({ tone: 'loading', message: 'Extraindo os dados dos documentos...', detail: 'Aguarde para iniciar a conferência.' });
    setFileProgress(files.map(file => ({ filename: file.name, status: 'Enviado; aguardando resposta da extração' })));
    const formData = new FormData();
    formData.append('tipo_calculo', tipoCalculo);
    formData.append('versao_extracao', '2');
    files.forEach(f => formData.append('arquivos', f));
    formData.append('metadados_arquivos', JSON.stringify(attachments.map(item => ({ id: crypto.randomUUID(), categoria: item.category }))));

    try {
      const response = await fetch(`${apiBaseUrl}/api/extrair-pdf`, {
        signal: operation.controller.signal,
        method: 'POST',
        credentials: 'include',
        body: formData,
      });
      if (!response.ok) {
        const failure = await response.json().catch(() => null);
        throw new Error(typeof failure?.detail === 'string' ? failure.detail : 'Não foi possível extrair os dados. Confira os PDFs e tente novamente.');
      }
      const result = await response.json();
      if (!operation.isCurrent()) return;
      setFileProgress([...(result.resultados ?? []).map((item: { filename: string; extracao?: ExtractedDocument }) => ({ filename: item.filename, status: item.extracao?.situacao ?? 'Interpretado; confira os dados' })), ...(result.falhas ?? []).map((item: { filename: string; mensagem: string }) => ({ filename: item.filename, status: `Falha: ${item.mensagem}. Preenchimento manual disponível.` }))]);
      
      let nextItem: CalculationItem;
      if (result.versao_contrato === 2) {
        const previous = currentItem?.dados_extraidos;
        let prepared = previous ? structuredClone(previous) : prepareReviewData(tipoCalculo, {});
        if (currentItem?.historico_id) prepared.substitui_historico_id = currentItem.historico_id;
        const sources = mergeExtractions(prepared.revisao_extracao as ExtractionReview | undefined, result.resultados.map((item: { extracao: ExtractedDocument }) => item.extracao));
        if (sources.documentos.length) prepared.revisao_extracao = sources;
        if (tipoCalculo === 'progressao' && !previous) prepared = suggestFinancialOrigin(suggestProgressionOrder(suggestProgressionIdentification(prepared)));
        else if (tipoCalculo === 'progressao' && sources.documentos.some(doc =>
          !(previous?.revisao_extracao as ExtractionReview | undefined)?.documentos.some(old => old.id === doc.id) &&
          doc.campos.some(f => f.leitor_id === 'portaria_docente_progressao'))) prepared = suggestProgressionOrder(prepared);
        else if (tipoCalculo === 'progressao' && sources.documentos.some(doc => doc.layout === 'FICHA_SIAPE' &&
          !(previous?.revisao_extracao as ExtractionReview | undefined)?.documentos.some(old => old.id === doc.id))) prepared = suggestFinancialOrigin(suggestProgressionIdentification(prepared));
        prepared = invalidateDocenteOrigin(prepared);
        for (const name of ['apuracao', 'progressao', 'adicionais', 'substituicao', 'rescisao', 'abono', 'exercicios']) if (prepared[name]) prepared[name] = { ...(prepared[name] as Record<string, unknown>), conferido_pelo_rh: false };
        nextItem = { filename: 'Processo com fontes documentais', dados_extraidos: prepared, resultado_calculo: null, historico_id: null, falhas_extracao: result.falhas ?? [] };
      } else if (tipoCalculo === 'exercicio_anterior' && result.resultados.some((doc: Record<string, unknown>) => doc.candidatos_exercicios !== undefined)) {
        const prepared = prepareReviewData('exercicio_anterior', {});
        const docs = result.resultados as { filename: string; dados_extraidos?: Record<string, unknown>; candidatos_exercicios?: unknown[] }[];
        prepared.alertas_extracao = ['Documentos agrupados em um processo. Confira vínculo, origem do direito e cada candidato antes de calcular.', ...docs.flatMap(doc => (Array.isArray(doc.dados_extraidos?.alertas_extracao) ? doc.dados_extraidos.alertas_extracao : []).map(note => `${doc.filename}: ${note}`))].slice(0, 100);
        (prepared.exercicios as Record<string, unknown>).documentos = docs.map(doc => ({ id: crypto.randomUUID(), nome_arquivo: doc.filename, vinculo_identificado: '', vinculo_confirmado: false, candidatos: doc.candidatos_exercicios ?? [], ...(doc.dados_extraidos?.matricula && doc.dados_extraidos.matricula !== 'N/A' ? { matricula_identificada: doc.dados_extraidos.matricula } : {}) }));
        nextItem = { filename: 'Exercícios anteriores por parcelas', dados_extraidos: prepared, historico_id: null, resultado_calculo: null };
      } else if (tipoCalculo === 'abono') {
        const prepared = prepareReviewData('abono', {});
        const docs = result.resultados as { filename: string; dados_extraidos?: Record<string, unknown>; observacoes_abono?: unknown[] }[];
        prepared.alertas_extracao = ['Documentos agrupados em um processo. Confirme a pessoa e o vínculo de cada fonte; classifique ou exclua com justificativa todas as observações.', ...docs.flatMap(doc => (prepareReviewData('abono', doc.dados_extraidos ?? {}).alertas_extracao as string[]).map(note => `${doc.filename}: ${note}`))].slice(0, 100);
        (prepared.abono as Record<string, unknown>).documentos = docs.map(doc => ({ id: crypto.randomUUID(), nome_arquivo: doc.filename, vinculo_identificado: '', vinculo_confirmado: false, observacoes: doc.observacoes_abono ?? [], ...(doc.dados_extraidos?.matricula && doc.dados_extraidos.matricula !== 'N/A' ? { matricula_identificada: doc.dados_extraidos.matricula } : {}) }));
        nextItem = { filename: 'Processo de abono de permanência', dados_extraidos: prepared, historico_id: null, resultado_calculo: null };
      } else if (tipoCalculo === 'rescisao') {
        const prepared = prepareReviewData('rescisao', {});
        const docs = result.resultados as { filename: string; dados_extraidos?: Record<string, unknown>; fontes_rescisao?: Record<string, unknown> }[];
        prepared.alertas_extracao = ['Documentos agrupados para um único contrato. Confira pessoa, vínculo e contrato em cada fonte; divergências precisam ser resolvidas manualmente.', ...docs.flatMap(doc => (prepareReviewData('rescisao', doc.dados_extraidos ?? {}).alertas_extracao as string[]).map(note => `${doc.filename}: ${note}`))].slice(0, 100);
        (prepared.rescisao as Record<string, unknown>).documentos = docs.map(doc => ({ id: crypto.randomUUID(), nome_arquivo: doc.filename, papel: '', contrato_identificado: '', vinculo_confirmado: false, candidatos: doc.fontes_rescisao?.candidatos ?? [], pagamentos_observados: doc.fontes_rescisao?.pagamentos_observados ?? [], ...(doc.dados_extraidos?.matricula && doc.dados_extraidos.matricula !== 'N/A' ? { matricula_identificada: doc.dados_extraidos.matricula } : {}) }));
        nextItem = { filename: 'Processo de rescisão', dados_extraidos: prepared, historico_id: null, resultado_calculo: null };
      } else if (tipoCalculo === 'substituicao') {
        const prepared = prepareReviewData('substituicao', {});
        const documents = result.resultados as { filename: string; dados_extraidos?: Record<string, unknown>; candidatos_substituicao?: unknown[]; pagamentos_observados?: unknown[] }[];
        const identifications = new Set(documents.map(r => String(r.dados_extraidos?.matricula ?? '')).filter(v => v && v !== 'N/A'));
        prepared.alertas_extracao = ['Os documentos foram agrupados em um processo. Identifique titular/substituto, confira o papel de cada documento e aplique os períodos extraídos. Preencha manualmente os campos ausentes.', ...(identifications.size > 1 ? ['Há matrículas diferentes entre os documentos. Confira quais pertencem ao titular e ao substituto.'] : []), ...documents.flatMap(r => (prepareReviewData('substituicao', r.dados_extraidos ?? {}).alertas_extracao as string[]).map(note => `${r.filename}: ${note}`))].slice(0, 100);
        const plan = prepared.substituicao as Record<string, unknown>;
        plan.documentos = documents.map(r => ({ id: crypto.randomUUID(), nome_arquivo: r.filename, candidatos: r.candidatos_substituicao ?? [], pagamentos_observados: r.pagamentos_observados ?? [], ...(r.dados_extraidos?.nome && r.dados_extraidos.nome !== 'N/A' ? { nome_identificado: r.dados_extraidos.nome } : {}), ...(r.dados_extraidos?.matricula && r.dados_extraidos.matricula !== 'N/A' ? { matricula_identificada: r.dados_extraidos.matricula } : {}) }));
        nextItem = { filename: 'Processo de substituição', dados_extraidos: prepared, historico_id: null, resultado_calculo: null };
      } else {
        if (result.resultados.length !== 1) throw new Error('A extração deve gerar uma revisão de um servidor por vez. Confira os documentos ou continue com preenchimento manual.');
        const [document] = result.resultados;
        nextItem = { filename: document.filename, dados_extraidos: prepareReviewData(tipoCalculo, document.dados_extraidos ?? {}), historico_id: null, resultado_calculo: null };
      }
      setCurrentItem(nextItem);
      setAttachments([]);
      if (result.versao_contrato === 2) {
        const recognized = result.resultados.filter((item: { extracao: ExtractedDocument }) => !['SEM_TEXTO', 'NAO_SUPORTADO'].includes(item.extracao.situacao)).length;
        setFeedback({ tone: recognized && !result.falhas?.length ? 'success' : 'warning', message: recognized ? `${recognized} arquivos interpretados; ${result.falhas?.length ?? 0} com falha.` : 'Nenhum arquivo foi interpretado. O preenchimento manual continua disponível.', detail: 'Confira a situação de cada arquivo e as fontes antes de confirmar o cálculo.' });
      } else {
        const count = result.resultados.length;
        setFeedback({ tone: 'success', message: `Dados extraídos de ${count} ${count === 1 ? 'documento' : 'documentos'}.`, detail: 'Confira os campos antes de confirmar o cálculo.' });
      }
    } catch (err: unknown) {
      if (!operation.isCurrent()) return;
      setFileProgress(files.map(file => ({ filename: file.name, status: 'Extração não concluída. Tente novamente ou preencha manualmente.' })));
      setFeedback(null);
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      pendingRequests.current.delete(operation.controller);
      if (operation.isCurrent()) setIsUploading(false);
    }
  };

  const handleCalculate = async () => {
    if (!currentItem?.dados_extraidos || !tipoCalculo) return;
    const missing = missingProgressionInputs(currentItem.dados_extraidos);
    if (Object.keys(missing).length) {
      setFeedback(null);
      setError(null);
      setFieldErrors(missing);
      return;
    }
    const operation = beginOperation();
    const idempotencyKey = currentItem.idempotency_key ?? crypto.randomUUID();
    setCurrentItem({ ...currentItem, idempotency_key: idempotencyKey });

    setIsUploading(true);
    setError(null);
    setFieldErrors({});
    setFeedback({ tone: 'loading', message: `Calculando ${currentItem.filename}...`, detail: 'Aguarde para consultar o resultado.' });
    try {
      const response = await fetch(`${apiBaseUrl}/api/calcular`, {
        signal: operation.controller.signal,
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json'
        },
        credentials: 'include',
        body: JSON.stringify({
          tipo_calculo: tipoCalculo,
          idempotency_key: idempotencyKey,
          dados_extraidos: serializeReviewData(currentItem.dados_extraidos)
        })
      });
      if (!response.ok) {
        const failure = await response.json().catch(() => null);
        const validation = apiErrorDetails(failure, 'Falha no cálculo');
        if (operation.isCurrent()) setFieldErrors(validation.fields);
        throw new Error(validation.message);
      }
      const result = await response.json();
      if (!Number.isInteger(result.historico_id) || result.historico_id <= 0) {
        throw new Error('O servidor não confirmou o registro do cálculo. Tente novamente.');
      }
      
      if (!operation.isCurrent()) return;
      setCurrentItem({
        ...currentItem,
        idempotency_key: idempotencyKey,
        resultado_calculo: result,
        historico_id: result.historico_id
      });
      setFeedback({ tone: 'success', message: `Cálculo concluído para ${currentItem.filename}.`, detail: 'Confira o resultado e baixe o relatório em PDF.' });
    } catch (err: unknown) {
      if (!operation.isCurrent()) return;
      setFeedback(null);
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      pendingRequests.current.delete(operation.controller);
      if (operation.isCurrent()) setIsUploading(false);
    }
  };

  const resetAll = () => {
    setFileProgress([]);
    setFieldErrors({});
    setShowDiscardConfirmation(false);
    setTipoCalculo(null);
    setAttachments([]);
    setCurrentItem(null);
    setError(null);
    setFeedback(null);
    setIsUploading(false);
    setIsExporting(false);
  };

  const discardAndStart = () => {
    resetAll();
    setActiveTab('calculo');
    if (window.innerWidth < 768) setIsSidebarOpen(false);
  };

  const hasPendingReview = currentItem ? !currentItem.resultado_calculo : files.length > 0;
  const startNewCalculation = () => {
    if (isUploading || isExporting) return;
    if (hasPendingReview) setShowDiscardConfirmation(true);
    else discardAndStart();
  };

  useEffect(() => {
    if (!hasPendingReview) return;
    const preventDiscard = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
    window.addEventListener('beforeunload', preventDiscard);
    return () => window.removeEventListener('beforeunload', preventDiscard);
  }, [hasPendingReview]);

  const handleChangeData = (path: (string | number)[], val: unknown) => {
    if (!currentItem) return;
    let novoDados = updateIn(currentItem.dados_extraidos, path, val) as Record<string, unknown>;
    novoDados = invalidateDocenteOrigin(novoDados);
    const approvalOnly = onlyGlobalApprovalChanged(currentItem.dados_extraidos ?? {}, novoDados, path);
    if (!approvalOnly && path[0] !== 'revisao_extracao') novoDados = syncApplications(novoDados);
    for (const key of ['adicionais', 'progressao', 'apuracao', 'substituicao', 'rescisao', 'abono', 'exercicios']) {
      if (!approvalOnly && novoDados[key] && path[0] !== key) novoDados[key] = { ...(novoDados[key] as Record<string, unknown>), conferido_pelo_rh: false };
    }
    if (currentItem.historico_id && path[0] !== 'substitui_historico_id') novoDados.substitui_historico_id = currentItem.historico_id;
    setError(null);
    setFieldErrors(Object.keys(fieldErrors).length ? missingProgressionInputs(novoDados) : {});
    if (currentItem.resultado_calculo != null) {
      setFeedback({ tone: 'info', message: 'Dados atualizados.', detail: 'Confirme e calcule novamente para atualizar o resultado.' });
    }
    
    setCurrentItem({
      ...currentItem,
      idempotency_key: undefined,
      dados_extraidos: novoDados as Record<string, unknown> | null,
      historico_id: null,
      resultado_calculo: null
    });
  };

  const handleAttachmentsChange = (selected: CalculationAttachment[]) => {
    setAttachments(selected);
    setError(null);
    setFeedback(null);
  };

  function handleLogin(role: string, username: string) {
    invalidateOperations();
    resetAll();
    setShowAlterarSenha(false);
    setIsLoggedIn(true);
    setUserRole(role);
    localStorage.setItem('isLoggedIn', 'true');
    localStorage.setItem('role', role);
    localStorage.setItem('username', username);
    publishSessionChange();
    setShowGuide(localStorage.getItem(guideStorageKey(username)) !== 'seen');
    setFocusGuide(false);
    setActiveTab('dashboard');
  }

  const dismissGuide = () => {
    try {
      localStorage.setItem(guideStorageKey(localStorage.getItem('username') || ''), 'seen');
    } catch {
      // A falta de espaço no navegador não deve impedir o fechamento do guia.
    }
    setShowGuide(false);
    guideTriggerRef.current?.focus();
  };

  const openGuide = () => {
    setActiveTab('dashboard');
    setShowGuide(true);
    setFocusGuide(true);
    setGuideOpenCount(count => count + 1);
    if (window.innerWidth < 768) setIsSidebarOpen(false);
  };

  async function handleLogout() {
    if (logoutRequest.current) return;
    invalidateOperations();
    resetAll();
    setShowAlterarSenha(false);
    setUserRole(null);
    localStorage.removeItem('isLoggedIn');
    localStorage.removeItem('role');
    localStorage.removeItem('username');
    localStorage.setItem('sgp:logout-pending', 'true');
    publishSessionChange();
    setLogoutState('pending');
    const operation = beginOperation();
    const version = sessionVersion.current;
    logoutRequest.current = operation.controller;
    let timeout: ReturnType<typeof setTimeout> | undefined;
    try {
      const response = await Promise.race([
        fetch(`${apiBaseUrl}/api/auth/logout`, { method: 'POST', credentials: 'include', signal: operation.controller.signal }),
        new Promise<never>((_, reject) => {
          timeout = setTimeout(() => {
            operation.controller.abort();
            reject(new Error('O servidor demorou para responder. Tente encerrar a sessão novamente.'));
          }, 15000);
        }),
      ]);
      if (version !== sessionVersion.current) return;
      if (!response.ok) throw new Error('O servidor não confirmou o encerramento. Sua sessão pode continuar ativa.');
      localStorage.removeItem('sgp:logout-pending');
      publishSessionChange();
      setLogoutState('idle');
      setIsLoggedIn(false);
      setActiveTab('dashboard');
    } catch (error) {
      if (version !== sessionVersion.current) return;
      setLogoutError(error instanceof Error && !(error instanceof TypeError) ? error.message : 'Não foi possível acessar o servidor. Sua sessão pode continuar ativa. Confira a conexão e tente novamente.');
      setLogoutState('error');
    } finally {
      clearTimeout(timeout);
      pendingRequests.current.delete(operation.controller);
      if (logoutRequest.current === operation.controller) logoutRequest.current = null;
    }
  }

  useEffect(() => {
    const synchronize = () => {
      const marker = sessionFingerprint();
      if (marker === sessionMarker.current) return;
      sessionMarker.current = marker;
      invalidateOperations();
      logoutRequest.current = null;
      resetAll();
      setShowAlterarSenha(false);
      setUserRole(null);
      setIsLoggedIn(false);
      setSessionSyncing(false);
      setActiveTab('dashboard');
      if (localStorage.getItem('sgp:logout-pending') === 'true') {
        setLogoutState('error');
        setLogoutError('A saída foi solicitada em outra aba. Aguarde a confirmação ou tente encerrar novamente.');
        return;
      }
      setLogoutState('idle');
      if (localStorage.getItem('isLoggedIn') !== 'true') return;
      // A shared cookie may now belong to another account. Confirm it with the server.
      const operation = beginOperation();
      setSessionSyncing(true);
      void (async () => {
        try {
          const response = await fetch(`${apiBaseUrl}/api/auth/me`, { credentials: 'include', signal: operation.controller.signal });
          if (!response.ok) throw new Error('Sessão indisponível');
          const identity = await response.json();
          if (!operation.isCurrent()) return;
          if (typeof identity.username !== 'string' || !['user', 'admin', 'dev'].includes(identity.role)) throw new Error('Sessão inválida');
          localStorage.setItem('username', identity.username);
          localStorage.setItem('role', identity.role);
          sessionMarker.current = sessionFingerprint();
          setUserRole(identity.role);
          setIsLoggedIn(true);
          setShowGuide(localStorage.getItem(guideStorageKey(identity.username)) !== 'seen');
          setFocusGuide(false);
        } catch {
          if (operation.isCurrent()) setShowLanding(false);
        } finally {
          pendingRequests.current.delete(operation.controller);
          if (operation.isCurrent()) setSessionSyncing(false);
        }
      })();
    };
    const onStorage = (event: StorageEvent) => {
      if (event.key === null || ['isLoggedIn', 'username', 'role', 'sgp:logout-pending', sessionEventKey].includes(event.key)) synchronize();
    };
    const onVisible = () => { if (document.visibilityState === 'visible') synchronize(); };
    window.addEventListener('storage', onStorage);
    window.addEventListener('focus', synchronize);
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      window.removeEventListener('storage', onStorage);
      window.removeEventListener('focus', synchronize);
      document.removeEventListener('visibilitychange', onVisible);
    };
    // These callbacks only use setters, refs, and current browser storage.
  }, []);

  if (sessionSyncing) return <main className="min-h-screen bg-canvas grid place-items-center p-6"><ActionFeedback feedback={{ tone: 'loading', message: 'Atualizando a sessão...' }} /></main>;

  if (logoutState !== 'idle') return <main className="min-h-screen bg-canvas grid place-items-center p-6">
    <div className="surface w-full max-w-lg space-y-5 p-6">
      <h1 className="page-title">Encerramento da sessão</h1>
      <ActionFeedback feedback={logoutState === 'pending' ? { tone: 'loading', message: 'Encerrando a sessão...' } : { tone: 'error', message: 'Não foi possível confirmar a saída.', detail: logoutError }} />
      <p className="body-text">Os dados foram retirados da tela. Aguarde a confirmação do servidor antes de deixar este navegador.</p>
      <Button busy={logoutState === 'pending'} onClick={() => void handleLogout()}>{logoutState === 'pending' ? 'Aguarde...' : 'Tentar encerrar novamente'}</Button>
    </div>
  </main>;

  if (!isLoggedIn) {
    if (showLanding) {
      return (
        <LandingPage 
          onLoginClick={() => setShowLanding(false)} 
          isDarkMode={isDarkMode} 
          setIsDarkMode={setIsDarkMode} 
        />
      );
    }

    return (
      <div className="min-h-screen bg-canvas flex items-center justify-center p-4 transition-colors duration-300">
        <Login onLogin={handleLogin} onBack={() => setShowLanding(true)} />
      </div>
    );
  }

  return (
    <>
      {showAlterarSenha && <AlterarSenhaModal onClose={() => setShowAlterarSenha(false)} />}
      {showDiscardConfirmation && <Modal title="Descartar a revisão em andamento?" description="Os dados ainda não calculados serão descartados. Você pode continuar a revisão antes de iniciar outro cálculo." onClose={() => setShowDiscardConfirmation(false)}>
        <div className="flex flex-wrap justify-end gap-3 p-6">
          <Button variant="secondary" onClick={() => setShowDiscardConfirmation(false)}>Continuar revisão</Button>
          <Button onClick={discardAndStart}>Descartar e iniciar novo cálculo</Button>
        </div>
      </Modal>}
      <div className="flex h-screen bg-canvas text-ink overflow-hidden">
      <Sidebar
        isSidebarOpen={isSidebarOpen}
        setIsSidebarOpen={setIsSidebarOpen}
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        userRole={userRole}
        isDarkMode={isDarkMode}
        setIsDarkMode={setIsDarkMode}
        resetAll={startNewCalculation}
        isBusy={isUploading || isExporting}
      />

      {/* Main Content */}
      <div className="min-w-0 flex-1 flex flex-col h-screen overflow-hidden relative">
        <Header
          isSidebarOpen={isSidebarOpen}
          setIsSidebarOpen={setIsSidebarOpen}
          activeTab={activeTab}
          setShowAlterarSenha={setShowAlterarSenha}
          handleLogout={handleLogout}
          onOpenGuide={openGuide}
          guideButtonRef={guideTriggerRef}
        />

        {/* Área Rolável de Trabalho */}
        <main ref={workspaceRef} tabIndex={-1} className="workspace custom-scrollbar flex w-full flex-1 flex-col items-center overflow-y-auto px-4 py-6 sm:px-6 md:px-8 md:py-10 xl:px-12 focus:outline-none">
          {activeTab === 'dashboard' ? (
            <Dashboard setActiveTab={setActiveTab} userRole={userRole} hasActiveCalculation={hasReview || files.length > 0} onboarding={showGuide && <OnboardingGuide key={guideOpenCount} userRole={userRole} hasActiveCalculation={hasReview || files.length > 0} onDismiss={dismissGuide} onStart={() => { dismissGuide(); setActiveTab('calculo'); workspaceRef.current?.focus(); }} focusOnOpen={focusGuide} />} />
          ) : activeTab === 'historico' ? (
            <Historico onRecalculate={(type, data, identifier) => {
              if (hasPendingReview) return false;
              const revised = structuredClone(data);
              for (const key of ['apuracao', 'progressao', 'adicionais', 'substituicao', 'abono', 'rescisao', 'exercicios']) if (revised[key]) revised[key] = { ...revised[key] as Record<string, unknown>, conferido_pelo_rh: false };
              if (revised.revisao_extracao) revised.revisao_extracao = { ...revised.revisao_extracao as Record<string, unknown>, confirmado: false };
              revised.substitui_historico_id = identifier;
              setTipoCalculo(type); setCurrentItem({ filename: `Recálculo do histórico #${identifier}`, dados_extraidos: revised, historico_id: null, resultado_calculo: null });
              setAttachments([]); setFileProgress([]); setError(null); setFieldErrors({}); setActiveTab('calculo');
            }} />
          ) : activeTab === 'usuarios' && (userRole === 'admin' || userRole === 'dev') ? (
            <GestaoUsuarios />
          ) : activeTab === 'tabelas' && (userRole === 'admin' || userRole === 'dev') ? (
            <GestaoTabelas />
          ) : activeTab === 'auditoria' && userRole === 'dev' ? (
            <AuditoriaLogs />
          ) : (
            <div className="page-layout">
              {!!fileProgress.length && <section aria-label="Situação dos arquivos" className="surface p-4"><h3 className="subsection-title">Arquivos enviados</h3><ul aria-live="polite">{fileProgress.map((file, index) => <li key={index}>{file.filename}: {file.status}</li>)}</ul></section>}
              <CalculationSteps current={!currentItem ? 'documentos' : currentItem?.resultado_calculo != null ? 'resultado' : 'revisao'} />
              <ActionFeedback inline={tipoCalculo === 'progressao' && hasReview && feedback?.tone === 'success' && !error} feedback={error ? { tone: 'error', message: error } : feedback} />
              {error && tipoCalculo && !currentItem && !isUploading && <Button variant="secondary" onClick={startManualReview}>Continuar com preenchimento manual</Button>}
              {!currentItem ? (
                <div className="grid place-items-center">
                  <FileUpload
                    tipoCalculo={tipoCalculo}
                    setTipoCalculo={tipo => { setTipoCalculo(tipo); setAttachments([]); setFileProgress([]); setError(null); setFeedback(null); }}
                    attachments={attachments}
                    setAttachments={handleAttachmentsChange}
                    isUploading={isUploading}
                    onSubmit={handleUpload}
                  />
                </div>
              ) : (
                <div className="grid gap-[var(--section-gap)]">
                  <p className="help-text">Revisão de um servidor e vínculo. Para outra pessoa, inicie um novo cálculo.</p>
                  
                  {/* O resultado ocupa a coluna principal; os dados ficam disponíveis para consulta. */}
                  <div className={currentItem?.resultado_calculo != null ? 'calculation-grid' : 'mx-auto w-full max-w-3xl'}>

                    {currentItem?.resultado_calculo != null && <div key="result" className="min-w-0 w-full flex flex-col gap-8">
                      <ResultadoCalculo
                        data={currentItem}
                        isExporting={isExporting}
                        onExportPDF={handleExportPDF}
                        onReset={startNewCalculation}
                      />
                    </div>}

                    <div key="review" className="min-w-0 w-full flex flex-col gap-8">
                      {['revisao_extracao', 'apuracao', 'adicionais', 'progressao', 'substituicao', 'rescisao', 'abono', 'exercicios'].some(name => currentItem?.dados_extraidos?.[name]) && <>
                        {currentItem.falhas_extracao?.map((failure, index) => <p role="alert" key={index}>{failure.filename}: {failure.mensagem}</p>)}
                        <details className="surface p-4"><summary className="field-label cursor-pointer">Adicionar ou repetir documentos</summary><form className="mt-4 space-y-3" onSubmit={handleUpload}>
                        <p className="help-text">Adicione fontes ou tente novamente os arquivos com falha. Os valores revisados serão preservados; fontes novas não serão aplicadas automaticamente.</p>
                        <DocumentAttachments tipoCalculo={tipoCalculo!} attachments={attachments} onChange={handleAttachmentsChange} disabled={isUploading || isExporting} />
                        <Button type="submit" disabled={!files.length || isUploading || isExporting}>Extrair arquivos selecionados preservando edições</Button>
                      </form></details></>}
                      <RevisaoDadosForm 
                        data={currentItem}
                        isCalculated={currentItem?.resultado_calculo != null}
                        isUploading={isUploading || isExporting}
                        onCalculate={handleCalculate}
                        handleChangeData={handleChangeData}
                        fieldErrors={fieldErrors}
                      />
                    </div>

                  </div>
                  

                </div>
              )}
            </div>
          )}
        </main>

        <style>{`
          .custom-scrollbar::-webkit-scrollbar { width: 6px; }
          .custom-scrollbar::-webkit-scrollbar-track { background: transparent; }
          .custom-scrollbar::-webkit-scrollbar-thumb { background: var(--color-control-outline); border-radius: 10px; }
        `}</style>

      </div>
    </div>
    </>
  );
}
