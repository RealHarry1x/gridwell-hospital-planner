import React, { useRef, useState } from 'react';
import { api } from '../api';
import { Badge, Card, Icon, PageTitle, SafetySummary } from '../components';
import { useWorkspace } from '../context';

export { Outage } from './Outage';
export { Presets } from './Presets';

export function Assistant() {
  const w = useWorkspace();
  const [message, setMessage] = useState(w.guideQuestion || '');
  const [lastReply, setLastReply] = useState(null);
  const [messages, setMessages] = useState([{
    role: 'assistant',
    text: 'Hi! What can I help you with? Ask a general question, or explore your hospital’s simulated energy plan.',
  }]);
  const bottom = useRef(null);
  const configured = w.config.assistant?.configured;
  const modeLabel = lastReply
    ? lastReply.mode.split(' · ')[0]
    : (configured ? 'Gemini configured · awaiting reply' : 'Sample mode');
  const contextLabel = lastReply ? (lastReply.uses_simulated_data ? 'SIMULATED GRIDWELL DATA' : 'GENERAL CHAT') : 'CHAT & ENERGY HELP';
  const sourceNotice = lastReply?.notice || w.config.assistant?.notice || 'Send a question to check the response source.';

  async function send(text) {
    const question = text.trim();
    if (!question || w.busy) return;
    setMessages(prev => [...prev, { role: 'user', text: question }]);
    setMessage('');
    // This same-origin Python endpoint is the only service the browser calls.
    const answer = await w.act('Preparing reply…', async () => api('/assistant', {
      method: 'POST',
      body: { message: question, plan_id: w.plan?.id || null, date: w.date, day_type: w.dayType },
    }));
    if (answer) {
      setLastReply(answer);
      setMessages(prev => [...prev, {
        role: 'assistant', text: answer.answer, context: answer.context,
        mode: answer.mode, provider: answer.provider, notice: answer.notice,
      }]);
    } else {
      setMessages(prev => [...prev, {
        role: 'assistant', text: 'The Python backend could not be reached. Check the error above and retry once the app is running.',
        mode: 'Connection unavailable',
      }]);
    }
    setTimeout(() => bottom.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }), 50);
  }

  return <>
    <PageTitle eyebrow="AN EXPLAINABLE SECOND OPINION" title="Ask. Understand. Decide."
      description="A friendly place for questions, ideas and help with your simulated hospital energy plan."
      action={<Badge tone={lastReply?.provider === 'google-genai' ? 'green' : ''}>{modeLabel.toUpperCase()} · {contextLabel}</Badge>}/>
    <div className="grid assistant-grid">
      <Card title="Your AI Guide"
        subtitle={w.plan ? `Energy context available · ${w.date} · revision ${w.plan.revision}` : `Energy forecast available · ${w.date}`}
        className="chat-card">
        <div className="soft-note" role="status" aria-live="polite"><b>{modeLabel}.</b> {sourceNotice}</div>
        <div className="chat-messages" role="log" aria-label="Energy guide conversation" aria-live="polite">
          {messages.map((m, i) => <div key={i} className={`chat-message ${m.role}`}>
            <span className="message-avatar">{m.role === 'assistant' ? <Icon name="suggestions" size={16}/> : 'OP'}</span>
            <div>
              <small>{m.role === 'user' ? 'YOU' : `GRIDWELL · ${m.mode || 'HELLO'}`}</small>
              <p>{m.text}</p>
              {m.notice && <span className="message-context">{m.notice}</span>}
              {m.context?.date && <span className="message-context">{m.context.date}{m.context.revision ? ` · revision ${m.context.revision}` : ' · original forecast'}</span>}
            </div>
          </div>)}
          <div ref={bottom}/>
        </div>
        <div className="quick-prompts">
          {['Hi', 'What is Python?', 'Explain my plan', 'Are critical loads protected?', 'How much does this cost?'].map(q =>
            <button key={q} disabled={!!w.busy} onClick={() => send(q)}>{q}<Icon name="arrow" size={13}/></button>)}
        </div>
        <form className="chat-form" onSubmit={e => { e.preventDefault(); send(message); }}>
          <label className="sr-only" htmlFor="assistant-message">Ask a general question or about the selected energy plan</label>
          <input id="assistant-message" maxLength={1500} value={message} onChange={e => setMessage(e.target.value)}
            placeholder="Say hi, ask a question, or explore your energy plan…"/>
          <button className="button primary" disabled={!!w.busy || !message.trim()} type="submit" aria-label="Send question"><Icon name="arrow" size={20}/></button>
        </form>
        <p className="muted small-text">Energy answers use the latest calculated revision and simulated hospital estimates. Weather inputs may come from Open-Meteo. General replies are labeled separately. Never include patient information, personal details or secrets.</p>
      </Card>
      <div className="assistant-aside">
        <Card title="Context, not guesswork." subtitle="Available for energy-plan questions">
          <div className="context-fact"><span>Selected day</span><b>{w.date}</b></div>
          <div className="context-fact"><span>Scenario</span><b>{w.dayType.replaceAll('_', ' ')}</b></div>
          <div className="context-fact"><span>Plan</span><b>{w.plan ? `Revision ${w.plan.revision} · ${w.plan.status}` : 'Not generated yet'}</b></div>
          <div className="context-fact"><span>Response mode</span><b>{modeLabel}</b></div>
          {lastReply?.model && <div className="context-fact"><span>Gemini model</span><b>{lastReply.model}</b></div>}
          {w.plan && <SafetySummary summary={w.plan.summary}/>}
        </Card>
        <div className="editorial-note">
          <Icon name="info" size={23}/><h3>A little help, when you need it.</h3>
          <p>General questions go to Gemini without hospital data. Energy questions use a small selection of Gridwell’s current simulated values and clearly labeled weather inputs. Greetings are answered locally; previous messages and database history are not forwarded.</p>
          <p>The guide cannot change the optimizer, settings, approvals, safety rules or equipment. Review the backend’s recorded checks before simulation approval.</p>
          <p>Gemini replies use your API account’s quota and billing. Local Sample mode remains available without a key.</p>
        </div>
      </div>
    </div>
  </>;
}
