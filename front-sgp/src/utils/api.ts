// Em produção, a interface e a API compartilham a origem protegida por HTTPS.
export const apiBaseUrl = import.meta.env.VITE_API_URL?.trim() || (import.meta.env.PROD ? '' : 'http://localhost:8000');
