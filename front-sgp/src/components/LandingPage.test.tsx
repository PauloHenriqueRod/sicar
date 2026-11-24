import type { ComponentProps } from 'react';
import { render } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { LandingPage } from './LandingPage';

describe('LandingPage Component', () => {
  it('renders without crashing', () => {
    const props: ComponentProps<typeof LandingPage> = { onLoginClick: () => {}, isDarkMode: false, setIsDarkMode: () => {} };
    const { container } = render(<LandingPage {...props} />);
    expect(container.firstChild).not.toBeNull();
  });
});
