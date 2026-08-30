#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
거점전 선착순 신청 연습 사이트
────────────────────────────────────────────────────────────
· 본사이트 개편(종이 테마 · /vote · /classes 분리)에 맞춰 수정
· 등수는 "요청이 서버에 도착한 순서"로 결정
· 직업은 브라우저에 저장 후 접속 시 서버로 자동 재등록
  → Render 슬립/재배포로 서버가 초기화돼도 다시 고를 필요 없음
· 표준 라이브러리만 사용

실행:  python practice_site.py
────────────────────────────────────────────────────────────
"""
import os
import json
import time
import mimetypes
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, unquote

PORT = int(os.environ.get("PORT", "8000"))

# 이미지 폴더: 이 파이썬 파일과 같은 위치의 static/ 안에
#   static/class-icons/Class_Icon_Sage.png  … (32개 직업)
#   static/marks/succession.png, awakening.png
#   static/img/hero.png
# 파일이 없으면 자동으로 글자 아이콘으로 대체되므로, 일부만 넣어도 동작합니다.
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

VOTE_LABEL = {"attend": "참여", "boarding": "부속", "late_attend": "늦참", "non_attend": "미참"}
VOTE_ORDER = ["attend", "boarding", "late_attend", "non_attend"]
ATTEND_TYPES = ["attend", "boarding"]

_lock = threading.Lock()
_state = {"id": "none", "status": "idle", "openAt": 0.0, "round": 0}
_entries = {}     # roundId -> [ {...} ]
_profiles = {}    # nickname -> {"name":..., "type":...}
_history = []     # 최근 테스트 요약 (최대 6개)
_last = None


def now_ms() -> float:
    return time.time() * 1000.0


def board_of(rid):
    rows = sorted(_entries.get(rid, []), key=lambda x: x["arrivalMs"])
    return [{"nickname": r["nickname"], "deltaMs": r["deltaMs"], "votingType": r["votingType"],
             "className": r.get("className"), "classType": r.get("classType")} for r in rows]


def archive_current():
    global _last, _history
    b = board_of(_state["id"])
    if b:
        counts = {}
        for e in b:
            counts[e["votingType"]] = counts.get(e["votingType"], 0) + 1
        _last = {"round": _state["round"], "board": b, "counts": counts,
                 "openAt": _state["openAt"]}
        _history = ([{"round": _state["round"], "count": len(b), "openAt": _state["openAt"]}]
                    + _history)[:6]


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
            return False, {"error": "이전 설문입니다. 새로고침하세요."}
        if _state["status"] == "closed":
            return False, {"error": "투표가 마감되었습니다."}
        if _state["status"] != "armed" or arrival < _state["openAt"]:
            return False, {"error": "아직 열리지 않았습니다."}

        rows = _entries.setdefault(rid, [])
        mine = next((r for r in rows if r["nickname"] == nickname), None)
        dup = False
        if mine:
            # 등수는 최초 도착 시각으로 고정
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
               "duplicated": dup, "votedAt": mine["arrivalMs"], "board": b}
    if not dup:
        print(f"  {rank:>3}등  {nickname:<14} {VOTE_LABEL[vtype]:<3} +{res['deltaMs']}ms")
    return True, res


HTML = r"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>거점전 선착순 연습</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Cinzel:wght@400;600;700&family=JetBrains+Mono:wght@400;500&family=Noto+Sans+KR:wght@400;500;700&display=swap" rel="stylesheet">
<link rel="stylesheet" as="style" crossorigin href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css">
<style>
:root{--color-paper:#f3f2f2;--color-surface:#eae9e9;--color-ink:#201f1d;--color-ink-dim:#605d5d;
--color-ink-faint:#7d7979;--color-hairline:#201f1d29;--color-rule:#201f1d1f;--color-accent:#b68235;
--color-accent-deep:#7d5411;--color-accent-deeper:#5a3b0a;--color-accent-tint:#fff3e4;
--color-dark:#1a1918;--color-dark-ink:#f3f2f2;--color-dark-ink-soft:#e2e0dd;--color-dark-ink-dim:#bab6b6;
--color-dark-accent:#e1ad66;--color-dark-accent-bright:#facb8d;--color-mark-succession:#5b7fb5;
--color-mark-awakening:#b0555f;--color-mark-neutral:#201f1d38;--shadow-card:0 3px 10px #2d2b2b1f;
--scrim-band:linear-gradient(180deg,transparent,#1a1918d1);
--shadow-modal:0 8px 28px #2d2b2b38;
--scrim-dark-hero:linear-gradient(180deg,#1a1918db,#1a191880 42%,#1a1918f0)}
:root{--font-korean-serif:"Nanum Myeongjo";--font-korean-sans:"Noto Sans KR";
--font-heading:"Cinzel","Pretendard Variable",Pretendard,var(--font-korean-sans),serif;
--font-prose:"Pretendard Variable",Pretendard,var(--font-korean-sans),sans-serif;
--font-body:"Pretendard Variable",Pretendard,var(--font-korean-sans),sans-serif;
--font-mono:"JetBrains Mono","Pretendard Variable",var(--font-korean-sans),ui-monospace,monospace;
--background:var(--color-paper);--foreground:var(--color-ink);--card-bg:var(--color-paper);
--border-color:var(--color-hairline);--muted:var(--color-ink-dim);--accent:var(--color-accent)}
html{color-scheme:light;height:100%}
html,body{max-width:100vw;overflow-x:hidden}
body{min-height:100%;color:var(--color-ink);background:var(--color-paper);font-family:var(--font-body);
-webkit-font-smoothing:antialiased;flex-direction:column;display:flex}
*{box-sizing:border-box;margin:0;padding:0}
h1,h2,h3,h4{font-family:var(--font-heading);font-weight:600}
a{color:inherit;text-decoration:none}
button{font-family:inherit}
a:focus-visible,button:focus-visible,input:focus-visible{outline:2px solid var(--color-accent);outline-offset:2px}

/* ── SiteHeader ── */
.siteHeader{width:100%;max-width:1120px;margin:0 auto;flex-wrap:wrap;align-items:center;
gap:18.4px;padding:27.6px 46px 18.4px;display:flex}
.brandBlock{align-items:flex-end;gap:9px;margin-right:auto;display:flex}
.brandIcon{object-fit:cover;border-radius:6px;width:28px;height:28px;display:block}
.brand{font-family:var(--font-heading);white-space:nowrap;font-size:22px;font-weight:700}
.kicker{font-family:var(--font-mono);letter-spacing:.16em;color:var(--color-ink-dim);font-size:11px}
.nav{align-items:center;gap:18.4px;display:flex}
.navLink,.navLinkSoon{color:var(--color-ink-dim);font-size:12.5px;cursor:pointer;background:0 0;border:none}
.navLink:hover{color:var(--color-accent-deep)}
.navLinkActive{color:var(--color-ink);font-weight:600}
.navLinkSoon{color:var(--color-ink-faint);cursor:default}
.logoutButton{border:1px solid var(--color-hairline);color:var(--color-ink-dim);cursor:pointer;
background:0 0;border-radius:4px;padding:6px 13.8px;font-size:13.5px;order:1}
.logoutButton:hover{border-color:var(--color-accent);color:var(--color-accent-deep)}
@media (max-width:768px){.siteHeader{gap:11px;padding:18.4px 22px}.brand{font-size:19px}
.nav{flex-basis:100%;order:2;gap:15px}.navLink,.navLinkSoon{white-space:nowrap;font-size:11.5px}}

/* ── 홈 (신규 page-module 기준) ── */
.homeMain{background:var(--color-paper);width:100%;max-width:1120px;min-height:100dvh;
color:var(--color-ink);margin:0 auto}
.hero{background:var(--color-dark);border-radius:4px;height:320px;margin:0 46px;
position:relative;overflow:hidden}
.heroImage{object-fit:cover;width:100%;height:100%;display:block}
.heroScrim{pointer-events:none;background:var(--scrim-band);height:72%;
position:absolute;bottom:0;left:0;right:0}
.heroPattern{position:absolute;inset:0;opacity:.5;
background:radial-gradient(circle at 22% 28%,#3a3630 0,transparent 55%),
radial-gradient(circle at 78% 12%,#2b2823 0,transparent 45%),
repeating-linear-gradient(115deg,#1f1e1c 0 22px,#1a1918 22px 44px)}
.homeBody{padding:27.6px 46px 46px}
.columns{grid-template-columns:1fr 280px;align-items:start;gap:36.8px;display:grid}
.sectionHeader{justify-content:space-between;align-items:baseline;display:flex}
.sectionTitle{letter-spacing:.08em;color:var(--color-ink-dim);font-size:13px;font-weight:600}
.sectionMeta{font-family:var(--font-mono);color:var(--color-ink-dim);font-size:11px}
.sectionLink{color:var(--color-accent-deep);font-size:11px;cursor:pointer}
.sectionLink:hover{color:var(--color-accent-deeper)}
.dayGrid{grid-template-columns:repeat(3,1fr);gap:9.2px;margin-top:18.4px;display:grid}
.dayCard{border:1px solid var(--color-hairline);background:var(--color-surface);border-radius:4px;
flex-direction:column;min-height:124px;padding:17px 16px 15px;display:flex}
.dayCardLive{border-color:var(--color-accent);background:var(--color-accent-tint);
box-shadow:inset 2px 0 0 var(--color-accent)}
.dayCardTop{flex-direction:column;align-items:flex-start;gap:10px;display:flex}
.dayLabel{letter-spacing:.01em;color:var(--color-ink);font-size:22px;font-weight:700;line-height:1}
.dayCardLive .dayLabel{color:var(--color-accent-deeper)}
.dayDate{font-family:var(--font-mono);font-variant-numeric:tabular-nums;letter-spacing:.02em;
color:var(--color-ink-dim);font-size:12px;line-height:1}
.dayCardLive .dayDate{color:var(--color-accent-deep)}
.dayState{letter-spacing:-.01em;white-space:nowrap;color:var(--color-ink-dim);align-self:flex-end;
align-items:center;gap:6px;margin-top:auto;padding-top:14px;font-size:13.5px;font-weight:500;
display:inline-flex}
.dayState:before{content:"";background:var(--color-ink-faint);border-radius:50%;flex:none;
width:5px;height:5px}
.dayStateLive{color:var(--color-accent-deep);font-weight:600}
.dayStateLive:before{background:var(--color-accent)}
.dayVote{color:var(--color-ink-faint);margin-top:auto;font-size:12.5px}
.dayVoteSet{color:var(--color-accent-deep)}
.classCardHome{border:1px solid var(--color-accent);background:var(--color-accent-tint);
border-radius:4px;align-items:center;gap:13.8px;margin-top:18.4px;padding:9.2px 11px;display:flex}
.classCardEmpty{border:1px dashed #201f1d42;border-radius:4px;flex-direction:column;gap:4px;
margin-top:18.4px;padding:13.8px 11px;display:flex}
.classNameTxt{color:var(--color-accent-deeper);font-size:13.5px}
.classCardEmpty .classNameTxt{color:var(--color-ink)}
.classSub{color:var(--color-accent-deep);font-size:11px}
.classCardEmpty .classSub{color:var(--color-ink-dim);line-height:1.5}
.classNote{color:#201f1db8;margin-top:13.8px;font-size:11px;line-height:1.75}
@media (max-width:768px){.hero{height:190px;margin:0 22px}
.heroScrim{background:linear-gradient(#1a19184d 0%,#1a191880 42%,#1a1918f2 100%);height:100%}
.homeBody{padding:18.4px 22px 36.8px}.columns{grid-template-columns:1fr;gap:27.6px}
.dayGrid{gap:6px}.dayCard{min-height:96px;padding:12px 10px 11px}
.dayLabel{font-size:18px}.dayDate{font-size:10px}
.dayState{padding-top:10px;font-size:11.5px}.dayVote{display:none}}

/* ── 로그인 ── */
.loginMain{background:var(--color-paper);justify-content:center;align-items:center;min-height:100dvh;
padding:24px;display:flex}
.loginHero{text-align:center;flex-direction:column;align-items:center;gap:8px;display:flex}
.loginBrand{font-size:46px;font-weight:400;line-height:1.05}
.loginTagline{color:var(--color-ink-dim);font-size:13px}
.loginRow{gap:8px;margin-top:18.4px;display:flex;width:100%;max-width:340px}
.loginInput{flex:1;min-width:0;border:1px solid var(--color-hairline);background:var(--color-paper);
color:var(--color-ink);border-radius:4px;padding:11px 12px;font-size:16px;font-family:inherit;outline:none}
.loginInput:focus{border-color:var(--color-accent)}
.loginButton{border:1px solid var(--color-accent);background:var(--color-accent-tint);
color:var(--color-accent-deeper);border-radius:4px;padding:12px 22px;font-size:13.5px;cursor:pointer;white-space:nowrap}
.loginButton:hover{border-color:var(--color-accent-deep)}

/* ── 투표 ── */
.voteMain{flex-direction:column;align-items:center;gap:16px;min-height:100dvh;padding:24px 16px 48px;display:flex}
.voteHeaderRow{justify-content:space-between;align-items:center;width:100%;max-width:480px;display:flex}
.homeLink{color:var(--color-ink-dim);font-size:.85rem;font-weight:600;cursor:pointer}
.homeLink:hover{color:var(--color-accent-deep)}
.headerRight{align-items:center;gap:12px;display:flex}
.nickname{font-weight:600}
.card{border:1px solid var(--color-hairline);background:var(--card-bg);border-radius:16px;width:100%;
max-width:480px;padding:28px 24px}
.title{margin:0 0 8px;font-size:1.25rem}
.dateLine{margin:0 0 4px;font-weight:600}
.instruction{color:var(--muted);margin:0 0 20px;font-size:.875rem}
.tabBar{background:var(--background);border:1px solid var(--color-hairline);border-radius:12px;
grid-template-columns:repeat(2,1fr);gap:6px;margin-bottom:20px;padding:4px;display:grid}
.tabButton{color:var(--muted);cursor:pointer;background:0 0;border:none;border-radius:9px;padding:10px 8px;
font-size:.85rem;font-weight:600}
.tabButtonActive{background:var(--color-accent-tint);color:var(--color-accent-deeper);
box-shadow:0 0 0 1px var(--color-accent)}
.buttonRow{grid-template-columns:repeat(2,1fr);gap:10px;display:grid}
.voteButton{color:#201f1db3;cursor:pointer;background:0 0;border:1px solid #201f1d4d;border-radius:4px;
min-height:48px;padding:13.8px 12px;font-size:13.5px;transition:border-color .18s,background .18s,color .18s}
.voteButton:hover:not(:disabled){border-color:var(--color-accent);color:var(--color-accent-deep)}
.voteButton:disabled{opacity:.45;cursor:not-allowed}
.selected{border-color:var(--color-accent);background:var(--color-accent-tint);color:var(--color-accent-deeper)}
.notice{color:var(--muted);margin-top:16px;font-size:.9rem;line-height:1.5}
.warning{color:var(--color-accent-deep);margin-top:16px;font-size:.9rem;line-height:1.5}
.message{color:var(--color-accent-deeper);margin-top:16px;font-size:.95rem;font-weight:600}
.errorTxt{color:#b3261e;margin-top:8px;font-size:.85rem}
.classSection{border-top:1px solid var(--color-hairline);margin-top:12px;padding-top:16px}
.classLink{color:var(--color-accent-deep);border-bottom:1px solid #b6823573;margin-top:9.2px;
font-size:12.5px;display:inline-block;cursor:pointer}
.classLink:hover{color:var(--color-accent-deeper);border-bottom-color:var(--color-accent)}
.countdown{font-variant-numeric:tabular-nums;align-items:baseline;gap:8px;margin-top:16px;display:flex}
.countdownSegment{font-size:1.75rem;font-weight:700;font-family:var(--font-mono)}
.countdownSoon{color:var(--accent);margin-top:16px;font-size:1.1rem;font-weight:700}
.summaryList{flex-direction:column;gap:8px;margin:16px 0 0;padding:0;list-style:none;display:flex}
.summaryItem{border:1px solid var(--color-hairline);border-radius:8px;justify-content:space-between;
padding:10px 12px;font-size:.9rem;display:flex}
@media (min-width:1024px){.voteHeaderRow,.card{max-width:880px}}

/* ── 순위 (연습 전용) ── */
.rankItem{border:1px solid var(--color-hairline);border-radius:4px;align-items:center;gap:10px;
padding:9px 12px;font-size:.9rem;display:flex}
.rankItem.first{border-color:var(--color-accent);background:var(--color-accent-tint)}
.rankItem.me{box-shadow:inset 2px 0 0 var(--color-accent)}
.rankNo{font-family:var(--font-mono);font-variant-numeric:tabular-nums;width:26px;
color:var(--color-ink-dim);font-weight:700}
.rankItem.first .rankNo,.rankItem.first .rankMs{color:var(--color-accent-deeper)}
.rankName{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.rankCls{font-size:.75rem;color:var(--color-ink-dim);white-space:nowrap}
.rankMs{font-family:var(--font-mono);font-variant-numeric:tabular-nums;color:var(--color-ink-dim);font-size:.85rem}

/* ── 직업 등록 페이지 ── */
.classesMain{background:var(--color-paper);width:100%;max-width:860px;min-height:100dvh;
flex-direction:column;margin:0 auto;display:flex}
.classesHeader{border-bottom:1px solid var(--color-hairline);justify-content:space-between;
align-items:center;gap:13.8px;padding:18.4px 36.8px;display:flex}
.cbrand{font-family:var(--font-heading);white-space:nowrap;font-size:19px;font-weight:600}
.headerKicker{font-family:var(--font-mono);letter-spacing:.04em;color:var(--color-ink-dim);font-size:10px}
@media (max-width:768px){.classesHeader{padding:18.4px 22px}}
.classesBody{flex:1;padding:36.8px}
.ckicker{font-family:var(--font-mono);letter-spacing:.16em;color:var(--color-accent-deep);font-size:10.5px}
.stepTitle{margin-top:4px;font-size:26px;font-weight:400}
.divider{background:var(--color-hairline);height:1px;margin:27.6px 0}
.branchRow{grid-template-columns:repeat(3,1fr);gap:13.8px;margin-top:13.8px;display:grid}
.branchCard{border:1px solid var(--color-hairline);text-align:left;cursor:pointer;background:0 0;
border-radius:4px;padding:13.8px 18.4px;transition:border-color .18s,background .18s}
.branchCard:hover{border-color:var(--color-accent)}
.branchCardSelected{border-color:var(--color-accent);background:var(--color-accent-tint)}
.branchNum{font-family:var(--font-mono);letter-spacing:.14em;color:var(--color-accent-deep);font-size:10px;display:block}
.branchLabel{font-family:var(--font-body);color:var(--color-ink);font-size:17px;display:block}
.branchCardSelected .branchLabel{color:var(--color-accent-deeper)}
.branchSub{color:var(--color-ink-dim);margin-top:4px;font-size:11.5px;line-height:1.5;display:block}
.stepTwo{opacity:.38;transition:opacity .22s}
.stepTwoActive{opacity:1}
.stepTwoHeader{justify-content:space-between;align-items:baseline;gap:13.8px;display:flex}
.stepTwoHint{font-family:var(--font-mono);color:var(--color-ink-dim);font-size:11px}
.classGrid{grid-template-columns:repeat(8,1fr);gap:9.2px;margin-top:18.4px;display:grid}
.classTile{border:1px solid var(--color-hairline);min-height:76px;color:var(--color-ink);cursor:pointer;
background:0 0;border-radius:4px;flex-direction:column;align-items:center;gap:6px;padding:9.2px 4.6px;
transition:border-color .18s,background .18s,transform .18s;display:flex}
.classTile:hover:not(:disabled){border-color:var(--color-accent);transform:translateY(-2px)}
.classTileSelected{border-color:var(--color-accent);background:var(--color-accent-tint)}
.classTileName{font-family:var(--font-body);text-align:center;font-size:11.5px;line-height:1.2}
.classTileSelected .classTileName{color:var(--color-accent-deeper)}
.classesFooter{border-top:1px solid var(--color-hairline);background:var(--color-surface);
justify-content:space-between;align-items:center;gap:13.8px;padding:18.4px 36.8px;display:flex;
position:sticky;bottom:0}
.summaryKicker{font-family:var(--font-mono);letter-spacing:.04em;color:var(--color-ink-dim);font-size:10px;display:block}
.summaryTxt{margin-top:2px;font-size:13.5px}
.summaryStrong{color:var(--color-accent-deeper)}
.summaryDim{color:var(--color-ink-dim)}
.footerActions{flex-wrap:wrap;justify-content:flex-end;align-items:center;gap:9.2px;display:flex}
.doneTxt{color:var(--color-accent-deep);font-size:11.5px}
.resetButton{border:1px solid var(--color-hairline);min-height:44px;color:var(--color-ink-dim);
cursor:pointer;background:0 0;border-radius:4px;padding:6px 13.8px;font-size:11.5px}
.resetButton:hover{border-color:var(--color-accent);color:var(--color-accent-deep)}
.submitButton{border:1px solid var(--color-accent);background:var(--color-accent-tint);min-height:44px;
color:var(--color-accent-deeper);cursor:pointer;border-radius:4px;padding:9.2px 22px;font-size:13.5px}
.submitButton:disabled{border-color:var(--color-hairline);color:var(--color-ink-faint);
cursor:not-allowed;opacity:.45;background:0 0}
@media (max-width:768px){.classesBody{padding:22px}.stepTitle{font-size:19px}
.branchRow{grid-template-columns:1fr;gap:9.2px}.branchNum{display:none}.divider{margin:22px 0}
.classGrid{grid-template-columns:repeat(4,1fr)}
.classesFooter{flex-direction:column;align-items:stretch;gap:9.2px;padding:13.8px 22px}
.summaryTxt{margin-top:0}.footerActions{justify-content:stretch}.submitButton{flex:1}}

/* ── 직업 아이콘(마크) ── */
.tile{width:34px;height:34px;flex:none;display:inline-flex;position:relative}
.tileImg{object-fit:contain;width:100%;height:100%;display:block;
filter:invert()sepia(.4)brightness(.78)contrast(1.05)}
.classTileSelected .tileImg{filter:invert()sepia(.75)saturate(1.6)brightness(.52)contrast(1.1)}
.tilePlaceholder{background:var(--color-hairline);border-radius:4px;width:100%;height:100%;
display:flex;align-items:center;justify-content:center;font-size:11px;color:var(--color-ink-dim);
font-family:var(--font-body)}
.markImg{image-rendering:pixelated;max-width:11px;max-height:13px}
.classTileSelected .tilePlaceholder{background:#b6823540;color:var(--color-accent-deeper)}
.mark{width:15px;height:15px;background:var(--color-paper);border:1px solid var(--mark-border);
border-radius:50%;position:absolute;bottom:-4px;right:-5px;overflow:hidden;
display:flex;align-items:center;justify-content:center}
.classTileSelected .mark{background:var(--color-accent-tint)}

/* ── 관리자(연습 진행) ── */
.hostBar{border-top:1px dashed var(--color-hairline);margin-top:20px;padding-top:14px}
.hostToggle{color:var(--color-ink-dim);cursor:pointer;background:0 0;border:none;padding:0;
font-family:var(--font-mono);font-size:11px;letter-spacing:.04em}
.hostRow{gap:8px;margin-top:12px;display:flex;flex-wrap:wrap}
.hostBtn{border:1px solid var(--color-hairline);color:var(--color-ink-dim);cursor:pointer;background:0 0;
border-radius:4px;padding:9px 12px;font-size:11.5px;min-height:40px}
.hostBtn:hover{border-color:var(--color-accent);color:var(--color-accent-deep)}
</style></head><body>
<div id="app">불러오는 중…</div>
<script>
// ── 직업 데이터 (신규 사이트 번들 기준: 32종) ──
const CLASS_TYPE_LABEL={Succession:"전승",Awaken:"각성",Else:"기타"};
// 본사이트 번들의 직업→영문 매핑 (아이콘 파일명에 사용)
const CLASS_EN={워리어:"Warrior",소서러:"Sorceress",레인저:"Ranger",자이언트:"Berserker",
금수랑:"Tamer",무사:"Musa",발키리:"Valkyrie",매화:"Maehwa",위자드:"Wizard",위치:"Witch",
쿠노이치:"Kunoichi",닌자:"Ninja",다크나이트:"Dark Knight",격투가:"Striker",미스틱:"Mystic",
란:"Lahn",아처:"Archer",샤이:"Shai",가디언:"Guardian",하사신:"Hashashin",노바:"Nova",
세이지:"Sage",커세어:"Corsair",드라카니아:"Drakania",우사:"Woosa",매구:"Maegu",
스칼라:"Scholar",도사:"Dosa",데드아이:"Deadeye",오공:"WuKong",세라핌:"Serapin",에이전트:"Agent"};
const iconSrc=n=>CLASS_EN[n]?`/class-icons/Class_Icon_${CLASS_EN[n].replace(/ /g,"_")}.png`:"";
// 한 번 실패한 이미지는 기억해두고 다시 요청하지 않는다 (깜빡임 방지)
const IMG_FAIL=new Set();
window.__imgFail=function(el){IMG_FAIL.add(el.getAttribute('src'));el.style.display='none';
  const ph=el.nextElementSibling; if(ph)ph.style.display='flex';
  lastHTML='';};  // 다음 렌더에 반영되도록
const MARK_SRC={Succession:"/marks/succession.png",Awaken:"/marks/awakening.png"};
// 아이콘 파일이 없으면 글자로 자동 대체
function iconHTML(name,type,cls){
  let src=iconSrc(name); const mark=MARK_SRC[type]||"";
  const useImg=src&&!IMG_FAIL.has(src);           // 실패 이력이 있으면 글자만 표시
  const useMark=mark&&!IMG_FAIL.has(mark);
  return `<span class="tile ${cls||''}">
    ${useImg?`<img class="tileImg" src="${src}" alt="${esc(name)}" onerror="__imgFail(this)">`:''}
    <span class="tilePlaceholder" ${useImg?'style="display:none"':''}>${esc(name.slice(0,2))}</span>
    <span class="mark" style="--mark-border:${markColor(type)}">
      ${useMark?`<img class="markImg" src="${mark}" alt="" onerror="__imgFail(this)">`:''}</span></span>`;
}
const CLASS_TYPE_SUBLABEL={Succession:"주 무기 계열",Awaken:"각성 무기 계열",Else:"개방 · 재능 계열"};
const ELSE_C=["아처","샤이","스칼라","데드아이","오공","세라핌"];
const DUAL_C=["워리어","소서러","레인저","자이언트","금수랑","무사","발키리","매화","위자드","위치",
"쿠노이치","닌자","다크나이트","격투가","미스틱","란","가디언","하사신","노바","세이지","커세어",
"드라카니아","우사","매구","도사","에이전트"];
const clsFor=t=>t==="Else"?ELSE_C:DUAL_C;
const markColor=t=>t==="Succession"?"var(--color-mark-succession)"
  :t==="Awaken"?"var(--color-mark-awakening)":"var(--color-mark-neutral)";

const VOTE_ORDER=["attend","boarding","late_attend","non_attend"];
const VOTING_TYPE_LABEL={attend:"참여",boarding:"부속",late_attend:"늦참",non_attend:"미참"};
const ATTEND_TYPES=["attend","boarding"];

const $=id=>document.getElementById(id);
const app=$('app');
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pad=n=>String(n).padStart(2,"0");
// 본사이트 formatSurveyDate / formatSurveyTime 와 동일 (Asia/Seoul 기준)
const DOW=["일","월","화","수","목","금","토"];
function fmtDate(ms){
  const p=new Intl.DateTimeFormat("en-CA",{timeZone:"Asia/Seoul",year:"numeric",month:"2-digit",day:"2-digit"}).formatToParts(new Date(ms));
  const g=t=>{const x=p.find(v=>v.type===t);return x?x.value:"";};
  const d=new Date(new Date(ms).toLocaleString("en-US",{timeZone:"Asia/Seoul"})).getDay();
  return `${g("year")}-${g("month")}-${g("day")} (${DOW[d]})`;
}
const fmtTime=ms=>new Intl.DateTimeFormat("ko-KR",{timeZone:"Asia/Seoul",hour:"2-digit",minute:"2-digit",hour12:false}).format(new Date(ms));
const clsLabel=e=>e.className?`${e.className} (${CLASS_TYPE_LABEL[e.classType]||'?'})`:'직업 미등록';

// ── 상태 ──
const LS_NICK='ps_nick',LS_PROF='ps_prof';
let nick=null,prof=null;
try{nick=localStorage.getItem(LS_NICK);}catch(e){}
try{const r=localStorage.getItem(LS_PROF);prof=r?JSON.parse(r):null;}catch(e){}
let route=location.pathname,st=null,board=[],last=null,history=[],offset=0;
let tab='current',myVote=null,myRank=null,myMs=null,myVotedAt=null,msg=null,err=null,busy=false;
let pickType=null,pickName=null,saving=false,savedMsg=null;
let hostOpen=false,autoSwitched=false,lastSync=0,tickTimer=null;

function saveProf(p){try{p?localStorage.setItem(LS_PROF,JSON.stringify(p)):localStorage.removeItem(LS_PROF);}catch(e){}}
async function api(p,b){
  const o=b?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)}:{};
  return (await fetch(p,o)).json();
}
async function syncProfToServer(){
  if(!nick||!prof)return;
  try{await api('/api/profile',{nickname:nick,name:prof.name,type:prof.type});}catch(e){}
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

function go(path){
  if(location.pathname!==path)history.pushState?history.pushState({},'',path):null;
  route=path;pickType=null;pickName=null;savedMsg=null;render();
}
function navigate(path){window.history.pushState({},'',path);route=path;
  pickType=null;pickName=null;savedMsg=null;render();}

async function pull(){
  let j;
  try{j=await api('/api/state');}catch(e){return;}
  const prev=st&&st.id;
  st=j.state;board=j.board;last=j.last;history=j.history||[];
  if(st.id!==prev){myVote=null;myRank=null;myMs=null;myVotedAt=null;msg=null;err=null;autoSwitched=false;syncProfToServer();}
  if(Date.now()-lastSync>30000){lastSync=Date.now();syncProfToServer();}
  if(isLive()&&!autoSwitched){autoSwitched=true;tab='current';}
  render();
}
async function castVote(type){
  if(busy||!st)return;
  busy=true;err=null;render();
  try{
    const j=await api('/api/vote',{nickname:nick,roundId:st.id,type});
    if(j.ok){
      myVote=j.votingType;myRank=j.rank;myMs=j.deltaMs;myVotedAt=j.votedAt;board=j.board;
      msg=j.duplicated?`이미 ${VOTING_TYPE_LABEL[j.votingType]}를 선택한 상태입니다.`
                      :`${VOTING_TYPE_LABEL[j.votingType]} 선택.`;
    }else{err=j.error;}
  }catch(e){err='투표 처리 중 오류가 발생했습니다.';}
  busy=false;render();
}
async function submitClass(){
  if(!pickName||!pickType||saving)return;
  saving=true;render();
  prof={name:pickName,type:pickType};
  saveProf(prof);
  await syncProfToServer();
  await pull();
  saving=false;savedMsg='등록 완료';render();
}

// ── 공통 헤더 ──
function siteHeaderHTML(active){
  const link=(p,l)=>`<span class="navLink ${route===p?'navLinkActive':''}" data-go="${p}">${l}</span>`;
  return `<header class="siteHeader">
    <div class="brandBlock">
      ${IMG_FAIL.has('/img/brand.png')?'':`<img class="brandIcon" src="/img/brand.png" alt="" onerror="__imgFail(this)">`}
      <span class="brand">아시바당</span>
      <span class="kicker">연습 · PRACTICE</span></div>
    <nav class="nav">
      ${link('/','홈')}${link('/vote','투표')}${link('/classes','직업 등록')}
      <span class="navLinkSoon">기록 (준비중)</span>
      <button class="logoutButton" id="btnLogout">가문명 변경</button>
    </nav></header>`;
}

// ── 로그인 ──
function renderLogin(){
  if($('ni'))return;   //
  lastHTML='';
  app.innerHTML=`<main class="loginMain"><div class="loginHero">
    <h1 class="loginBrand">아시바당</h1>
    <p class="loginTagline">거점전 선착순 신청 연습</p>
    <p class="kicker">동일한 주소로 접속한 인원 전원이 함께 참여합니다</p>
    <div class="loginRow"><input class="loginInput" id="ni" placeholder="가문명 입력" maxlength="16">
    <button class="loginButton" id="jb">입장</button></div>
  </div></main>`;
  const i=$('ni');
  const enter=async()=>{const v=i.value.trim();if(!v)return;
    nick=v;try{localStorage.setItem(LS_NICK,v);}catch(e){}
    await syncProfToServer();render();};
  $('jb').onclick=enter;
  i.addEventListener('keydown',e=>{if(e.key==='Enter')enter()});
  i.focus();
}

// ── 홈 ──
function homeHTML(){
  const live=isLive();
  const armed=st&&st.status==='armed'&&!live;
  // 지난 연습 + 현재 라운드를 한 그리드에 (본사이트 dayGrid 스타일)
  const cards=[];
  if(st&&st.round&&(live||armed)){
    cards.push(`<div class="dayCard dayCardLive"><div class="dayCardTop">
      <span class="dayLabel">${st.round}회</span>
      <span class="dayDate">${fmtTime(st.openAt)}</span></div>
      <span class="dayState dayStateLive">${live?'진행중':'대기'}</span>
      <span class="dayVote ${myVote?'dayVoteSet':''}">${myVote?VOTING_TYPE_LABEL[myVote]:'미신청'}</span></div>`);
  }
  (history||[]).slice(0,6-cards.length).forEach(h=>{
    cards.push(`<div class="dayCard"><div class="dayCardTop">
      <span class="dayLabel">${h.round}회</span>
      <span class="dayDate">${fmtTime(h.openAt)}</span></div>
      <span class="dayState">종료</span>
      <span class="dayVote">${h.count}명</span></div>`);
  });

  return `${siteHeaderHTML()}<main class="homeMain">
    <section class="hero">
      <div class="heroPattern"></div>
      ${IMG_FAIL.has('/img/Wallpaper.jpg')?''
        :`<img class="heroImage" src="/img/Wallpaper.jpg" alt="" onerror="__imgFail(this)">`}
      <div class="heroScrim"></div>
    </section>
    <div class="homeBody"><div class="columns">
      <div>
        <div class="sectionHeader"><h2 class="sectionTitle">연습 기록</h2>
          <span class="sectionMeta">최근 ${cards.length}회</span></div>
        <div class="dayGrid">${cards.length?cards.join('')
          :'<div class="dayCard"><span class="dayState">기록 없음</span></div>'}</div>
      </div>
      <aside>
        <div class="sectionHeader"><h2 class="sectionTitle">내 등록 직업</h2>
          <span class="sectionLink" data-go="/classes">변경</span></div>
        ${prof?`<div class="classCardHome">
            ${iconHTML(prof.name,prof.type)}
            <span><span class="classNameTxt">${esc(prof.name)}</span><br>
            <span class="classSub">${CLASS_TYPE_LABEL[prof.type]}</span></span></div>`
          :`<div class="classCardEmpty"><span class="classNameTxt">직업 미등록</span>
            <span class="classSub">등록해두면 실전에서 신청 버튼만 누르면 됩니다.</span></div>`}
        <p class="classNote">등수는 요청이 서버에 도착한 순서로 정해집니다.</p>
      </aside>
    </div></div></main>`;
}

// ── 투표 ──
function currentTabHTML(){
  const live=isLive();
  const closed=st&&st.status==='closed';
  if(!live&&!closed&&st&&st.status==='armed'){
    const s=Math.max(0,Math.floor((st.openAt-srvNow())/1000));
    return `<h1 class="title">거점전 설문조사</h1>
      <p class="dateLine">거점 일시 ${fmtDate(st.openAt)} ${fmtTime(st.openAt)}</p>
      <p class="instruction">설문이 열리면 이 화면이 투표 화면으로 바뀝니다.</p>
      ${s<=0?'<p class="countdownSoon">곧 설문이 열립니다...</p>'
      :`<div class="countdown"><span class="countdownSegment">${pad(Math.floor(s/3600))}:${pad(Math.floor(s%3600/60))}:${pad(s%60)}</span></div>`}`;
  }
  return `<h1 class="title">거점전 설문조사</h1>
  <p class="dateLine">거점 일시 ${st&&st.openAt?fmtDate(st.openAt)+' '+fmtTime(st.openAt):'-'}</p>
  <p class="instruction">선택지는 하나만 선택해주세요. (부속인 경우 부속만 선택)</p>
  <div class="buttonRow">${VOTE_ORDER.map(t=>`
    <button class="voteButton ${myVote===t?'selected':''}" data-v="${t}"
      ${(!live||busy)?'disabled':''}>${VOTING_TYPE_LABEL[t]}</button>`).join('')}</div>
  ${myVotedAt?`<p class="notice">${fmtDate(myVotedAt)} ${fmtTime(myVotedAt)}에 투표 완료</p>`:''}
  ${myRank?`<p class="message">서버 도착 ${myMs}ms · ${myRank}등</p>`:''}
  ${closed?'<p class="notice">투표가 마감되었습니다.</p>':''}
  ${!live&&!closed?'<p class="notice">아직 설문이 열리지 않았습니다.</p>':''}
  ${msg?`<p class="notice">${esc(msg)}</p>`:''}
  ${err?`<p class="errorTxt">${esc(err)}</p>`:''}
  ${!closed&&myVote&&ATTEND_TYPES.includes(myVote)?`<div class="classSection">
    ${prof?`<p class="notice">현재 직업: ${esc(prof.name)} (${CLASS_TYPE_LABEL[prof.type]})</p>`
          :`<p class="warning">⚠️ 직업 미등록! 직업을 등록해야 인원제한결과에 포함됩니다.</p>`}
    <span class="classLink" data-go="/classes">직업 등록 화면 →</span></div>`:''}
  <div class="classSection"><p class="dateLine">순위 (서버 도착 순)</p>
  <ul class="summaryList">${board.length===0?'<li class="summaryItem"><span>아직 신청자가 없습니다.</span></li>'
    :board.map((e,i)=>`<li class="rankItem ${i===0?'first':''} ${e.nickname===nick?'me':''}">
      <span class="rankNo">${i+1}</span><span class="rankName">${esc(e.nickname)}</span>
      <span class="rankCls">${esc(VOTING_TYPE_LABEL[e.votingType])} · ${esc(clsLabel(e))}</span>
      <span class="rankMs">${e.deltaMs}ms</span></li>`).join('')}</ul></div>`;
}
function pastTabHTML(){
  if(!last)return `<h1 class="title">지난 설문</h1><p class="instruction">아직 완료된 연습이 없습니다.</p>`;
  const c=last.counts;
  return `<h1 class="title">지난 설문 (${last.round}회차)</h1>
  <ul class="summaryList">${VOTE_ORDER.map(k=>`
    <li class="summaryItem"><span>${VOTING_TYPE_LABEL[k]}</span><span>${c[k]||0}명</span></li>`).join('')}</ul>
  <p class="notice">총 ${last.board.length}명 참여</p>
  <ul class="summaryList">${last.board.map((e,i)=>`
    <li class="rankItem ${i===0?'first':''} ${e.nickname===nick?'me':''}">
    <span class="rankNo">${i+1}</span><span class="rankName">${esc(e.nickname)}</span>
    <span class="rankCls">${esc(VOTING_TYPE_LABEL[e.votingType])} · ${esc(clsLabel(e))}</span>
    <span class="rankMs">${e.deltaMs}ms</span></li>`).join('')}</ul>`;
}
function voteHTML(){
  const tabs={current:'현재 설문',past:'지난 설문'};
    return `<main class="voteMain">
    <div class="voteHeaderRow">
      <span class="homeLink" data-go="/">← 홈</span>
      <div class="headerRight"><span class="nickname">${esc(nick)}</span>
        <button class="logoutButton" id="btnLogout">로그아웃</button></div>
    </div>
    <div class="card">
      <div class="tabBar" role="tablist">${Object.keys(tabs).map(k=>
        `<button class="tabButton ${tab===k?'tabButtonActive':''}" data-tab="${k}">${tabs[k]}</button>`).join('')}</div>
      <div>${tab==='current'?currentTabHTML():pastTabHTML()}</div>
      <div class="hostBar"><button class="hostToggle" id="ht">${hostOpen?'▲ 연습 진행 닫기':'▼ 연습 진행 (관리자)'}</button>
      ${hostOpen?`<div class="hostRow">
        <button class="hostBtn" data-d="5">5초 후 오픈</button>
        <button class="hostBtn" data-d="10">10초 후 오픈</button>
        <button class="hostBtn" data-d="30">30초 후 오픈</button>
        <button class="hostBtn" data-d="-1">마감</button></div>
        <p class="notice" style="font-size:11.5px">설문을 열면 접속 중인 모두의 화면이 동시에 카운트다운으로 바뀝니다.</p>`:''}</div>
    </div></main>`;
}

// ── 직업 등록 ──
function classesHTML(){
  const activeType=pickType||(prof&&prof.type)||null;
  const selName=pickName||(prof&&prof.name)||null;
  const list=activeType?clsFor(activeType):[];
  return `<main class="classesMain">
    <header class="classesHeader">
      <div class="brandBlock"><span class="cbrand">아시바당</span>
        <span class="headerKicker">직업 등록</span></div>
      <span class="homeLink" data-go="/">← 홈으로</span>
    </header>
    <div class="classesBody">
      <p class="ckicker">STEP 01</p>
      <h1 class="stepTitle">계열 선택</h1>
      <div class="branchRow">${Object.keys(CLASS_TYPE_LABEL).map((t,i)=>`
        <button class="branchCard ${activeType===t?'branchCardSelected':''}" data-t="${t}">
          <span class="branchNum">0${i+1}</span>
          <span class="branchLabel">${CLASS_TYPE_LABEL[t]}</span>
          <span class="branchSub">${CLASS_TYPE_SUBLABEL[t]}</span></button>`).join('')}</div>
      <div class="divider"></div>
    <div class="stepTwo ${activeType?'stepTwoActive':''}">
        <div class="stepTwoHeader">
          <div>
            <p class="ckicker">STEP 02</p>
            <h2 class="stepTitle">직업 선택</h2>
          </div>
          <span class="stepTwoHint">${activeType ? CLASS_TYPE_LABEL[activeType] + ' · ' + list.length + '개 직업' : '계열 먼저 선택'}</span>
        </div>
        <div class="classGrid">${list.map(n=>`
          <button class="classTile ${selName===n&&activeType===(pickType||(prof&&prof.type))?'classTileSelected':''}" data-n="${esc(n)}">
            ${iconHTML(n,activeType)}
            <span class="classTileName">${esc(n)}</span>
          </button>`).join('')}
        </div>
      </div>
    </div>
    <footer class="classesFooter">
      <div class="summaryBlock"><span class="summaryKicker">선택한 직업</span>
        <p class="summaryTxt">${selName&&activeType
          ?`<span class="summaryStrong">${CLASS_TYPE_LABEL[activeType]} · ${esc(selName)}</span>`
          :'<span class="summaryDim">선택 없음</span>'}</p></div>
      <div class="footerActions">
        ${savedMsg?`<span class="doneTxt">${savedMsg}</span>`:''}
        <button class="resetButton" id="btnReset">초기화</button>
        <button class="submitButton" id="btnSave" ${(!pickName||!pickType||saving)?'disabled':''}>
          ${saving?'저장 중…':'등록하기'}</button>
      </div></footer></main>`;
}

// ── 렌더 ──
let lastHTML='';
function render(){
  if(!nick)return renderLogin();
  const html=route==='/vote'?voteHTML():route==='/classes'?classesHTML():homeHTML();
  // 내용이 그대로면 DOM을 건드리지 않는다 → 이미지가 다시 로드되지 않아 깜빡이지 않음
  if(html===lastHTML)return;
  lastHTML=html;
  app.innerHTML=html;

  document.querySelectorAll('[data-go]').forEach(b=>b.onclick=()=>navigate(b.dataset.go));
  const lo=$('btnLogout');
  if(lo)lo.onclick=()=>{try{localStorage.removeItem(LS_NICK);}catch(e){}nick=null;render();};
  document.querySelectorAll('[data-tab]').forEach(b=>b.onclick=()=>{tab=b.dataset.tab;render()});
  document.querySelectorAll('[data-v]').forEach(b=>b.onclick=()=>castVote(b.dataset.v));
  document.querySelectorAll('[data-t]').forEach(b=>b.onclick=()=>{
    pickType=b.dataset.t;pickName=null;savedMsg=null;render()});
  document.querySelectorAll('[data-n]').forEach(b=>b.onclick=()=>{
    pickName=b.dataset.n;savedMsg=null;render()});
  const sv=$('btnSave');if(sv)sv.onclick=submitClass;
  const br=$('btnReset');if(br)br.onclick=()=>{pickType=null;pickName=null;savedMsg=null;render()};
  const ht=$('ht');if(ht)ht.onclick=()=>{hostOpen=!hostOpen;render()};
  document.querySelectorAll('[data-d]').forEach(b=>b.onclick=async()=>{
    const d=Number(b.dataset.d);
    await api(d<0?'/api/reset':'/api/arm',d<0?{}:{delay:d});
    pull();});
}

window.addEventListener('popstate',()=>{route=location.pathname;render();});

(function(){
  render(); // 데이터를 기다리지 않고 화면 즉시 렌더링
  pull(); // 백그라운드에서 서버 상태 로드
  syncClock().then(() => {
    syncProfToServer();
  }); // 백그라운드에서 시간 동기화 및 프로필 전송
  setInterval(pull,1000);
  setInterval(()=>{if(st&&st.status==='armed'&&!isLive())render();},200);
  setInterval(syncClock,60000);
})();

</script>
</body></html>
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
        if not getattr(self, "_head_only", False):
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

    def _serve_static(self, path):
        """static/ 폴더의 이미지를 서빙. 없으면 404(프론트가 알아서 글자로 대체)."""
        rel = unquote(path.lstrip("/"))
        full = os.path.normpath(os.path.join(STATIC_DIR, rel))
        # 상위 경로 탈출 방지
        if not full.startswith(STATIC_DIR) or not os.path.isfile(full):
            return self._json({"error": "not found"}, 404)
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        with open(full, "rb") as f:
            raw = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "public, max-age=86400")
        self.end_headers()
        if not getattr(self, "_head_only", False):
            self.wfile.write(raw)

    def do_GET(self):
        path = urlparse(self.path).path
        # 본사이트와 동일한 경로 구조: / (홈), /vote (투표), /classes (직업 등록)
        if path in ("/", "/vote", "/classes"):
            return self._send(HTML, "text/html; charset=utf-8")
        if path.startswith(("/class-icons/", "/marks/", "/img/")):
            return self._serve_static(path)
        if path == "/api/time":
            return self._json({"now": now_ms()})
        if path == "/api/state":
            with _lock:
                return self._json({"state": _state, "board": board_of(_state["id"]),
                                   "last": _last, "history": _history})
        if path == "/api/profile":
            q = parse_qs(urlparse(self.path).query)
            with _lock:
                return self._json({"profile": _profiles.get((q.get("nickname") or [""])[0])})
        return self._json({"error": "not found"}, 404)

    def do_HEAD(self):
        # 일부 프록시/브라우저가 HEAD를 먼저 보내므로 GET과 동일하게 처리 (본문만 생략)
        self._head_only = True
        try:
            self.do_GET()
        finally:
            self._head_only = False

    def do_POST(self):
        arrival = now_ms()          # 등수 기준: 요청이 서버에 도착한 시각
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
                _state["status"] = "closed"
                _state["openAt"] = 0.0
                return self._json({"ok": True, "state": _state})

        if path == "/api/profile":
            nick = (data.get("nickname") or "").strip()
            name, ctype = data.get("name"), data.get("type")
            if nick and name and ctype:
                with _lock:
                    _profiles[nick] = {"name": name, "type": ctype}
                    # 이미 신청한 상태면 순위표의 직업 표시도 즉시 갱신
                    # (등수와 도착 시각은 최초 클릭 기준 유지)
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
    print("\n  경로:  /  홈   ·   /vote  투표   ·   /classes  직업 등록")
    print("  등수 기준: 요청이 서버에 도착한 순서")
    print("  직업은 각자 브라우저에 저장되어 서버 재시작 후에도 유지됩니다.")
    print("  종료: Ctrl+C\n")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n종료합니다.")
