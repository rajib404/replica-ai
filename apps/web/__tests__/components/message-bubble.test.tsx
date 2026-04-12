/**
 * MessageBubble component tests.
 *
 * Verifies rendering for the three message roles (user / assistant / system),
 * the streaming indicator, language badge, source count badge, and reaction
 * callbacks.
 */

import { render, screen, fireEvent } from '@testing-library/react';
import { MessageBubble, type ChatMessage } from '@/components/chat/message-bubble';

const baseMessage: ChatMessage = {
  id: 'msg-1',
  role: 'assistant',
  content: 'Hello there, how can I help?',
  timestamp: new Date('2026-01-01T12:00:00Z'),
};

describe('MessageBubble', () => {
  it('renders assistant message content', () => {
    render(<MessageBubble message={baseMessage} />);
    expect(screen.getByText(/hello there/i)).toBeInTheDocument();
  });

  it('renders user message with different alignment', () => {
    const userMsg: ChatMessage = { ...baseMessage, role: 'user', content: 'Hi!' };
    const { container } = render(<MessageBubble message={userMsg} />);
    expect(screen.getByText('Hi!')).toBeInTheDocument();
    // The outer flex container reverses for user messages
    const wrapper = container.querySelector('.flex-row-reverse');
    expect(wrapper).not.toBeNull();
  });

  it('renders system message in pill style', () => {
    const sysMsg: ChatMessage = {
      ...baseMessage,
      role: 'system',
      content: 'You have a new notification',
    };
    render(<MessageBubble message={sysMsg} />);
    expect(screen.getByText(/new notification/i)).toBeInTheDocument();
  });

  it('shows the streaming indicator while streaming', () => {
    const streamingMsg: ChatMessage = { ...baseMessage, isStreaming: true };
    const { container } = render(<MessageBubble message={streamingMsg} />);
    // The streaming caret has animate-pulse
    expect(container.querySelector('.animate-pulse')).not.toBeNull();
  });

  it('shows the language badge for non-English content', () => {
    const frMsg: ChatMessage = { ...baseMessage, language: 'fr', content: 'Bonjour' };
    render(<MessageBubble message={frMsg} />);
    expect(screen.getByText('FR')).toBeInTheDocument();
  });

  it('does not show a language badge for English', () => {
    const enMsg: ChatMessage = { ...baseMessage, language: 'en' };
    render(<MessageBubble message={enMsg} />);
    expect(screen.queryByText('EN')).not.toBeInTheDocument();
  });

  it('shows a sources count badge when sources are present', () => {
    const sourcedMsg: ChatMessage = {
      ...baseMessage,
      sources: [
        { entry_id: 'a', content_type: 'text', score: 0.9 },
        { entry_id: 'b', content_type: 'text', score: 0.8 },
      ],
    };
    render(<MessageBubble message={sourcedMsg} />);
    expect(screen.getByText(/2 sources/i)).toBeInTheDocument();
  });

  it('singular "source" when there is exactly one', () => {
    const sourcedMsg: ChatMessage = {
      ...baseMessage,
      sources: [{ entry_id: 'a', content_type: 'text', score: 0.9 }],
    };
    render(<MessageBubble message={sourcedMsg} />);
    expect(screen.getByText(/1 source$/i)).toBeInTheDocument();
  });

  it('calls onReaction when like button is clicked', () => {
    const onReaction = jest.fn();
    render(<MessageBubble message={baseMessage} onReaction={onReaction} />);
    // The like button is inside a tooltip — find by lucide icon role isn't
    // possible, so we click the first button rendered (Like)
    const buttons = screen.getAllByRole('button');
    fireEvent.click(buttons[0]);
    expect(onReaction).toHaveBeenCalledWith('msg-1', 'like');
  });

  it('calls onBookmark when bookmark button is clicked', () => {
    const onBookmark = jest.fn();
    render(<MessageBubble message={baseMessage} onBookmark={onBookmark} />);
    const buttons = screen.getAllByRole('button');
    // The bookmark button is the second action button on assistant messages
    fireEvent.click(buttons[1]);
    expect(onBookmark).toHaveBeenCalledWith('msg-1');
  });
});
