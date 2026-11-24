import { render } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { AuditoriaLogs } from './AuditoriaLogs';

describe('AuditoriaLogs Component', () => {
  it('renders without crashing', () => {
    const { container } = render(<AuditoriaLogs />);
    expect(container.firstChild).not.toBeNull();
  });
});
