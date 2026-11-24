import { reviewField } from './reviewFields';

export interface ApiErrorDetails {
  message: string;
  fields: Record<string, string>;
}

// Keep validation locations and messages only; API payloads may also contain sensitive inputs.
export function apiErrorDetails(body: unknown, fallback: string): ApiErrorDetails {
  const fields: Record<string, string> = {};
  if (!body || typeof body !== 'object' || !('detail' in body)) return { message: fallback, fields };
  const detail = body.detail;
  if (typeof detail === 'string') return { message: detail, fields };
  if (!Array.isArray(detail)) return { message: fallback, fields };
  const messages: string[] = [];
  for (const issue of detail.slice(0, 20)) {
    if (!issue || typeof issue !== 'object' || typeof issue.msg !== 'string' || !Array.isArray(issue.loc)) continue;
    const path = issue.loc.filter((part: unknown): part is string | number => typeof part === 'string' || typeof part === 'number');
    while (path[0] === 'body' || path[0] === 'dados_extraidos') path.shift();
    const message = issue.type === 'missing' ? 'Preencha este campo.' : issue.msg.slice(0, 300);
    if (path.length) {
      fields[JSON.stringify(path)] = message;
      messages.push(`${reviewField(path[path.length - 1], path).label}: ${message}`);
    } else messages.push(message);
  }
  return { message: messages.length ? messages.join(' ') : fallback, fields };
}
