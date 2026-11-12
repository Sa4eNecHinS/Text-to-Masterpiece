import { useEffect, useId, useRef, useState } from 'react';
import type { KeyboardEvent } from 'react';
import { ModelSelect, type ModelSelectProps } from './ModelSelect';

interface ChatInputProps {
  value: string;
  onChange: (val: string) => void;
  onSend: () => void;
  loading?: boolean;
  disabled?: boolean;
  placeholder?: string;
  isGlass?: boolean;
  modelSelect?: ModelSelectProps;
}

export const ChatInput = ({
  value, onChange, onSend, loading, disabled, placeholder = "Describe your thoughts...", isGlass = false, modelSelect
}: ChatInputProps) => {
  const [menuOpen, setMenuOpen] = useState(false);
  const [dismissedCommand, setDismissedCommand] = useState<string | null>(null);
  const root = useRef<HTMLDivElement>(null);
  const textarea = useRef<HTMLTextAreaElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const menuId = useId();
  const commandsId = useId();
  const commandOptionId = useId();
  const modelCommand = /^\/model(?:\s|$)/i.test(value);
  const showMenu = menuOpen && !loading && !!modelSelect;
  const commandPrefix = value.startsWith('/') && '/model'.startsWith(value.toLowerCase());
  const showCommands = commandPrefix && dismissedCommand !== value && !showMenu && !loading && !!modelSelect;
  const openCommand = () => {
    onChange('/model');
    setDismissedCommand(null);
    setMenuOpen(true);
  };
  const selectedModel = modelSelect?.models.find(model => model.model_id === modelSelect.value);

  useEffect(() => {
    if (!showMenu && !showCommands) return;
    const closeOutside = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) {
        setMenuOpen(false);
        setDismissedCommand(value);
      }
    };
    document.addEventListener('pointerdown', closeOutside);
    return () => document.removeEventListener('pointerdown', closeOutside);
  }, [showMenu, showCommands, value]);

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.nativeEvent.isComposing) return;
    if (showCommands && (e.key === 'ArrowDown' || e.key === 'ArrowUp')) {
      e.preventDefault();
      return;
    }
    if (showCommands && (e.key === 'Tab' || e.key === 'Enter') && !e.shiftKey) {
      e.preventDefault();
      openCommand();
      return;
    }
    if (modelSelect && modelCommand && (e.key === 'Tab' || e.key === 'Enter') && !e.shiftKey && !loading) {
      e.preventDefault();
      setMenuOpen(true);
      return;
    }
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (!loading && !disabled) onSend();
    }
  };

  return (
    <div ref={root} className={`input-pill ${isGlass ? 'glass' : ''}`}
      onBlur={event => {
        if (!event.currentTarget.contains(event.relatedTarget)) {
          setMenuOpen(false);
          setDismissedCommand(value);
        }
      }}
      onKeyDown={event => {
        if ((showMenu || showCommands) && event.key === 'Escape') {
          event.preventDefault();
          setMenuOpen(false);
          if (modelCommand || showCommands) textarea.current?.focus();
          else trigger.current?.focus();
          setDismissedCommand(value);
        }
      }}>
      <button ref={trigger} type="button" className="action-btn" disabled={loading || !modelSelect}
        aria-label="Choose model" title={selectedModel ? `Model: ${selectedModel.name}` : 'Choose model'}
        aria-haspopup="menu" aria-expanded={showMenu} aria-controls={showMenu ? menuId : undefined}
        onClick={() => setMenuOpen(open => !open)}>
        +
      </button>
      {showMenu && <div id={menuId} className="model-popover">
        <ModelSelect {...modelSelect} onChange={id => {
          modelSelect.onChange(id);
          if (modelCommand) onChange(value.replace(/^\/model\s*/i, ''));
          setMenuOpen(false);
          textarea.current?.focus();
        }} />
      </div>}

      {showCommands && <div id={commandsId} className="model-popover command-popover" role="listbox" aria-label="Commands">
        <div className="model-menu-heading">Commands <span>Tab ↹ / Enter ↵</span></div>
        <button type="button" id={commandOptionId} className="command-option" role="option" aria-selected="true"
          tabIndex={-1} onMouseDown={event => event.preventDefault()} onClick={openCommand}>
          <span className="command-icon" aria-hidden="true">/</span>
          <span><strong>/model</strong><span className="command-description">Choose an image model</span></span>
          <span className="command-shortcut" aria-hidden="true">↵</span>
        </button>
      </div>}

      <textarea
        ref={textarea}
        className="prompt-input"
        aria-label="Image prompt"
        aria-autocomplete="list"
        aria-haspopup="listbox"
        aria-expanded={showCommands}
        aria-controls={showCommands ? commandsId : undefined}
        aria-activedescendant={showCommands ? commandOptionId : undefined}
        rows={1}
        placeholder={placeholder}
        value={value}
        onFocus={() => setDismissedCommand(null)}
        onChange={(e) => {
          setDismissedCommand(null);
          onChange(e.target.value);
        }}
        onKeyDown={handleKeyDown}
        disabled={loading}
      />

      <button
        type="button"
        className="send-btn"
        aria-label="Generate image"
        onClick={onSend}
        disabled={!value.trim() || loading || disabled || showCommands || (!!modelSelect && modelCommand)}
      >
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M12 19V5M5 12L12 5L19 12" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
      </button>
      {modelSelect && !showMenu && (modelSelect.error || (!modelSelect.loading && !modelSelect.models.length)) &&
        <span className="model-input-status" role="status">Models unavailable. Open + to retry.</span>}
    </div>
  );
};
