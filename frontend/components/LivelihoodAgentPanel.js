'use client';
import {useState} from 'react';
import {api} from '../lib/api';

export function LivelihoodAgentPanel({sessionId,onComplete}){
  const [goal,setGoal]=useState('Find suitable local training options and outline next steps');
  const [result,setResult]=useState(null);
  const [error,setError]=useState('');
  const [busy,setBusy]=useState(false);
  async function run(event){
    event.preventDefault();setBusy(true);setError('');setResult(null);
    try{const response=await api(`/api/v1/agent/livelihood/${sessionId}/run`,{method:'POST',body:JSON.stringify({goal})});setResult(response);onComplete?.()}
    catch(e){setError(e.message)}finally{setBusy(false)}
  }
  const action=result?.final_action;
  return <section className="panel" style={{marginTop:12}}>
    <div className="panel-head"><div><h3>Livelihood planning assistant</h3><small className="muted">Uses approved planning tools; eligibility and current availability still need counsellor review.</small></div><span className="status amber">CONTROLLED AGENT</span></div>
    <form className="row wrap" onSubmit={run}><input className="input" value={goal} onChange={e=>setGoal(e.target.value)} maxLength={400} minLength={3} required aria-label="Planning goal"/><button className="button primary small" disabled={busy}>{busy?'Planning…':'Run planning'}</button></form>
    {busy&&<small>Reviewing approved records…</small>}{error&&<div className="notice" role="alert">{error}</div>}
    {action&&<div className="notice blue" style={{marginTop:10}}><b>{result.status.replaceAll('_',' ')}</b><p>{action.message}</p>
      {action.recommendations?.map(x=><div className="profileitem" key={x.pathway_id}><b>{x.title}</b><small>{x.sector} · {x.data_status||'catalogue record'} · Skills to build: {(x.missing_skills||[]).join(', ')||'not listed'}</small></div>)}
      {action.training_centres?.map(x=><div className="profileitem" key={x.centre_id}><b>{x.name}</b><small>{x.district} · {x.verification_status} · Verify details before travel.</small></div>)}
      {action.action_plan?.map((item,index)=><small key={index}>• {item}</small>)}
      {action.handoffs?.map((item,index)=><small key={`h${index}`}>Counsellor handoff {item.handoff_id}: {item.created?'created':'already open'}.</small>)}
      {action.followups?.map((item,index)=><small key={`f${index}`}>Follow-up {item.followup_id}: {item.stage} {item.due_date&&`· ${item.due_date}`}.</small>)}
      <small>Tools: {result.tools_used.join(' → ')||'none'}</small>
    </div>}
  </section>
}
