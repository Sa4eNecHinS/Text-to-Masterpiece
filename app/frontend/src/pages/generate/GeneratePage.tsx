import { useEffect, useRef, useState } from "react";
import { generateImage, getChat, getModels, initializeSession, type ImageModel } from "@/services/requests";
import { useAuth } from "@/components/auth/authContext";
import { useChatHistory } from "@/components/chat/useChatHistory";
import { generationMessages, readCurrentChat, saveCurrentChat } from "@/utils/currentChat";
import type { Message } from "@/types/message";
import { AppLayout } from "@/components/layout/AppLayout";
import { ChatInput } from "@/components/chat/ChatInput";
import { MessageList } from "@/components/chat/MessageList";
import { ModelSelect } from "@/components/chat/ModelSelect";

export default function GeneratePage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [ready, setReady] = useState(false);
  const [sessionRevision, setSessionRevision] = useState(0);
  const [restoreError, setRestoreError] = useState('');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [chatLoading, setChatLoading] = useState(false);
  const [chatError, setChatError] = useState('');
  const activeChat = useRef<string | null>(null);
  const chatRequest = useRef<AbortController | null>(null);
  const viewVersion = useRef(0);
  const [models, setModels] = useState<ImageModel[]>([]);
  const [modelId, setModelId] = useState('');
  const [modelsLoading, setModelsLoading] = useState(true);
  const [modelsError, setModelsError] = useState('');
  const [modelsRevision, setModelsRevision] = useState(0);
  const owner = useRef<number | null | undefined>(undefined);
  const sending = useRef(false);
  const { user } = useAuth();
  const history = useChatHistory();

  useEffect(() => {
    const controller = new AbortController();
    const load = async () => {
      setModelsLoading(true);
      setModelsError('');
      try {
        const catalogue = await getModels(controller.signal);
        if (controller.signal.aborted) return;
        setModels(catalogue);
        setModelId(previous => catalogue.some(model => model.model_id === previous) ? previous
          : (catalogue.find(model => model.model_id === 'cloudflare/flux-1-schnell') ?? catalogue[0])?.model_id ?? '');
      } catch (error) {
        if (!controller.signal.aborted) setModelsError(error instanceof Error ? error.message : 'Unable to load models.');
      } finally {
        if (!controller.signal.aborted) setModelsLoading(false);
      }
    };
    void load();
    return () => controller.abort();
  }, [modelsRevision]);

  const validModel = !modelsLoading && !modelsError && models.some(model => model.model_id === modelId);
  const modelSelector = <ModelSelect models={models} value={modelId} loading={modelsLoading}
    error={modelsError} disabled={loading} onChange={setModelId}
    onRetry={() => setModelsRevision(value => value + 1)} />;

  useEffect(() => {
    const controller = new AbortController();
    chatRequest.current?.abort();
    chatRequest.current = controller;
    const version = ++viewVersion.current;
    const invalidateView = () => { ++viewVersion.current; };
    const previousOwner = owner.current;
    const previousChat = activeChat.current;
    const guestDraft = previousOwner === null ? readCurrentChat(null) : null;
    sending.current = false;
    activeChat.current = null;
    setReady(false);
    setLoading(false);
    setChatLoading(false);
    setChatError('');
    setSelectedId(null);
    setMessages([]);
    setInput('');
    const restore = async () => {
      const currentUser = await initializeSession();
      if (controller.signal.aborted) return;
      const nextOwner = currentUser?.id ?? null;
      // A guest's active chat was transferred by sign-in. Other owner changes
      // must never reuse the previous owner's selection or cached results.
      const migrated = previousOwner === null && nextOwner !== null;
      const saved = migrated ? guestDraft : readCurrentChat(nextOwner);
      const chatId = (migrated ? previousChat : saved?.selectedId) ?? null;
      owner.current = nextOwner;
      activeChat.current = chatId;
      setSelectedId(chatId);
      setInput(saved?.input ?? '');
      setRestoreError('');
      if (chatId) {
        setChatLoading(true);
        try {
          const entries = await getChat(chatId, controller.signal);
          if (!controller.signal.aborted && version === viewVersion.current) setMessages(generationMessages(entries));
        } catch (error) {
          if (!controller.signal.aborted) setChatError(error instanceof Error ? error.message : 'Unable to load chat.');
        } finally {
          if (!controller.signal.aborted) setChatLoading(false);
        }
      } else {
        setMessages(saved?.messages ?? []);
      }
      if (!controller.signal.aborted && version === viewVersion.current) setReady(true);
    };
    void restore().catch(() => {
      if (!controller.signal.aborted) setRestoreError('Unable to restore your session. Please reload to try again.');
    });
    return () => {
      controller.abort();
      chatRequest.current?.abort();
      invalidateView();
    };
  }, [user?.id, sessionRevision]);

  useEffect(() => {
    if (!ready || owner.current === undefined) return;
    saveCurrentChat({ owner: owner.current, messages, input, selectedId });
  }, [ready, messages, input, selectedId]);

  const isChatMode = messages.length > 0;
  const selectHistory = async (chatId: string) => {
    if (sending.current || !ready) return;
    chatRequest.current?.abort();
    const controller = new AbortController();
    chatRequest.current = controller;
    const version = ++viewVersion.current;
    activeChat.current = chatId;
    setSelectedId(chatId);
    setMessages([]);
    setInput('');
    setChatError('');
    setChatLoading(true);
    try {
      const entries = await getChat(chatId, controller.signal);
      if (!controller.signal.aborted && version === viewVersion.current) setMessages(generationMessages(entries));
    } catch (error) {
      if (!controller.signal.aborted) setChatError(error instanceof Error ? error.message : 'Unable to load chat.');
    } finally {
      if (!controller.signal.aborted) setChatLoading(false);
    }
  };
  const newChat = () => {
    if (sending.current || !ready) return;
    chatRequest.current?.abort();
    ++viewVersion.current;
    activeChat.current = null;
    setMessages([]);
    setInput('');
    setSelectedId(null);
    setChatError('');
    setChatLoading(false);
  };

  const handleSend = async () => {
    if (!input.trim() || sending.current || !ready || !validModel || chatLoading || chatError) return;
    sending.current = true;
    const version = ++viewVersion.current;
    
    const userMsg: Message = { role: 'user', content: input };
    setMessages(prev => [...prev, userMsg]);
    const currentPrompt = input;
    setInput(""); 
    setLoading(true);

    try {
      const result = await generateImage(currentPrompt, modelId, activeChat.current);
      if (version !== viewVersion.current) return;
      activeChat.current = result.chat_id;
      setSelectedId(result.chat_id);
      setMessages(prev => [...prev, { role: 'assistant', content: 'Result:', image: result.image_url, modelName: result.model_name }]);
      history.refresh();
    } catch (err) {
      if (version !== viewVersion.current) return;
      console.error(err);
      const message = err instanceof Error ? err.message : 'Error generating image.';
      setMessages(prev => [...prev, { role: 'assistant', content: message }]);
    } finally {
      if (version === viewVersion.current) {
        sending.current = false;
        setLoading(false);
      }
    }
  };

  return (
    <AppLayout onNewChat={newChat} onSignedOut={() => {
      chatRequest.current?.abort();
      ++viewVersion.current;
      activeChat.current = null;
      owner.current = null;
      sending.current = false;
      setReady(false);
      setLoading(false);
      setChatLoading(false);
      setChatError('');
      setMessages([]);
      setInput('');
      setSelectedId(null);
      saveCurrentChat({ owner: null, messages: [], input: '', selectedId: null });
      // Logout's user update may commit before this callback. Always restore
      // the new session, even when user?.id is already null at this point.
      setSessionRevision(value => value + 1);
      history.refresh();
    }} history={{
      entries: history.entries, loading: history.loading, error: history.error,
      hasMore: history.hasMore, selectedId, disabled: loading || !ready,
      onSelect: entry => { void selectHistory(entry.id); }, onLoadMore: history.loadMore, onRetry: history.refresh,
    }}>
      {restoreError && <p className="chat-restore-error" role="alert">{restoreError}</p>}
      {chatLoading && <p className="chat-restore-error" role="status">Loading chat…</p>}
      {chatError && <div className="chat-restore-error" role="alert">
        <p>{chatError}</p>
        <button onClick={() => { if (selectedId) void selectHistory(selectedId); }} disabled={!ready}>Try again</button>
      </div>}
      
      <div className="hero-center-wrapper">
        <div className={`hero-glass-window ${isChatMode ? 'hidden' : ''}`}>
          <h1 className="hero-title">Create your masterpiece</h1>
          
          {!isChatMode && (
            <div className="input-transition-wrapper centered">
              {modelSelector}
              <ChatInput 
                value={input} 
                onChange={setInput} 
                onSend={handleSend} 
                loading={loading || chatLoading || !ready}
                disabled={!validModel || !!chatError}
                placeholder="Describe your vision..."
                isGlass={true} 
              />
            </div>
          )}
        </div>
      </div>

      {/* messages list */}
      {isChatMode && (
        <div style={{ flex: 1, overflowY: 'auto', paddingBottom: '180px', paddingTop: '20px' }}>
           <MessageList messages={messages} loading={loading} />
        </div>
      )}

      {isChatMode && (
        <div className="input-transition-wrapper bottom">
          {modelSelector}
          <ChatInput 
            value={input} 
            onChange={setInput} 
            onSend={handleSend} 
            loading={loading || chatLoading || !ready}
            disabled={!validModel || !!chatError}
            placeholder="Continue..."
            isGlass={true}
          />
        </div>
      )}

    </AppLayout>
  );
}
