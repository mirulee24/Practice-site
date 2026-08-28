#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
거점전 선착순 신청 연습 사이트 (웹 전용)
────────────────────────────────────────────────────────────
· 등수는 "요청이 서버에 도착한 순서"로 결정됩니다 (실전과 동일 기준).
· 직업은 브라우저에 저장되고 접속할 때마다 서버로 자동 재등록됩니다.
  → 서버가 재시작(Render 슬립/재배포)돼도 직업을 다시 고를 필요가 없습니다.
· 표준 라이브러리만 사용. 외부 패키지 불필요.

실행:  python practice_site.py
────────────────────────────────────────────────────────────
"""
import os
import json
import time
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

PORT = int(os.environ.get("PORT", "8000"))

VOTE_LABEL = {"attend": "참여", "non_attend": "미참", "boarding": "부속", "late_attend": "늦참"}

_lock = threading.Lock()
_state = {"id": "none", "status": "idle", "openAt": 0.0, "round": 0}
_entries = {}     # roundId -> [ {nickname, arrivalMs, deltaMs, votingType, className, classType} ]
_profiles = {}    # nickname -> {"name":..., "type":...}  (클라이언트가 접속 시 자동 재등록)
_last = None


def now_ms() -> float:
    return time.time() * 1000.0


def board_of(rid):
    rows = sorted(_entries.get(rid, []), key=lambda x: x["arrivalMs"])
    return [{"nickname": r["nickname"], "deltaMs": r["deltaMs"], "votingType": r["votingType"],
             "className": r.get("className"), "classType": r.get("classType")} for r in rows]


def archive_current():
    global _last
    b = board_of(_state["id"])
    if b:
        counts = {}
        for e in b:
            counts[e["votingType"]] = counts.get(e["votingType"], 0) + 1
        _last = {"round": _state["round"], "board": b, "counts": counts}


def arm_round(delay_sec: float):
    with _lock:
        archive_current()
        _state["round"] += 1
        _state["id"] = f"r{_state['round']}-{int(now_ms())}"
        _state["status"] = "armed"
        _state["openAt"] = now_ms() + delay_sec * 1000.0
        _entries[_state["id"]] = []
        snap = dict(_state)
    print(f"\n=== 테스트 {snap['round']} — {delay_sec:.0f}초 후 오픈 ===")
    return snap


def record_vote(nickname, rid, vtype, arrival):
    nickname = (nickname or "").strip()
    if not nickname:
        return False, {"error": "가문명이 없습니다."}
    if vtype not in VOTE_LABEL:
        return False, {"error": "알 수 없는 선택지입니다."}
    with _lock:
        if rid != _state["id"]:
            return False, {"error": "이전 테스트입니다. 새로고침하세요."}
        if _state["status"] == "closed":
            return False, {"error": "투표가 마감되었습니다."}
        if _state["status"] != "armed" or arrival < _state["openAt"]:
            return False, {"error": "아직 열리지 않았습니다."}

        rows = _entries.setdefault(rid, [])
        mine = next((r for r in rows if r["nickname"] == nickname), None)
        dup = False
        if mine:
            # 실전처럼 선택 변경은 허용하되, 등수는 최초 도착 시각으로 고정
            dup = (mine["votingType"] == vtype)
            mine["votingType"] = vtype
        else:
            p = _profiles.get(nickname) or {}
            mine = {"nickname": nickname, "arrivalMs": arrival,
                    "deltaMs": int(round(arrival - _state["openAt"])),
                    "votingType": vtype, "className": p.get("name"),
                    "classType": p.get("type")}
            rows.append(mine)

        b = board_of(rid)
        rank = next(i + 1 for i, r in enumerate(b) if r["nickname"] == nickname)
        res = {"rank": rank, "deltaMs": mine["deltaMs"], "votingType": vtype,
               "duplicated": dup, "board": b}
    if not dup:
        print(f"  {rank:>3}등  {nickname:<14} {VOTE_LABEL[vtype]:<3} +{res['deltaMs']}ms")
    return True, res


HTML = r"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>거점전 선착순 연습</title>
<style>
:root{--color-bg-deep:#0c0a12;--color-bg-mid:#17131f;--color-accent:#a56cff;
--color-accent-soft:#a56cff29;--color-text-main:#f2eee6;--color-text-dim:#a79fb8;
--color-text-faint:#5c5568;--color-line:#ffffff14}
:root{--background:var(--color-bg-deep);--foreground:var(--color-text-main);
--card-bg:var(--color-bg-mid);--border-color:var(--color-line);
--muted:var(--color-text-dim);--accent:var(--color-accent)}
html{color-scheme:dark;height:100%}
html,body{max-width:100vw;overflow-x:hidden}
body{min-height:100%;color:var(--foreground);background:var(--background);
-webkit-font-smoothing:antialiased;flex-direction:column;display:flex;
font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Apple SD Gothic Neo,Noto Sans KR,Roboto,sans-serif}
*{box-sizing:border-box;margin:0;padding:0}
button{font-family:inherit}
.main{flex-direction:column;align-items:center;gap:16px;min-height:100dvh;
padding:24px 16px 48px;display:flex}
.header{justify-content:space-between;align-items:center;width:100%;max-width:480px;display:flex}
.nickname{font-weight:600}
.logoutButton{border:1px solid var(--border-color);color:var(--muted);cursor:pointer;
background:0 0;border-radius:6px;padding:6px 12px;font-size:.85rem}
.card{border:1px solid var(--border-color);background:var(--card-bg);border-radius:16px;
width:100%;max-width:480px;padding:28px 24px}
.title{margin:0 0 8px;font-size:1.25rem}
.dateLine{margin:0 0 4px;font-weight:600}
.instruction{color:var(--muted);margin:0 0 20px;font-size:.875rem}
.buttonRow{grid-template-columns:repeat(2,1fr);gap:10px;display:grid}
.voteButton{border:1px solid var(--border-color);color:var(--foreground);cursor:pointer;
background:0 0;border-radius:10px;padding:14px 12px;font-size:1rem;font-weight:600}
.voteButton:disabled{opacity:.5;cursor:not-allowed}
.primary{border-color:var(--accent);color:var(--accent)}
.grey{border-color:var(--muted)}
.green{color:#2f9e44;border-color:#2f9e44}
.danger{color:#e5484d;border-color:#e5484d}
.selected{background:color-mix(in srgb,currentColor 15%,transparent)}
.notice{color:var(--muted);margin-top:16px;font-size:.9rem;line-height:1.5}
.warning{color:#f0a000;margin-top:16px;font-size:.9rem;line-height:1.5}
.message{margin-top:16px;font-size:.95rem;font-weight:600}
.error{color:#e5484d;margin-top:8px;font-size:.85rem}
.classSection{border-top:1px solid var(--border-color);margin-top:12px;padding-top:16px}
.classStep{flex-direction:column;gap:10px;display:flex}
.classTypeRow{grid-template-columns:repeat(3,1fr);gap:8px;display:grid}
.classTypeButton{border:1px solid var(--border-color);color:var(--foreground);text-align:center;
cursor:pointer;background:0 0;border-radius:10px;padding:14px 6px;font-size:.8rem;font-weight:600}
.classTypeButton:hover{border-color:var(--accent);color:var(--accent)}
.classBackButton{color:var(--muted);cursor:pointer;background:0 0;border:none;
align-self:flex-start;padding:0;font-size:.8rem}
.classGrid{grid-template-columns:repeat(auto-fill,minmax(72px,1fr));gap:10px;display:grid}
.classCard{border:2px solid var(--border-color);color:var(--foreground);cursor:pointer;
background:0 0;border-radius:10px;flex-direction:column;align-items:center;gap:6px;
padding:8px 4px;display:flex}
.classCardSelected{border-color:var(--accent);background:color-mix(in srgb,var(--accent) 15%,transparent)}
.classCardLabel{text-align:center;font-size:.75rem;line-height:1.2}
.classIconPlaceholder{background:var(--border-color);border-radius:8px;width:48px;height:48px;
display:flex;align-items:center;justify-content:center;font-size:.7rem;color:var(--color-text-faint)}
.tabBar{background:var(--background);border:1px solid var(--border-color);border-radius:12px;
grid-template-columns:repeat(3,1fr);gap:6px;margin-bottom:20px;padding:4px;display:grid}
.tabButton{color:var(--muted);cursor:pointer;background:0 0;border:none;border-radius:9px;
padding:10px 8px;font-size:.85rem;font-weight:600}
.tabButtonActive{background:var(--card-bg);color:var(--accent);box-shadow:0 0 0 1px var(--accent)}
@media (max-width:480px){.tabBar{z-index:1;position:sticky;top:0}}
.countdown{font-variant-numeric:tabular-nums;align-items:baseline;gap:8px;margin-top:16px;display:flex}
.countdownSegment{font-size:1.75rem;font-weight:700}
.countdownSoon{color:var(--accent);margin-top:16px;font-size:1.1rem;font-weight:700}
.summaryList{flex-direction:column;gap:8px;margin:16px 0 0;padding:0;list-style:none;display:flex}
.summaryItem{border:1px solid var(--border-color);border-radius:8px;justify-content:space-between;
padding:10px 12px;font-size:.9rem;display:flex}
.rankItem{border:1px solid var(--border-color);border-radius:8px;align-items:center;gap:10px;
padding:9px 12px;font-size:.9rem;display:flex}
.rankItem.first{border-color:var(--accent)}
.rankItem.me{background:var(--color-accent-soft)}
.rankNo{font-variant-numeric:tabular-nums;width:26px;color:var(--muted);font-weight:700}
.rankName{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.rankCls{font-size:.75rem;color:var(--muted);white-space:nowrap}
.rankMs{font-variant-numeric:tabular-nums;color:var(--muted);font-size:.85rem}
.rankItem.first .rankNo,.rankItem.first .rankMs{color:var(--accent)}
.hostBar{border-top:1px dashed var(--border-color);margin-top:20px;padding-top:14px}
.hostToggle{color:var(--muted);cursor:pointer;background:0 0;border:none;padding:0;font-size:.8rem}
.hostRow{gap:8px;margin-top:12px;display:flex;flex-wrap:wrap}
.hostBtn{border:1px solid var(--border-color);color:var(--foreground);cursor:pointer;background:0 0;
border-radius:8px;padding:9px 12px;font-size:.8rem;font-weight:600}
.hostBtn:hover{border-color:var(--accent);color:var(--accent)}
.loginRow{gap:8px;margin-top:16px;display:flex}
.loginInput{flex:1;min-width:0;border:1px solid var(--border-color);background:var(--background);
color:var(--foreground);border-radius:8px;padding:11px 12px;font-size:1rem;outline:none}
.loginInput:focus{border-color:var(--accent)}
.ok{color:#2f9e44;margin-top:16px;font-size:.9rem;font-weight:600}
</style></head><body>
<div class="main">
  <div class="header">
    <span class="nickname" id="hdrNick"></span>
    <button class="logoutButton" id="hdrOut" style="display:none">가문명 변경</button>
  </div>
  <div class="card" id="card">불러오는 중…</div>
</div>
<script>
const TL={Succession:"전승",Awaken:"각성",Else:"기타(아처, 샤이, 스칼라)"};
const TS={Succession:"전승",Awaken:"각성",Else:"기타"};
// 순위표에 "매구 (전승)" 형태로 표시
const clsLabel=e=>e.className?`${e.className} (${TS[e.classType]||'?'})`:'직업 미등록';
const ELSE_C=["아처","샤이","스칼라"];
const DUAL_C=["워리어","소서러","레인저","자이언트","금수랑","무사","발키리","매화","위자드","위치",
"쿠노이치","닌자","다크나이트","격투가","미스틱","란","가디언","하사신","노바","세이지","커세어",
"드라카니아","우사","매구","도사","데드아이","에이전트"];
const VOTES=[{t:"attend",c:"primary"},{t:"non_attend",c:"grey"},
{t:"boarding",c:"green"},{t:"late_attend",c:"danger"}];
const VL={attend:"참여",non_attend:"미참",boarding:"부속",late_attend:"늦참"};
const CLASS_SHOW=["attend","boarding"];
const clsFor=t=>t==="Else"?ELSE_C:DUAL_C;
const $=id=>document.getElementById(id);
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pad=n=>String(n).padStart(2,"0");

// ── 직업/가문명은 브라우저에 저장하고, 접속할 때마다 서버에 자동 재등록 ──
// 서버가 재시작(Render 슬립/재배포)돼도 다시 고를 필요가 없게 하는 핵심 부분
const LS_NICK='ps_nick', LS_PROF='ps_prof';
function loadProf(){
  try{const r=localStorage.getItem(LS_PROF);return r?JSON.parse(r):null;}catch(e){return null;}
}
function saveProf(p){
  try{p?localStorage.setItem(LS_PROF,JSON.stringify(p)):localStorage.removeItem(LS_PROF);}catch(e){}
}
async function syncProfToServer(){
  if(!nick||!prof)return;
  try{await api('/api/profile',{nickname:nick,name:prof.name,type:prof.type});}catch(e){}
}

let nick=null,prof=null;
try{nick=localStorage.getItem(LS_NICK);}catch(e){}
prof=loadProf();
let st=null,board=[],last=null,offset=0;
let screen='race',tab='process',pickType=null,hostOpen=false;
let myVote=null,myRank=null,myMs=null,msg=null,err=null,busy=false;
let autoSwitched=false,lastSync=0;

async function api(p,b){
  const o=b?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)}:{};
  return (await fetch(p,o)).json();
}
async function syncClock(){
  let best=1e9;
  for(let i=0;i<5;i++){
    const t0=Date.now(),j=await api('/api/time'),t1=Date.now();
    if(t1-t0<best){best=t1-t0;offset=j.now-(t1-(t1-t0)/2);}
  }
}
const srvNow=()=>Date.now()+offset;
const isLive=()=>st&&st.status==='armed'&&srvNow()>=st.openAt;

async function pull(){
  let j;
  try{ j=await api('/api/state'); }catch(e){ return; }
  const prevId=st&&st.id;
  st=j.state;board=j.board;last=j.last;
  if(st.id!==prevId){
    myVote=null;myRank=null;myMs=null;msg=null;err=null;autoSwitched=false;
    // 새 라운드가 열리면 내 직업이 서버에 남아있는지 다시 밀어넣는다
    syncProfToServer();
  }
  // 서버가 재시작됐을 수 있으니 30초마다 직업을 다시 등록해둔다
  if(Date.now()-lastSync>30000){ lastSync=Date.now(); syncProfToServer(); }
  if(isLive()&&!autoSwitched){autoSwitched=true;tab='process';}
  render();
}
async function castVote(type){
  if(busy||!st)return;
  busy=true;err=null;render();
  try{
    const j=await api('/api/vote',{nickname:nick,roundId:st.id,type});
    if(j.ok){
      myVote=j.votingType;myRank=j.rank;myMs=j.deltaMs;board=j.board;
      msg=j.duplicated?`이미 ${VL[j.votingType]}를 선택한 상태입니다.`:`${VL[j.votingType]} 선택.`;
      // 본사이트와 동일하게: 직업이 이미 있으면 종류 선택을 건너뛰고 직업 목록부터 표시
      if(CLASS_SHOW.includes(j.votingType)&&pickType===null&&prof)pickType=prof.type;
    }else{err=j.error;}
  }catch(e){err='통신 오류가 발생했습니다. 다시 시도하세요.';}
  busy=false;render();
}
async function pickClass(name){
  prof={name,type:pickType};
  saveProf(prof);                 // 먼저 브라우저에 저장 (서버가 재시작돼도 유지됨)
  await syncProfToServer();
  await pull();                   // 순위표의 내 직업 표시를 즉시 갱신
  render();
}

function classPickerHTML(){
  if(pickType===null){
    return `<div class="classStep"><div class="classTypeRow">
      ${Object.keys(TL).map(t=>`<button class="classTypeButton" data-t="${t}">${TL[t]}</button>`).join('')}
    </div></div>`;
  }
  return `<div class="classStep">
    <button class="classBackButton" id="clsBack">‹ 직업 종류 다시 선택</button>
    <div class="classGrid">${clsFor(pickType).map(n=>`
      <button class="classCard ${prof&&prof.name===n&&prof.type===pickType?'classCardSelected':''}" data-n="${esc(n)}">
        <span class="classIconPlaceholder">${esc(n.slice(0,2))}</span>
        <span class="classCardLabel">${esc(n)}</span></button>`).join('')}</div></div>`;
}

function processHTML(){
  const live=isLive();
  return `<h1 class="title">거점전 설문조사${live?'':' (대기중)'}</h1>
  <p class="dateLine">선착순 신청 연습</p>
  <p class="instruction">선택지는 하나만 선택해주세요. (부속인 경우 부속만 선택)</p>
  <div class="buttonRow">${VOTES.map(v=>`
    <button class="voteButton ${v.c} ${myVote===v.t?'selected':''}" data-v="${v.t}"
      ${(!live||busy)?'disabled':''}>${VL[v.t]}</button>`).join('')}</div>
  ${myRank?`<p class="message">서버 도착 ${myMs}ms · <strong>${myRank}등</strong></p>`:''}
  ${msg?`<p class="notice">${esc(msg)}</p>`:''}
  ${err?`<p class="error">${esc(err)}</p>`:''}
  ${!live?(st&&st.status==='closed'
      ?'<p class="notice">투표가 마감되었습니다.</p>'
      :'<p class="notice">아직 열리지 않았습니다. 대기중 탭에서 카운트다운을 확인하세요.</p>'):''}
  ${myVote&&CLASS_SHOW.includes(myVote)?`<div class="classSection">
    ${prof?`<p class="notice">현재 직업: ${esc(prof.name)} (${TS[prof.type]})<br>직업을 변경하시려면 아래에서 다시 선택해주세요.</p>`
          :`<p class="warning">⚠️ 직업 미등록! 아래에서 직업을 등록해야 인원제한결과에 포함됩니다.</p>`}
    ${classPickerHTML()}</div>`:''}
  <div class="classSection"><p class="dateLine">순위 (서버 도착 순)</p>
  <ul class="summaryList">${board.length===0?'<li class="summaryItem"><span>아직 신청자가 없습니다.</span></li>'
    :board.map((e,i)=>`<li class="rankItem ${i===0?'first':''} ${e.nickname===nick?'me':''}">
      <span class="rankNo">${i+1}</span><span class="rankName">${esc(e.nickname)}</span>
      <span class="rankCls">${esc(VL[e.votingType])} · ${esc(clsLabel(e))}</span>
      <span class="rankMs">${e.deltaMs}ms</span></li>`).join('')}</ul></div>`;
}

function waitHTML(){
  if(!st||st.status!=='armed')
    return `<h1 class="title">거점전 설문조사 (대기중)</h1>
    <p class="instruction">예약된 테스트가 없습니다. 아래 관리자 모드에서 시작하세요.</p>`;
  const left=Math.max(0,st.openAt-srvNow());
  const s=Math.floor(left/1000);
  return `<h1 class="title">거점전 설문조사 (대기중)</h1>
  <p class="dateLine">선착순 신청 연습</p>
  <p class="instruction">열리면 자동으로 진행중 탭으로 전환됩니다.</p>
  ${left<=0?'<p class="countdownSoon">곧 열립니다...</p>'
    :`<div class="countdown"><span class="countdownSegment">${pad(Math.floor(s/3600))}:${pad(Math.floor(s%3600/60))}:${pad(s%60)}</span></div>`}`;
}

function completeHTML(){
  if(!last)return `<h1 class="title">이전 테스트</h1><p class="instruction">아직 완료된 테스트가 없습니다.</p>`;
  const c=last.counts;
  return `<h1 class="title">이전 테스트 (${last.round}회차)</h1>
  <ul class="summaryList">${Object.keys(VL).map(k=>`
    <li class="summaryItem"><span>${VL[k]}</span><span>${c[k]||0}명</span></li>`).join('')}</ul>
  <p class="notice">총 ${last.board.length}명 참여</p>
  <ul class="summaryList">${last.board.map((e,i)=>`
    <li class="rankItem ${i===0?'first':''} ${e.nickname===nick?'me':''}">
    <span class="rankNo">${i+1}</span><span class="rankName">${esc(e.nickname)}</span>
    <span class="rankCls">${esc(VL[e.votingType])} · ${esc(clsLabel(e))}</span>
    <span class="rankMs">${e.deltaMs}ms</span></li>`).join('')}</ul>`;
}

function render(){
  if(!nick){
    if($('ni'))return;
    $('hdrNick').textContent='';$('hdrOut').style.display='none';
    $('card').innerHTML=`<h1 class="title">거점전 선착순 연습</h1>
      <p class="instruction">가문명을 입력하고 입장하세요. 같은 주소로 접속한 길드원 전원이 동일한 테스트에 함께 참여합니다.</p>
      <div class="loginRow"><input class="loginInput" id="ni" placeholder="가문명 입력" maxlength="16">
      <button class="voteButton primary" id="jb" style="padding:11px 18px;font-size:.9rem">입장</button></div>`;
    const i=$('ni');
    const go=async()=>{const v=i.value.trim();if(!v)return;
      nick=v;try{localStorage.setItem(LS_NICK,v);}catch(e){}
      await syncProfToServer();
      tab='process';
      render();};
    $('jb').onclick=go;i.addEventListener('keydown',e=>{if(e.key==='Enter')go()});i.focus();
    return;
  }
  $('hdrNick').textContent=nick;
  $('hdrOut').style.display='';
  $('hdrOut').onclick=()=>{
    try{localStorage.removeItem(LS_NICK);}catch(e){}
    nick=null;render();
  };

  const tabs={process:'진행중',wait:'대기중',complete:'이전 테스트'};
  $('card').innerHTML=`<div class="tabBar" role="tablist">
    ${Object.keys(tabs).map(k=>`<button class="tabButton ${tab===k?'tabButtonActive':''}" data-tab="${k}">${tabs[k]}</button>`).join('')}
    </div><div class="tabContent">
    ${tab==='process'?processHTML():tab==='wait'?waitHTML():completeHTML()}</div>
    <div class="hostBar"><button class="hostToggle" id="ht">${hostOpen?'▲ 관리자 모드 닫기':'▼ 관리자 모드 (테스트 진행)'}</button>
    ${hostOpen?`<div class="hostRow">
      <button class="hostBtn" data-d="5">5초 후</button>
      <button class="hostBtn" data-d="10">10초 후</button>
      <button class="hostBtn" data-d="30">30초 후</button>
      <button class="hostBtn" data-d="-1">초기화</button></div>
      <p class="notice" style="font-size:.8rem">테스트를 열면 접속 중인 모두의 화면이 동시에 카운트다운으로 바뀝니다.</p>`:''}</div>`;

  document.querySelectorAll('[data-tab]').forEach(b=>b.onclick=()=>{tab=b.dataset.tab;pickType=null;render()});
  document.querySelectorAll('[data-v]').forEach(b=>b.onclick=()=>castVote(b.dataset.v));
  document.querySelectorAll('[data-t]').forEach(b=>b.onclick=()=>{pickType=b.dataset.t;render()});
  document.querySelectorAll('[data-n]').forEach(b=>b.onclick=()=>pickClass(b.dataset.n));
  const cb=$('clsBack');if(cb)cb.onclick=()=>{pickType=null;render()};
  $('ht').onclick=()=>{hostOpen=!hostOpen;render()};
  document.querySelectorAll('[data-d]').forEach(b=>b.onclick=async()=>{
    const d=Number(b.dataset.d);
    await api(d<0?'/api/reset':'/api/arm',d<0?{}:{delay:d});
    if(d>=0)tab='wait';
    pull();});
}
(async function(){
  await syncClock();
  await syncProfToServer();
  await pull();
  render();
  setInterval(pull,1000);
  setInterval(()=>{if(tab==='wait'&&st&&st.status==='armed')render();},200);
  setInterval(syncClock,60000);
})();
</script></body></html>
"""


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _send(self, body, ctype="application/json; charset=utf-8", code=200):
        raw = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def _json(self, obj, code=200):
        self._send(json.dumps(obj, ensure_ascii=False), code=code)

    def _read_body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except Exception:
            return {}

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            return self._send(HTML, "text/html; charset=utf-8")
        if path == "/api/time":
            return self._json({"now": now_ms()})
        if path == "/api/state":
            with _lock:
                return self._json({"state": _state, "board": board_of(_state["id"]), "last": _last})
        if path == "/api/profile":
            q = parse_qs(urlparse(self.path).query)
            with _lock:
                return self._json({"profile": _profiles.get((q.get("nickname") or [""])[0])})
        return self._json({"error": "not found"}, 404)

    def do_POST(self):
        arrival = now_ms()          # ★ 등수 기준: 요청이 서버에 도착한 시각
        path = urlparse(self.path).path
        data = self._read_body()

        if path == "/api/vote":
            ok, res = record_vote(data.get("nickname"), data.get("roundId"),
                                  data.get("type"), arrival)
            return self._json({"ok": ok, **res})

        if path == "/api/arm":
            d = data.get("delay")
            return self._json({"ok": True, "state": arm_round(float(d) if d is not None else 5.0)})

        if path == "/api/reset":
            with _lock:
                archive_current()
                # 아직 한 번도 안 연 상태(idle)와 구분하기 위해 closed 로 표시
                _state["status"] = "closed"
                _state["openAt"] = 0.0
                return self._json({"ok": True, "state": _state})

        if path == "/api/profile":
            nick = (data.get("nickname") or "").strip()
            name, ctype = data.get("name"), data.get("type")
            if nick and name and ctype:
                with _lock:
                    _profiles[nick] = {"name": name, "type": ctype}
                    # 이미 이번 라운드에 신청한 상태라면 순위표의 직업 표시도 즉시 갱신
                    # (등수와 도착 시각은 최초 클릭 기준 그대로 유지)
                    for r in _entries.get(_state["id"], []):
                        if r["nickname"] == nick:
                            r["className"] = name
                            r["classType"] = ctype
                            break
                    return self._json({"profile": _profiles[nick]})
            return self._json({"profile": None})

        return self._json({"error": "not found"}, 404)


class PracticeServer(ThreadingHTTPServer):
    request_queue_size = 512      # 기본값 5는 인원이 몰리면 접속이 거절됨
    daemon_threads = True
    allow_reuse_address = True


def local_ips():
    import socket
    ips = set()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ips.add(s.getsockname()[0])
        s.close()
    except Exception:
        pass
    return sorted(ips)


if __name__ == "__main__":
    srv = PracticeServer(("0.0.0.0", PORT), Handler)
    print("=" * 56)
    print("  거점전 선착순 신청 연습 사이트")
    print("=" * 56)
    print(f"  주소:           http://localhost:{PORT}")
    for ip in local_ips():
        print(f"  같은 와이파이:  http://{ip}:{PORT}")
    print("\n  등수 기준: 요청이 서버에 도착한 순서")
    print("  직업은 각자 브라우저에 저장되어 서버 재시작 후에도 유지됩니다.")
    print("  종료: Ctrl+C\n")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n종료합니다.")
