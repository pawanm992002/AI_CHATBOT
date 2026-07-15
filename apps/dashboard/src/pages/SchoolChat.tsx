import { FormEvent, KeyboardEvent, useEffect, useRef, useState } from 'react';
import { Bot, CirclePlus, Loader2, Send, UserRound } from 'lucide-react';
import { privateAxios } from '../utils/axios';

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

const SESSION_KEY = 'dashboard-school-chat-session';

const questions = [
  'Which students have pending fees?',
  'Show fees due for Aryan Nagar.',
  'What is the transport status for Ansh Sharma?',
  'How many students are in class 5?',
];

const SchoolChat = () => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(() => localStorage.getItem(SESSION_KEY));
  const [question, setQuestion] = useState('');
  const [loading, setLoading] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(Boolean(localStorage.getItem(SESSION_KEY)));
  const [error, setError] = useState('');
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const loadHistory = async () => {
      if (!sessionId) {
        setLoadingHistory(false);
        return;
      }
      try {
        const response = await privateAxios.get(`/dashboard/school/chat/${sessionId}`);
        setMessages(response.data.messages || []);
      } catch {
        localStorage.removeItem(SESSION_KEY);
        setSessionId(null);
      } finally {
        setLoadingHistory(false);
      }
    };
    loadHistory();
  }, [sessionId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const startNewChat = () => {
    localStorage.removeItem(SESSION_KEY);
    setSessionId(null);
    setMessages([]);
    setQuestion('');
    setError('');
  };

  const sendMessage = async (event?: FormEvent, nextQuestion?: string) => {
    event?.preventDefault();
    const text = (nextQuestion ?? question).trim();
    if (!text || loading) return;

    setMessages(previous => [...previous, { role: 'user', content: text }]);
    setQuestion('');
    setLoading(true);
    setError('');
    try {
      const response = await privateAxios.post('/dashboard/school/chat', {
        query: text,
        session_id: sessionId,
      });
      const nextSessionId = response.data.session_id as string;
      setSessionId(nextSessionId);
      localStorage.setItem(SESSION_KEY, nextSessionId);
      setMessages(previous => [...previous, { role: 'assistant', content: response.data.answer }]);
    } catch (requestError: any) {
      setMessages(previous => previous.slice(0, -1));
      setError(requestError.response?.data?.detail || 'School Chat could not answer right now. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      sendMessage();
    }
  };

  return (
    <div className="flex h-[calc(100vh-9.5rem)] min-h-[620px] flex-col border border-slate-800 bg-slate-900 text-slate-100 animate-fadeIn">
      <header className="flex items-center justify-between border-b border-slate-800 px-5 py-4">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center bg-violet-600 text-white"><Bot size={19} /></div>
          <div><h2 className="font-bold text-white">School Chat</h2><p className="text-xs text-emerald-300">School mode active</p></div>
        </div>
        <button onClick={startNewChat} disabled={loading} title="Start new school chat" className="flex h-9 w-9 items-center justify-center border border-slate-700 text-slate-400 transition-colors hover:border-violet-400 hover:text-violet-300 disabled:opacity-50"><CirclePlus size={18} /></button>
      </header>

      <div className="flex-1 overflow-y-auto p-4 sm:p-6">
        {loadingHistory ? <div className="flex h-full items-center justify-center gap-2 text-sm text-slate-400"><Loader2 size={18} className="animate-spin" /> Loading conversation</div> : messages.length ? <div className="mx-auto max-w-4xl space-y-5">{messages.map((message, index) => <div key={`${message.role}-${index}`} className={`flex gap-3 ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}><div className={`flex h-8 w-8 shrink-0 items-center justify-center ${message.role === 'user' ? 'order-2 bg-slate-700 text-slate-200' : 'bg-violet-600 text-white'}`}>{message.role === 'user' ? <UserRound size={16} /> : <Bot size={16} />}</div><div className={`max-w-[85%] whitespace-pre-wrap border px-4 py-3 text-sm leading-6 ${message.role === 'user' ? 'order-1 border-violet-500/40 bg-violet-950/40 text-violet-100' : 'border-slate-800 bg-slate-950 text-slate-200'}`}>{message.content}</div></div>)}{loading && <div className="flex gap-3"><div className="flex h-8 w-8 items-center justify-center bg-violet-600 text-white"><Bot size={16} /></div><div className="flex items-center border border-slate-800 bg-slate-950 px-4 text-sm text-slate-400"><Loader2 size={16} className="mr-2 animate-spin" /> Checking school data</div></div>}<div ref={bottomRef} /></div> : <div className="mx-auto flex h-full max-w-2xl flex-col items-center justify-center text-center"><div className="flex h-12 w-12 items-center justify-center bg-violet-600 text-white"><Bot size={24} /></div><h3 className="mt-4 text-lg font-bold text-white">School data assistant</h3><div className="mt-6 grid w-full gap-2 sm:grid-cols-2">{questions.map(item => <button key={item} onClick={() => sendMessage(undefined, item)} className="border border-slate-700 bg-slate-950 px-4 py-3 text-left text-sm text-slate-300 transition-colors hover:border-violet-500 hover:text-white">{item}</button>)}</div></div>}
      </div>

      <div className="border-t border-slate-800 p-4">
        {error && <p className="mb-3 border-l-2 border-rose-400 bg-rose-950/20 px-3 py-2 text-sm text-rose-200">{error}</p>}
        <form onSubmit={sendMessage} className="mx-auto flex max-w-4xl items-end gap-2"><textarea value={question} onChange={event => setQuestion(event.target.value)} onKeyDown={handleKeyDown} disabled={loading || loadingHistory} rows={2} maxLength={500} placeholder="Ask about students, fees, payments, transport, or hostel" className="min-h-11 flex-1 resize-none border border-slate-700 bg-slate-950 px-3 py-2.5 text-sm text-slate-100 outline-none placeholder:text-slate-600 focus:border-violet-500 disabled:opacity-60" /><button type="submit" disabled={!question.trim() || loading || loadingHistory} title="Send question" className="flex h-11 w-11 shrink-0 items-center justify-center bg-violet-600 text-white transition-colors hover:bg-violet-500 disabled:cursor-not-allowed disabled:opacity-50"><Send size={18} /></button></form>
      </div>
    </div>
  );
};

export default SchoolChat;
