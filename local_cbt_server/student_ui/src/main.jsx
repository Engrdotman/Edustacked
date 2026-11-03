import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';

const API = '/local/api/v1';
const tokenKey = 'edustacked.localcbt.token';
const requestKey = (session, question) => `edustacked.localcbt.pending.${session}.${question}`;

async function api(path, options = {}) {
  const token = sessionStorage.getItem(tokenKey);
  const response = await fetch(`${API}${path}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}), ...options.headers },
  });
  const data = response.status === 204 ? null : await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || Object.values(data)[0] || `Request failed (${response.status})`);
  return data;
}

function App() {
  const [student, setStudent] = useState(null);
  const [exams, setExams] = useState([]);
  const [exam, setExam] = useState(null);
  const [questionIndex, setQuestionIndex] = useState(0);
  const [login, setLogin] = useState({ admission_number: '', password: '' });
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [saving, setSaving] = useState(false);
  const [hasPendingSaves, setHasPendingSaves] = useState(false);
  const [remaining, setRemaining] = useState(0);
  const [online, setOnline] = useState(navigator.onLine);
  const autoSubmitting = useRef(false);
  const answerTimers = useRef(new Map());
  const answerQueues = useRef(new Map());
  const current = exam?.questions?.[questionIndex];

  function refreshPendingState() {
    setHasPendingSaves(Array.from({ length: sessionStorage.length }, (_, index) => sessionStorage.key(index)).some(key => key?.startsWith('edustacked.localcbt.pending.')));
  }

  const loadExams = useCallback(async () => setExams(await api('/exams/')), []);
  const recover = useCallback(async () => {
    const raw = sessionStorage.getItem('edustacked.localcbt.session');
    if (!raw) return;
    try {
      const restored = await api(`/sessions/${raw}/`);
      if (restored.status === 'in_progress') setExam(restored);
      else sessionStorage.removeItem('edustacked.localcbt.session');
    } catch { sessionStorage.removeItem('edustacked.localcbt.session'); }
  }, []);

  useEffect(() => {
    const update = () => setOnline(navigator.onLine);
    addEventListener('online', update); addEventListener('offline', update);
    if (sessionStorage.getItem(tokenKey)) {
      setStudent(JSON.parse(sessionStorage.getItem('edustacked.localcbt.student') || 'null'));
      loadExams().catch(error => setNotice(error.message)); recover();
    }
    return () => { removeEventListener('online', update); removeEventListener('offline', update); };
  }, [loadExams, recover]);

  useEffect(() => {
    if (!exam?.expires_at || exam.status !== 'in_progress') return;
    const expiry = Date.parse(exam.expires_at);
    const serverOffset = Date.parse(exam.server_now) - Date.now();
    const tick = async () => {
      const seconds = Math.max(0, Math.ceil((expiry - (Date.now() + serverOffset)) / 1000));
      setRemaining(seconds);
      if (seconds === 0 && !autoSubmitting.current) {
        autoSubmitting.current = true;
        try { await api(`/sessions/${exam.session_id}/submit/`, { method: 'POST', body: '{}' });
          sessionStorage.removeItem('edustacked.localcbt.session'); setExam(null); setNotice('Time is up. Your saved answers were submitted to this school server.'); await loadExams();
        } catch (error) { setNotice(`Time is up. Waiting to submit when the server is reachable: ${error.message}`); setTimeout(() => { autoSubmitting.current = false; }, 10000); }
      }
    };
    tick(); const id = setInterval(tick, 1000); return () => clearInterval(id);
  }, [exam, loadExams]);

  const persistAnswer = useCallback((sessionId, data) => {
    const storageKey = requestKey(sessionId, data.question_id);
    const queueKey = `${sessionId}.${data.question_id}`;
    const previous = answerQueues.current.get(queueKey) || Promise.resolve();
    const task = previous.catch(() => {}).then(async () => {
      const pending = sessionStorage.getItem(storageKey);
      if (!pending || JSON.parse(pending).request_id !== data.request_id) return;
      setSaving(true);
      try {
        await api(`/sessions/${sessionId}/answers/`, { method: 'POST', body: JSON.stringify(data) });
        const latest = sessionStorage.getItem(storageKey);
        if (latest && JSON.parse(latest).request_id === data.request_id) {
          sessionStorage.removeItem(storageKey);
          refreshPendingState();
          setNotice('Answer saved on the school server.');
        }
      } catch (error) {
        setNotice(`Answer is still waiting to save on the school server: ${error.message}`);
      } finally { setSaving(false); }
    });
    answerQueues.current.set(queueKey, task);
    return task;
  }, []);

  const saveAnswer = useCallback((question, value) => {
    if (!exam) return;
    const data = { request_id: crypto.randomUUID(), question_id: question.question_id, value };
    setExam(previous => previous ? ({ ...previous, questions: previous.questions.map(row => row.question_id === question.question_id ? { ...row, answer: value } : row) }) : previous);
    const storageKey = requestKey(exam.session_id, question.question_id);
    sessionStorage.setItem(storageKey, JSON.stringify(data));
    setHasPendingSaves(true);
    const priorTimer = answerTimers.current.get(storageKey);
    if (priorTimer) clearTimeout(priorTimer);
    if (question.type === 'text') {
      answerTimers.current.set(storageKey, setTimeout(() => {
        answerTimers.current.delete(storageKey);
        persistAnswer(exam.session_id, data);
      }, 450));
    } else persistAnswer(exam.session_id, data);
  }, [exam, persistAnswer]);

  useEffect(() => {
    if (!online || !exam) return;
    const flushPending = () => {
      for (const question of exam.questions) {
        const raw = sessionStorage.getItem(requestKey(exam.session_id, question.question_id));
        if (!raw) continue;
        if (answerTimers.current.has(requestKey(exam.session_id, question.question_id))) continue;
        const data = JSON.parse(raw);
        persistAnswer(exam.session_id, data);
      }
    };
    flushPending();
    const retry = setInterval(flushPending, 5000);
    return () => clearInterval(retry);
  }, [online, exam, persistAnswer]);

  async function signIn(event) {
    event.preventDefault(); setBusy(true); setNotice('');
    try {
      const data = await api('/auth/login/', { method: 'POST', body: JSON.stringify(login) });
      sessionStorage.setItem(tokenKey, data.token); sessionStorage.setItem('edustacked.localcbt.student', JSON.stringify(data.student));
      setStudent(data.student); await loadExams();
    } catch (error) { setNotice(error.message); }
    finally { setBusy(false); }
  }

  async function startExam(item) {
    setBusy(true); setNotice('');
    try { const data = await api(`/exams/${item.package_id}/start/`, { method: 'POST', body: '{}' });
      setExam(data); autoSubmitting.current = false; sessionStorage.setItem('edustacked.localcbt.session', data.session_id); setQuestionIndex(0);
    } catch (error) { setNotice(error.message); }
    finally { setBusy(false); }
  }

  async function submitExam() {
    if (!exam || !confirm('Submit this examination? You cannot change answers afterwards.')) return;
    setBusy(true);
    try {
      for (const question of exam.questions) {
        const key = requestKey(exam.session_id, question.question_id);
        const timer = answerTimers.current.get(key);
        if (timer) { clearTimeout(timer); answerTimers.current.delete(key); }
        const raw = sessionStorage.getItem(key);
        if (raw) await persistAnswer(exam.session_id, JSON.parse(raw));
      }
      await Promise.all([...answerQueues.current.values()]);
      const unsaved = exam.questions.some(question => sessionStorage.getItem(requestKey(exam.session_id, question.question_id)));
      if (unsaved) { setNotice('Some answers are not saved on the school server. Reconnect to the school network and retry before submitting.'); return; }
      await api(`/sessions/${exam.session_id}/submit/`, { method: 'POST', body: '{}' });
      sessionStorage.removeItem('edustacked.localcbt.session'); setExam(null); setNotice('Your examination has been submitted to the school server.'); await loadExams();
    } catch (error) { setNotice(error.message); }
    finally { setBusy(false); }
  }

  async function signOut() {
    const pending = Array.from({ length: sessionStorage.length }, (_, index) => sessionStorage.key(index)).some(key => key?.startsWith('edustacked.localcbt.pending.'));
    if (pending && !confirm('Some answers are still waiting to save on the school server. Signing out clears this browser’s temporary queue. Continue?')) return;
    try { await api('/auth/logout/', { method: 'POST', body: '{}' }); } catch {}
    for (let i = sessionStorage.length - 1; i >= 0; i--) { const key = sessionStorage.key(i); if (key?.startsWith('edustacked.localcbt.')) sessionStorage.removeItem(key); }
    setStudent(null); setExam(null); setExams([]);
  }

  const answered = useMemo(() => exam?.questions?.filter(row => row.answer !== undefined && row.answer !== null && row.answer !== '').length || 0, [exam]);
  const formatTime = value => `${Math.floor(value / 60).toString().padStart(2, '0')}:${(value % 60).toString().padStart(2, '0')}`;

  if (!student) return <main className="login-shell"><section className="login-card"><div className="brand-mark">ES</div><p className="eyebrow">SCHOOL EXAMINATION PORTAL</p><h1>Sign in to your exam</h1><p className="muted">Use the examination login provided by your school. This server works on the school network.</p>
    {notice && <p className="notice error">{notice}</p>}<form onSubmit={signIn}><label>Admission number<input required value={login.admission_number} onChange={e => setLogin({ ...login, admission_number: e.target.value })} autoComplete="username" /></label><label>Password<input required type="password" value={login.password} onChange={e => setLogin({ ...login, password: e.target.value })} autoComplete="current-password" /></label><button disabled={busy}>{busy ? 'Signing in…' : 'Continue'}</button></form></section></main>;

  if (!exam) return <main className="app-shell"><header className="topbar"><div className="brand"><span className="brand-mark small">ES</span><span>EDUstacked <small>OFFLINE CBT</small></span></div><div className="top-actions"><span className={online ? 'network good' : 'network'}>{online ? 'School server connected' : 'Connection interrupted'}</span><span>{student.name}</span><button className="quiet" onClick={signOut}>Sign out</button></div></header><section className="content"><p className="eyebrow">STUDENT PORTAL</p><h1>Your examinations</h1><p className="muted">Your saved answers are held by the school server. Keep this device connected to the school network while you work.</p>{notice && <p className="notice">{notice}</p>}<div className="exam-list">{exams.length ? exams.map(item => <article className="exam-card" key={item.package_id}><div><p className="eyebrow">{item.subject} · {item.class_name}</p><h2>{item.title}</h2><p className="muted">{item.duration_minutes} minutes · {item.attempts_used}/{item.maximum_attempts} attempts used</p><p>{item.instructions}</p></div><button disabled={busy || item.status === 'expired' || item.attempts_used >= item.maximum_attempts} onClick={() => startExam(item)}>{item.status === 'in_progress' ? 'Resume exam' : 'Start exam'}</button></article>) : <div className="empty">No available examinations are assigned to your account.</div>}</div></section></main>;

  return <main className="exam-shell"><header className="exam-top"><div><p className="eyebrow">{exam.subject} · {exam.class_name}</p><h1>{exam.title}</h1><p>{student.name} · {student.admission_number}</p></div><div className={`timer ${remaining < 300 ? 'urgent' : ''}`}><span>TIME LEFT</span><strong>{formatTime(remaining)}</strong></div></header>{exam.instructions && <details className="instructions"><summary>Examination instructions</summary><p>{exam.instructions}</p></details>}<div className="progress-line"><span>{answered} of {exam.questions.length} answered</span><span>{saving ? 'Saving…' : hasPendingSaves ? 'Waiting to save · keep the page open' : online ? 'Saved on school server' : 'Connection interrupted'}</span></div><div className="exam-layout"><nav className="question-nav" aria-label="Question navigation">{exam.questions.map((q, i) => <button key={q.question_id} className={`${i === questionIndex ? 'selected' : ''} ${q.answer !== undefined && q.answer !== null && q.answer !== '' ? 'answered' : ''}`} onClick={() => setQuestionIndex(i)}>{i + 1}</button>)}</nav><section className="question-card"><p className="eyebrow">QUESTION {questionIndex + 1} OF {exam.questions.length} · {current.marks} MARKS</p><h2>{current.prompt}</h2>{current.image_data && <img className="question-image" src={`data:${current.image_mime};base64,${current.image_data}`} alt="Question illustration" />}{current.type === 'text' ? <textarea value={current.answer || ''} onChange={e => saveAnswer(current, e.target.value)} placeholder="Write your answer" /> : <div className="options">{current.options.map(option => <label key={option.id} className="option"><input type={current.type === 'multiple_answer' ? 'checkbox' : 'radio'} name={`q-${current.question_id}`} checked={current.type === 'multiple_answer' ? (current.answer || []).includes(option.id) : current.answer === option.id} onChange={e => { if (current.type === 'multiple_answer') { const values = new Set(current.answer || []); e.target.checked ? values.add(option.id) : values.delete(option.id); saveAnswer(current, [...values]); } else saveAnswer(current, option.id); }} /><span>{option.text}</span></label>)}</div>}<footer className="question-footer"><button className="secondary" disabled={questionIndex === 0} onClick={() => setQuestionIndex(questionIndex - 1)}>Previous</button><span>{saving ? 'Saving answer…' : hasPendingSaves ? 'Answer is waiting to save' : 'Saved on school server'}</span>{questionIndex < exam.questions.length - 1 ? <button onClick={() => setQuestionIndex(questionIndex + 1)}>Next question</button> : <button onClick={submitExam} disabled={busy}>{busy ? 'Submitting…' : 'Review and submit'}</button>}</footer></section></div></main>;
}

createRoot(document.getElementById('root')).render(<App />);
