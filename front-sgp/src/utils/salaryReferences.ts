export const salaryContextKeys = ['referencia_salarial', 'referencia_antiga', 'referencia_nova'];
export type SalaryPosition = Record<string, string | number | null>;
export const emptySalaryPosition = (): SalaryPosition => ({ carreira: '', vinculo: '', jornada: '', versao_carreira: '' });
export function serializeSalaryPosition(value: SalaryPosition): Record<string, unknown> {
  return Object.fromEntries(Object.entries(value).filter(([, v]) => v !== '' && v !== null).map(([k, v]) => {
    if (k !== 'padrao_tae' && k !== 'nivel_docente') return [k, v];
    const level = Number(v);
    if (!Number.isSafeInteger(level) || level < 1 || level > 1000) throw new Error('Nível ou padrão: informe um número inteiro válido entre 1 e 1000.');
    return [k, level];
  }));
}
