import { useEffect, useRef, useState } from "react";
import { generateImage, getModels, initializeSession, type ChatHistoryEntry, type ImageModel } from "@/services/requests";
import { useAuth } from "@/components/auth/authContext";
import { useChatHistory } from "@/components/chat/useChatHistory";
import { readCurrentChat, saveCurrentChat } from "@/utils/currentChat";
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
  const [restoreError, setRestoreError] = useState('');
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [models, setModels] = useState<ImageModel[]>([]);
  const [modelId, setModelId] = useState('');
  const [modelsLoading, setModelsLoading] = useState(true);
  const [modelsError, setModelsError] = useState('');
  const [modelsRevision, setModelsRevision] = useState(0);
  const owner = useRef<number | null>(null);
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
    if (ready) return;
    let active = true;
    initializeSession().then(currentUser => {
      if (!active) return;
      owner.current = currentUser?.id ?? null;
      const saved = readCurrentChat(owner.current);
      if (saved) {
        setMessages(saved.messages);
        setInput(saved.input);
        setSelectedId(saved.selectedId);
      }
      setRestoreError('');
      setReady(true);
    }).catch(() => {
      if (active) setRestoreError('Unable to restore your session. Please reload to try again.');
    });
    return () => { active = false; };
  }, [ready, user?.id]);

  useEffect(() => {
    if (!ready) return;
    // Keep the open guest dialogue when signing in; the server merges its history.
    if (user) owner.current = user.id;
    saveCurrentChat({ owner: owner.current, messages, input, selectedId });
  }, [ready, user, messages, input, selectedId]);

  const isChatMode = messages.length > 0;
  const selectHistory = (entry: ChatHistoryEntry) => {
    if (sending.current || !ready) return;
    setMessages([
      { role: 'user', content: entry.prompt },
      { role: 'assistant', content: 'Result:', image: entry.image_url, modelName: entry.model_name },
    ]);
    setInput('');
    setSelectedId(entry.id);
  };
  const newChat = () => {
    if (sending.current || !ready) return;
    setMessages([]);
    setInput('');
    setSelectedId(null);
  };

  const handleSend = async () => {
    if (!input.trim() || sending.current || !ready || !validModel) return;
    sending.current = true;
    
    const userMsg: Message = { role: 'user', content: input };
    setMessages(prev => [...prev, userMsg]);
    const currentPrompt = input;
    setInput(""); 
    setLoading(true);

    try {
      const result = await generateImage(currentPrompt, modelId);
      setMessages(prev => [...prev, { role: 'assistant', content: 'Result:', image: result.image_url, modelName: result.model_name }]);
      history.refresh();
    } catch (err) {
      console.error(err);
      const message = err instanceof Error ? err.message : 'Error generating image.';
      setMessages(prev => [...prev, { role: 'assistant', content: message }]);
    } finally {
      sending.current = false;
      setLoading(false);
    }
  };

  return (
    <AppLayout onNewChat={newChat} onSignedOut={() => {
      owner.current = null;
      setMessages([]);
      setInput('');
      setSelectedId(null);
      saveCurrentChat({ owner: null, messages: [], input: '', selectedId: null });
    }} history={{
      entries: history.entries, loading: history.loading, error: history.error,
      hasMore: history.hasMore, selectedId, disabled: loading || !ready,
      onSelect: selectHistory, onLoadMore: history.loadMore, onRetry: history.refresh,
    }}>
      {restoreError && <p className="chat-restore-error" role="alert">{restoreError}</p>}
      
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
                loading={loading || !ready}
                disabled={!validModel}
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
            loading={loading || !ready}
            disabled={!validModel}
            placeholder="Continue..."
            isGlass={true}
          />
        </div>
      )}

    </AppLayout>
  );
}
