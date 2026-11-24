import type { ComponentProps } from 'react';
import { render } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { Sidebar } from './Sidebar';

describe('Sidebar Component', () => {
  it('renders without crashing', () => {
    const props: ComponentProps<typeof Sidebar> = { isSidebarOpen: true, setIsSidebarOpen: () => {}, activeTab: 'dashboard', setActiveTab: () => {}, userRole: 'user', isDarkMode: false, setIsDarkMode: () => {}, resetAll: () => {} };
    const { container } = render(<Sidebar {...props} />);
    expect(container.firstChild).not.toBeNull();
  });
});
