'use client';
import {useCallback,useEffect,useState} from 'react';
import {api} from '../lib/api';
import {LockKeyhole,LogIn,LogOut} from 'lucide-react';

export function AuthGate({role,children}){
  const [staff,setStaff]=useState(null),[checked,setChecked]=useState(false),[username,setUsername]=useState(''),[password,setPassword]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false);
  const refresh=useCallback(async()=>{try{const current=await api('/api/v1/auth/me');setStaff(current);setError('')}catch{setStaff(null)}finally{setChecked(true)}},[]);
  useEffect(()=>{refresh()},[refresh]);
  async function signIn(e){e.preventDefault();setBusy(true);setError('');try{const current=await api('/api/v1/auth/login',{method:'POST',body:JSON.stringify({username,password})});if(current.role!==role){await api('/api/v1/auth/logout',{method:'POST'});throw new Error(`This page requires a ${role} account.`)}setStaff(current);setPassword('')}catch(e){setError(e.message)}finally{setBusy(false)}}
  async function signOut(){try{await api('/api/v1/auth/logout',{method:'POST'})}finally{setStaff(null)}}
  if(!checked)return <main className="shell"><div className="container"><div className="panel">Checking staff access…</div></div></main>;
  if(staff?.role===role)return <>{children}<div className="container row" style={{justifyContent:'flex-end',paddingBottom:20}}><small className="muted">Signed in as {staff.username}</small><button className="button outline small" onClick={signOut}><LogOut size={14}/>Sign out</button></div></>;
  return <main className="shell"><div className="container" style={{maxWidth:520,paddingTop:70,paddingBottom:80}}><section className="panel"><div className="iconbox"><LockKeyhole/></div><div className="eyebrow" style={{color:'#168f91',marginTop:18}}>STAFF ACCESS · {role.toUpperCase()}</div><h1 style={{fontSize:30}}>Sign in to continue</h1><p className="muted">This workspace contains protected beneficiary and planning information.</p><form className="stack" onSubmit={signIn}><label className="label">Username<input className="input" autoComplete="username" value={username} onChange={e=>setUsername(e.target.value)} required/></label><label className="label">Password<input className="input" type="password" autoComplete="current-password" value={password} onChange={e=>setPassword(e.target.value)} required/></label>{error&&<div className="notice" role="alert">{error}</div>}<button className="button primary" disabled={busy}><LogIn size={16}/>{busy?'Signing in…':'Sign in'}</button></form></section></div></main>;
}
