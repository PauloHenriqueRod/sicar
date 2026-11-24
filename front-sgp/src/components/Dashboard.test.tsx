import type { ComponentProps } from 'react';
import { render } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { Dashboard } from './Dashboard';

describe('Dashboard Component', () => {
  it('renders without crashing', () => {
    const props: ComponentProps<typeof Dashboard> = { setActiveTab: () => {}, userRole: 'user' };
    const { container } = render(<Dashboard {...props} />);
    expect(container.firstChild).not.toBeNull();
  });
});
