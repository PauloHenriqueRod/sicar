import { ArrowRight, ClipboardCheck, FileText, FileDown, Moon, Sun } from 'lucide-react';
import { Button } from './ui';

interface LandingPageProps {
  onLoginClick: () => void;
  isDarkMode: boolean;
  setIsDarkMode: (val: boolean) => void;
}

export function LandingPage({ onLoginClick, isDarkMode, setIsDarkMode }: LandingPageProps) {
  return (
    <div className="min-h-screen bg-canvas text-ink flex flex-col transition-colors duration-300">

      <header className="app-header px-4 sm:px-6 py-4 flex items-center justify-between gap-4">
        <div className="flex items-center gap-2">
          <h1 className="brand-title text-2xl text-ink">
            SICAR
          </h1>
          <span className="text-sm font-semibold text-muted hidden sm:block">
            Sistema de Conferência e Apuração Remuneratória
          </span>
        </div>

        <div className="flex items-center gap-4">
          <button
            onClick={() => setIsDarkMode(!isDarkMode)}
            className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-lg hover:bg-panel transition-colors text-muted cursor-pointer"
            aria-label={isDarkMode ? 'Usar tema claro' : 'Usar tema escuro'}
            title={isDarkMode ? 'Usar tema claro' : 'Usar tema escuro'}
          >
            {isDarkMode ? <Sun className="h-5 w-5" aria-hidden="true" /> : <Moon className="h-5 w-5" aria-hidden="true" />}
          </button>
        </div>
      </header>

      <main className="flex-1">
      <section aria-labelledby="landing-title" className="flex flex-col items-center px-5 py-12 sm:py-16 text-center">
        
        <span className="caption-text mb-4">
          Rotinas de RH • UFPI
        </span>

        <h2 id="landing-title" className="hero-title max-w-3xl mb-4">
          Cálculos de RH, do documento ao relatório
        </h2>

        <p className="body-text text-muted max-w-xl mb-6">
          Extraia dados dos PDFs, confira os valores e gere a memória de cálculo.
        </p>

        <div className="flex flex-col sm:flex-row gap-4">
          <Button
            onClick={onLoginClick}
            className="cursor-pointer"
          >
            Acessar Sistema <ArrowRight className="w-5 h-5" aria-hidden="true" />
          </Button>
        </div>
      </section>

      <section aria-labelledby="landing-flow" className="px-5 pb-12 sm:pb-16">
        <div className="max-w-6xl mx-auto">
          <div className="mb-6 border-t border-outline pt-8">
            <h3 id="landing-flow" className="subsection-title">Como funciona</h3>
          </div>

          <ol className="grid grid-cols-1 md:grid-cols-3 gap-8">
            <li>
              <h4 className="text-base font-semibold leading-relaxed flex items-center gap-2 mb-2"><FileText className="h-5 w-5 shrink-0 text-muted" aria-hidden="true" />1. Envie os documentos</h4>
              <p className="help-text">
                Escolha o cálculo e selecione as fichas financeiras e os documentos do processo.
              </p>
            </li>

            <li>
              <h4 className="text-base font-semibold leading-relaxed flex items-center gap-2 mb-2"><ClipboardCheck className="h-5 w-5 shrink-0 text-muted" aria-hidden="true" />2. Confira os dados</h4>
              <p className="help-text">
                Revise os valores extraídos e complete os campos antes de calcular.
              </p>
            </li>

            <li>
              <h4 className="text-base font-semibold leading-relaxed flex items-center gap-2 mb-2"><FileDown className="h-5 w-5 shrink-0 text-muted" aria-hidden="true" />3. Gere o relatório</h4>
              <p className="help-text">
                Confira o resultado e baixe o PDF. Consulte os cálculos registrados no histórico.
              </p>
            </li>
          </ol>
        </div>
      </section>
      </main>

      <footer className="text-muted px-5 py-5 text-center border-t border-outline">
        <p className="text-sm">
          SICAR · Trabalho de Conclusão de Curso · {new Date().getFullYear()}
        </p>
      </footer>

    </div>
  );
}
