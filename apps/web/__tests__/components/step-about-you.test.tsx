/**
 * Setup wizard "About You" step tests.
 *
 * Verifies the form's controlled-state binding, validation gating on the
 * Continue button, and the language picker open/select interactions.
 */

import { render, screen, fireEvent } from '@testing-library/react';
import { StepAboutYou } from '@/components/setup/step-about-you';
import type { SetupData } from '@/components/setup/setup-wizard';

function makeProps(overrides: Partial<SetupData> = {}) {
  const data: SetupData = {
    name: '',
    email: '',
    preferredLanguage: 'en',
    password: '',
    verificationMethod: 'secret_word',
    secretValue: '',
    ...overrides,
  };
  const onChange = jest.fn();
  const onBack = jest.fn();
  const onNext = jest.fn();
  return { data, onChange, onBack, onNext };
}

describe('StepAboutYou', () => {
  it('renders the form fields', () => {
    const props = makeProps();
    render(<StepAboutYou {...props} />);
    expect(screen.getByLabelText(/name/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
    expect(screen.getByText(/preferred language/i)).toBeInTheDocument();
  });

  it('continue button is disabled when name is empty', () => {
    const props = makeProps({ name: '' });
    render(<StepAboutYou {...props} />);
    const continueBtn = screen.getByRole('button', { name: /continue/i });
    expect(continueBtn).toBeDisabled();
  });

  it('continue button is enabled when name is filled', () => {
    const props = makeProps({ name: 'Alice' });
    render(<StepAboutYou {...props} />);
    const continueBtn = screen.getByRole('button', { name: /continue/i });
    expect(continueBtn).not.toBeDisabled();
  });

  it('calls onChange when typing in the name field', () => {
    const props = makeProps();
    render(<StepAboutYou {...props} />);
    const input = screen.getByLabelText(/name/i);
    fireEvent.change(input, { target: { value: 'Bob' } });
    expect(props.onChange).toHaveBeenCalledWith({ name: 'Bob' });
  });

  it('calls onChange when typing in the email field', () => {
    const props = makeProps();
    render(<StepAboutYou {...props} />);
    const input = screen.getByLabelText(/email/i);
    fireEvent.change(input, { target: { value: 'bob@example.com' } });
    expect(props.onChange).toHaveBeenCalledWith({ email: 'bob@example.com' });
  });

  it('calls onBack when back button is clicked', () => {
    const props = makeProps();
    render(<StepAboutYou {...props} />);
    fireEvent.click(screen.getByRole('button', { name: /back/i }));
    expect(props.onBack).toHaveBeenCalledTimes(1);
  });

  it('calls onNext when continue is clicked (with valid name)', () => {
    const props = makeProps({ name: 'Alice' });
    render(<StepAboutYou {...props} />);
    fireEvent.click(screen.getByRole('button', { name: /continue/i }));
    expect(props.onNext).toHaveBeenCalledTimes(1);
  });

  it('shows the language dropdown when clicked', () => {
    const props = makeProps();
    render(<StepAboutYou {...props} />);
    // The language toggle is the button showing the selected language name
    const langButton = screen.getByText(/select language|english/i);
    fireEvent.click(langButton);
    // The search input appears once the dropdown is open
    expect(
      screen.getByPlaceholderText(/search languages/i),
    ).toBeInTheDocument();
  });

  it('filters the language list when typing in search', () => {
    const props = makeProps();
    render(<StepAboutYou {...props} />);
    fireEvent.click(screen.getByText(/english/i));
    const search = screen.getByPlaceholderText(/search languages/i);
    fireEvent.change(search, { target: { value: 'spanish' } });
    expect(screen.getByText(/spanish/i)).toBeInTheDocument();
  });
});
