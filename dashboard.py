"""Local dashboard (Frosted Forest Glass, v2). Run: python main.py dash  ->  http://127.0.0.1:8765 (auto-refreshes every 30 s).

Chart view: pick a stock with the watchlist tabs (or ?s=SYMBOL). ?p=0 hides candlestick-pattern labels.
Charts are display only - patterns are NOT used by the trading rules (rule version unchanged).

v2: the page is a static shell plus one JSON blob; the chart is drawn on a canvas in the browser (no Plotly / CDN script),
the forest background is rasterised once, and animations only use cheap compositor properties, so it stays smooth.
Look: Palomar-style cream / forest editorial theme with a video hero; light + dark mode (button in the navbar).
The page updates its data in place every 30 s (GET /data), so the video never restarts.
Widget: python main.py widget -> small always-on-top desktop window (GET /widget) with the same theme + video; shows the
watchlist, and switches to the live trades while the live engine is running and has trades.
"""
import base64
import json
import os
import time
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pandas as pd

import db
import report

_px = {}
_bars = {}


def bars(sym):
    """Today's 5-min bars for a symbol, cached for 60 s. None if unavailable."""
    hit = _bars.get(sym)
    if hit and time.time() - hit[0] < 60:
        return hit[1]
    try:
        import data
        df = data.fetch(sym, "5m", "1d")
        if not len(df):                                          # market closed / pre-open: show the last session instead
            df = data.fetch(sym, "5m", "5d")
            df = df[df.index.date == df.index[-1].date()] if len(df) else df
        df = df if len(df) else None
    except Exception:
        df = None
    _bars[sym] = (time.time(), df)
    return df


def fetch_all_bars(syms):
    """Bars for several symbols at once. One-by-one Yahoo calls made a cold load take about a second per stock."""
    if len(syms) < 2:
        return {s: bars(s) for s in syms}
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=4) as ex:
        return dict(zip(syms, ex.map(bars, syms)))


def last_price(sym):
    """Latest 5-min close for an open position, cached for 60 s. None if unavailable."""
    hit = _px.get(sym)
    if hit and time.time() - hit[0] < 60:
        return hit[1]
    df = bars(sym)
    p = float(df.close.iloc[-1]) if df is not None else None
    _px[sym] = (time.time(), p)
    return p


def _bg_file():
    """Optional own photo: put bg.jpg / bg.png / bg.webp in the project folder."""
    for ext in ("jpg", "jpeg", "png", "webp"):
        if os.path.exists(f"bg.{ext}"):
            return f"bg.{ext}"
    return None


CSS = r"""html,body{background:var(--bg);margin:0}
html{overflow-x:clip;scroll-behavior:smooth}
:root{color-scheme:light;--bg:#faf8f5;--ink:#2d3a2e;--onink:#fff;--green:#3d5a3e;--bignum:#1f2b21;--dim:rgba(45,58,46,.62);--faint:rgba(45,58,46,.45);
  --pos:#2f8f5b;--neg:#c4503f;--accent:#b8803f;--blue:#3b6ea5;
  --glass:rgba(255,255,255,.62);--panel:rgba(255,255,255,.74);--pill:rgba(255,255,255,.6);--edge:rgba(45,58,46,.14);--tile:rgba(255,255,255,.5);
  --hover:var(--hover);--line:rgba(45,58,46,.1);--tipbg:rgba(255,255,255,.94);--prebg:rgba(45,58,46,.05);--thumb:rgba(45,58,46,.25);
  --chipopen:#8a5c22;--chipwatch:#1f6b40;--scrim:0;
  --c-grid:rgba(45,58,46,.09);--c-label:rgba(45,58,46,.55);--c-cross:rgba(45,58,46,.35);--c-or:rgba(45,58,46,.45);--c-neutral:#6b7a6c;
  --ease:cubic-bezier(.16,1,.3,1);
  --serif:'Helvetica Neue Light',Helvetica,Arial,sans-serif;--sans:'Helvetica Neue Light',Helvetica,Arial,sans-serif;--mono:'Helvetica Neue Light',Helvetica,Arial,sans-serif}
:root[data-theme=dark]{color-scheme:dark;--bg:#0d1710;--ink:#e8f1ec;--onink:#0d1710;--green:#9fd3b0;--bignum:#f1f7f3;--dim:rgba(232,241,236,.68);--faint:rgba(232,241,236,.45);
  --pos:#4cd27a;--neg:#ff7a6d;--accent:#f0a35e;--blue:#7cc0ff;
  --glass:rgba(16,32,22,.58);--panel:rgba(10,22,14,.66);--pill:rgba(10,22,14,.5);--edge:rgba(255,255,255,.16);--tile:rgba(6,16,10,.45);
  --hover:rgba(255,255,255,.1);--line:rgba(255,255,255,.1);--tipbg:rgba(8,18,12,.92);--prebg:rgba(0,0,0,.28);--thumb:rgba(255,255,255,.25);
  --chipopen:#ffc994;--chipwatch:#9cf0b9;--scrim:1;
  --c-grid:rgba(255,255,255,.08);--c-label:rgba(232,241,236,.55);--c-cross:rgba(255,255,255,.3);--c-or:rgba(215,230,220,.55);--c-neutral:#a9bfb2}
*{box-sizing:border-box}
::selection{background:rgba(61,90,62,.25)}
body{min-height:100vh;color:var(--ink);font-family:var(--sans);font-size:15px;line-height:1.5;-webkit-font-smoothing:antialiased;-moz-osx-font-smoothing:grayscale;overflow-x:hidden}
.pos{color:var(--pos)}.neg{color:var(--neg)}.dim{color:var(--dim)}
.num{font-variant-numeric:tabular-nums}
.bg,.vig,.grain{display:none}

/* ---------- video stage (hero) ---------- */
.stage{position:relative;overflow:hidden;min-height:640px;background:var(--bg);border-radius:0 0 32px 32px}
.stage::before{content:"";position:absolute;inset:0;z-index:1;background:rgba(6,14,9,.55);opacity:var(--scrim);pointer-events:none;transition:opacity .4s}
.stage video{z-index:0;position:absolute;inset:0;width:100%;height:100%;object-fit:cover;object-position:bottom}
.wrap{position:relative;z-index:10;max-width:1280px;margin:0 auto;padding:max(22px,env(safe-area-inset-top)) 32px 40px}
.wrap.main{padding:40px 32px 72px}

#v1{opacity:0}.stage video{will-change:transform,opacity}

/* ---------- navbar ---------- */
header{position:relative;display:flex;align-items:center;gap:10px;flex-wrap:wrap;min-height:48px}
#livePill{margin-right:auto}
.pill{display:inline-flex;align-items:center;gap:8px;padding:8px 16px;border-radius:999px;font-size:13px;color:var(--ink);
  background:var(--pill);border:1px solid var(--edge);backdrop-filter:blur(4px);-webkit-backdrop-filter:blur(4px)}
.dot{position:relative;width:8px;height:8px;border-radius:50%;background:var(--pos)}
.dot::after{content:'';position:absolute;inset:0;border-radius:50%;background:var(--pos);will-change:transform,opacity;animation:ping 1.8s steps(10,end) infinite}
@keyframes ping{0%{transform:scale(1);opacity:.7}70%,100%{transform:scale(3.2);opacity:0}}
@media(min-width:900px){
  #livePill{margin-right:0}
  #livePill{order:-1}.spacer{flex:1}
}
.spacer{display:none}@media(min-width:900px){.spacer{display:block}}

/* hero numerals */
.hero{display:grid;grid-template-columns:minmax(0,1.5fr) minmax(0,1fr);gap:48px;align-items:end;padding:72px 0 8px}
.balcard{padding:26px 32px 24px;border-radius:24px;background:var(--panel);border:1px solid var(--edge);box-shadow:0 10px 40px rgba(0,0,0,.12);backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);justify-self:start;min-width:0;max-width:100%}
.eyebrow{font-size:12px;letter-spacing:.25em;text-transform:uppercase;color:var(--ink);opacity:.7}
.big{color:var(--bignum);font-weight:400;font-size:clamp(48px,7.4vw,104px);line-height:.95;letter-spacing:-.04em;margin:14px 0;white-space:nowrap;font-variant-numeric:tabular-nums}
.big .cur{color:var(--green);font-size:.42em;letter-spacing:-.01em;margin-right:.18em;vertical-align:.52em}
.big .dec{color:var(--green)}
.herosub{font-size:14px;color:var(--ink);opacity:.85;max-width:34rem}
.herosub b{font-weight:400;color:var(--ink)}
.stats{display:flex;flex-direction:column;padding:4px 24px;border-radius:24px;background:var(--panel);border:1px solid var(--edge);backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px)}
.stat{display:flex;justify-content:space-between;align-items:baseline;gap:16px;padding:16px 0;border-top:1px solid var(--line)}
.stat:first-child{border-top:0}
.stat .k{font-size:12px;letter-spacing:.2em;text-transform:uppercase;color:var(--dim)}
.stat .s{display:block;margin-top:4px;font-size:12px;letter-spacing:0;text-transform:none;color:var(--faint)}
.stat .v{font-weight:400;font-size:clamp(28px,3.4vw,42px);letter-spacing:-.03em;line-height:1;white-space:nowrap}

/* cards */
.glass{position:relative;background:var(--glass);border:1px solid var(--edge);border-radius:24px;padding:22px 24px;
  backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);box-shadow:0 10px 40px rgba(0,0,0,.1)}
h2{margin:0 0 14px;font-size:12px;font-weight:400;letter-spacing:.22em;text-transform:uppercase;color:var(--dim)}
h2 i{font-style:normal;letter-spacing:-.01em;text-transform:none;font-size:15px;color:var(--ink);margin-left:6px}
.grid{display:grid;grid-template-columns:minmax(0,1.9fr) minmax(0,1fr);gap:20px;align-items:start;margin-bottom:20px}
.col{display:flex;flex-direction:column;gap:20px;min-width:0}

/* chart */
#cbody{transition:opacity .2s}#cbody.busy{opacity:.45}
.chart-head{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;margin-bottom:10px}
.sym{font-weight:400;font-size:34px;letter-spacing:-.03em;line-height:1}
.sym .px{font-size:15px;letter-spacing:0;margin-left:12px;color:var(--ink)}
.sym .chg{font-size:12px;letter-spacing:0;margin-left:8px}
.meta{font-size:12px;color:var(--dim);margin-top:6px}
.btn{white-space:nowrap;flex:none;font:inherit;font-size:13px;cursor:pointer;padding:8px 16px;min-height:36px;border-radius:999px;color:var(--ink);background:transparent;border:1px solid var(--edge);transition:background .25s,color .25s}
.btn:hover{background:var(--hover)}
.btn[aria-pressed=true]{color:var(--onink);background:var(--ink);border-color:var(--ink)}
.btn:focus-visible,.tab:focus-visible,.seg a:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.tip{position:absolute;left:0;top:0;will-change:transform;pointer-events:none;z-index:5;padding:9px 12px;border-radius:12px;font-size:11px;line-height:1.55;white-space:nowrap;
  background:var(--tipbg);color:var(--ink);border:1px solid var(--edge);box-shadow:0 6px 24px rgba(0,0,0,.18);opacity:0;transition:opacity .15s;font-variant-numeric:tabular-nums}
.legend{display:flex;flex-wrap:wrap;gap:6px 18px;margin-top:12px;font-size:11px;color:var(--dim)}
.legend span{display:inline-flex;align-items:center;gap:7px}
.legend i{display:inline-block;width:18px;height:0;border-top:2px dashed}
.cw{position:relative;height:440px}.cw.compact{height:270px}
.cw canvas{width:100%;height:100%;display:block}.cw .ov{position:absolute;inset:0;cursor:crosshair}
.ctl{display:flex;gap:8px;align-items:center;flex-wrap:wrap;justify-content:flex-end}
.seg{display:inline-flex;border:1px solid var(--edge);border-radius:999px;padding:3px;gap:2px}
.seg a{display:inline-flex;align-items:center;min-height:30px;padding:0 14px;border-radius:999px;font-size:13px;color:var(--ink);text-decoration:none;transition:background .25s,color .25s}
.seg a:hover{background:var(--hover)}.seg a[aria-pressed=true]{background:var(--ink);color:var(--onink)}
.cgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(440px,100%),1fr));gap:16px}
.mini{background:var(--tile);border:1px solid var(--edge);border-radius:18px;padding:14px 14px 4px;min-width:0}
.mhead{display:flex;align-items:baseline;gap:10px;margin-bottom:6px;flex-wrap:wrap}
.msym{font-weight:400;font-size:22px;letter-spacing:-.02em;color:var(--ink);text-decoration:none}
.msym:hover{text-decoration:underline}.mpx{font-size:13px}.mchg{font-size:11px}

/* watchlist */
.tabs{display:flex;gap:6px;flex-wrap:wrap}
.tab{font:inherit;font-size:13px;cursor:pointer;padding:8px 16px;min-height:38px;border-radius:999px;color:var(--ink);background:transparent;border:1px solid transparent;transition:background .25s,color .25s;text-decoration:none;display:inline-flex;align-items:center}
.tab:hover{background:var(--hover)}
.tab[aria-selected=true]{background:var(--ink);color:var(--onink)}
.tab[aria-selected=true] small{color:var(--onink)!important;opacity:.85}
.tab small{font-size:10px;margin-left:6px}

/* heartbeat */
.beat{display:flex;align-items:center;gap:18px}
.pulse{position:relative;width:88px;height:88px;flex:none}
.pulse svg{position:absolute;inset:0;width:100%;height:100%}
.ringfx{position:absolute;inset:10%;border-radius:50%;border:2px solid var(--pos);will-change:transform,opacity;animation:ring 2.4s steps(14,end) infinite}
@keyframes ring{0%{transform:scale(.85);opacity:.7}100%{transform:scale(1.15);opacity:0}}
.beat .msg{font-size:12px;letter-spacing:.12em;font-weight:400;color:var(--pos)}
.beat .sub{font-size:12px;color:var(--dim);margin-top:4px}
.beat.off .ringfx{animation:none;opacity:.25}
.beat .msg.off,.dot.off{color:var(--dim)}.dot.off{background:var(--dim)}.dot.off::after{display:none}

/* tables */
.scroll{overflow-x:auto;margin:0 -8px;padding:0 8px 6px}
table{border-collapse:collapse;width:100%}
th{font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:var(--faint);font-weight:400;text-align:left;padding:8px 12px}
td{padding:13px 12px;border-top:1px solid var(--line);white-space:nowrap;font-size:14px}
td.r,th.r{text-align:right}
tbody tr{transition:background .2s}tbody tr:hover{background:var(--hover)}
.tag{display:inline-block;padding:2px 10px;border-radius:999px;font-size:11px;letter-spacing:.1em;border:1px solid currentColor}
.chip{display:inline-block;padding:2px 10px;border-radius:999px;font-size:12px;background:var(--hover);color:var(--ink)}
.chip.open{background:rgba(184,128,63,.18);color:var(--chipopen)}
.chip.watching{background:rgba(47,143,91,.16);color:var(--chipwatch)}
.chip.extra{color:var(--dim)}
.full{margin-bottom:20px}
pre{margin:0;padding:18px 20px;overflow-x:auto;background:var(--prebg);border:1px solid var(--line);border-radius:16px;color:var(--ink);font-family:ui-monospace,'SF Mono',Menlo,Consolas,monospace;font-size:12.5px;line-height:1.7}

/* entrance (same easing + stagger as the Palomar page) */
@keyframes rise{from{opacity:0;transform:translateY(20px)}to{opacity:1;transform:none}}
.rise{animation:rise .8s var(--ease) backwards;animation-delay:calc(var(--i,0)*120ms)}
.seen .rise{animation:none}

/* themed scrollbars */
html,body{scrollbar-width:none}html::-webkit-scrollbar,body::-webkit-scrollbar{display:none;width:0;height:0}   /* page still scrolls, just no bar (body too: its overflow-x:hidden can make it the scroller) */
.scroll,pre{scrollbar-width:thin;scrollbar-color:var(--thumb) transparent}
@supports selector(::-webkit-scrollbar){
  html,body{scrollbar-width:none}
  .scroll,pre{scrollbar-width:auto;scrollbar-color:auto}
  ::-webkit-scrollbar{width:10px;height:10px;background:transparent}
  ::-webkit-scrollbar-track,::-webkit-scrollbar-corner{background:transparent}
  ::-webkit-scrollbar-button{display:none;width:0;height:0}
  ::-webkit-scrollbar-thumb{background:var(--thumb);border-radius:999px;border:3px solid transparent;background-clip:padding-box}
  ::-webkit-scrollbar-thumb:hover{background:var(--faint);background-clip:padding-box}
}

@media(max-width:900px){
  .wrap{padding:max(16px,env(safe-area-inset-top)) 18px 32px}.wrap.main{padding:28px 18px 56px}
  .hero{grid-template-columns:1fr;gap:28px;padding:48px 0 8px}
  .grid{grid-template-columns:1fr}
  .glass{padding:18px}
  .sym{font-size:28px}
  .sym .px{display:block;margin:6px 0 0}.sym .chg{margin-left:0}
  .chart-head>div{min-width:0}
  header .pill.hide-m{display:none}
  .cw{height:340px}.cw.compact{height:240px}
}
@media(prefers-reduced-motion:reduce){*,*::before,*::after{animation:none!important;transition:none!important}}

.themebtn{cursor:pointer;font:inherit;padding:8px 11px;color:var(--ink)}
.themebtn svg{width:16px;height:16px;display:block}
:root[data-theme=dark] .i-moon,:root:not([data-theme=dark]) .i-sun{display:none}
"""

HEAD_JS = "try{var r=document.documentElement;r.classList.add('js');r.dataset.theme=localStorage.getItem('nsetheme')||(matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light');if(sessionStorage.getItem('nsepx'))r.classList.add('seen');else sessionStorage.setItem('nsepx','1')}catch(e){}"

JS = r"""(function(){
'use strict';
var D=window.__D,RM=matchMedia('(prefers-reduced-motion: reduce)').matches,root=document.documentElement,SEEN=root.classList.contains('seen');
var $=function(id){return document.getElementById(id)};
function esc(x){return String(x).replace(/[&<>"']/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]})}
function pad(n){return String(n).padStart(2,'0')}
var TH={};function readTheme(){var cs=getComputedStyle(root);['grid','label','cross','or','neutral'].forEach(function(k){TH[k]=cs.getPropertyValue('--c-'+k).trim()})}


/* ---------- data ---------- */
var BARS={},DC={};
function loadBars(){BARS={};DC={};Object.keys(D.bars).forEach(function(s){var b=D.bars[s];BARS[s]=b?b.t.map(function(_,i){return{o:b.o[i],h:b.h[i],l:b.l[i],c:b.c[i],v:b.v[i]}}):null})}
loadBars();
function tstr(sym,i){var t=D.bars[sym].t[0].split(':'),m=(+t[0])*60+(+t[1])+i*5;return pad(Math.floor(m/60)%24)+':'+pad(m%60)}
function vwap(b){var pv=0,v=0,any=false,last=null;var out=b.map(function(x){var tp=(x.h+x.l+x.c)/3;pv+=tp*x.v;v+=x.v;if(x.v>0)any=true;if(v>0)last=pv/v;return last});return any?out:null}
function patterns(b){
  var out=[];
  for(var i=0;i<b.length;i++){
    var o=b[i].o,h=b[i].h,l=b[i].l,c=b[i].c,rg=h-l;if(rg<=0)continue;
    var body=Math.abs(c-o),up=h-Math.max(o,c),lo=Math.min(o,c)-l;
    if(body<=.1*rg)out.push([i,'Doji','neutral']);
    else if(body<=.35*rg&&lo>=2*body&&up<=.3*rg)out.push([i,'Hammer','bull']);
    else if(body<=.35*rg&&up>=2*body&&lo<=.3*rg)out.push([i,'Shooting star','bear']);
    if(i>0){var po=b[i-1].o,pc=b[i-1].c,pb=Math.abs(pc-po),pu=pc>po,cu=c>o;
      if(pb>0&&pu!==cu&&body>pb&&Math.max(o,c)>=Math.max(po,pc)&&Math.min(o,c)<=Math.min(po,pc))out.push([i,cu?'Bull engulfing':'Bear engulfing',cu?'bull':'bear'])}
  }
  return out;
}
function derived(sym){var c=DC[sym];if(!c){var b=BARS[sym];c=DC[sym]={vw:vwap(b),pats:patterns(b)}}return c}

/* ---------- formatting ---------- */
var IN=function(v,d){return Number(v).toLocaleString('en-IN',{minimumFractionDigits:d,maximumFractionDigits:d})};
function signed(v,d){return(v>0?'+':v<0?'\u2212':'')+IN(Math.abs(v),d==null?2:d)}
function cls(v){return v>0?'pos':v<0?'neg':''}
function money(v){return v==null?'<span class="dim">n/a</span>':'<span class="num '+cls(v)+'">'+signed(v)+'</span>'}
function bigHTML(v){var s=IN(v,2).split('.');return '<span class="cur">Rs</span>'+s[0]+'<span class="dec">.'+s[1]+'</span>'}
function side(s){return '<span class="tag '+(s==='LONG'?'pos':'neg')+'">'+esc(s)+'</span>'}
function table(head,rows,right){
  if(!rows.length)return '<p class="dim">Nothing yet.</p>';
  return '<div class="scroll"><table><thead><tr>'+head.map(function(h,i){return '<th'+(right.indexOf(i)>-1?' class="r"':'')+'>'+h+'</th>'}).join('')+'</tr></thead><tbody>'+
    rows.map(function(r){return '<tr>'+r.map(function(c,i){return '<td'+(right.indexOf(i)>-1?' class="r num"':'')+'>'+c+'</td>'}).join('')+'</tr>'}).join('')+'</tbody></table></div>'}

/* ---------- page content ---------- */
var S={sym:D.sel,pat:D.showPat},booted=false;
var hbAge=D.hbAge;
function render(){
  $('upd').textContent=D.updated;
  $('pillTxt').textContent=D.pill;$('pillDot').className='dot'+(D.live?'':' off');
  $('heroSub').innerHTML='Start <b class="num">'+IN(D.capital,0)+'</b> + added <b class="num">'+signed(D.funds,0)+'</b> + closed trades <b class="num '+cls(D.realizedAll)+'">'+signed(D.realizedAll)+'</b>. Open positions are marked to the last 5-minute close.';
  $('todaySub').innerHTML='realized '+money(D.realizedToday);
  $('today').className='v '+cls(D.total);$('today').innerHTML=D.total==null?'<span class="dim">n/a</span>':signed(D.total);
  $('open').textContent=D.nOpen;$('openSub').innerHTML='P&amp;L '+money(D.unreal)+' before exit costs';
  if(D.nClosed){$('win').innerHTML=Math.round(100*D.wins/D.nClosed)+'<span style="font-size:.5em;color:var(--dim)">%</span>';$('winSub').textContent=D.wins+' of '+D.nClosed+' closed trades won'}
  else{$('win').innerHTML='<span class="dim">\u2014</span>';$('winSub').textContent='no closed trades yet'}
  if(!SEEN&&!RM&&!booted){var t0=null;(function f(t){t0=t0||t;var k=Math.min((t-t0)/1400,1),e=1-Math.pow(1-k,3);$('bal').innerHTML=bigHTML(D.balance*e);if(k<1)requestAnimationFrame(f)})(performance.now())}
  else $('bal').innerHTML=bigHTML(D.balance);

  $('today-date').textContent='('+D.today+')';
  $('tradesBox').innerHTML=table(['Stock','Side','Qty','Entry','Stop','Target','Exit / now','Net Rs'],D.trades.map(function(t){
    return ['<b style="font-weight:600">'+esc(t.symbol)+'</b>',side(t.side),t.qty,IN(t.entry,2),t.stop==null?'':IN(t.stop,2),t.target==null?'':IN(t.target,2),
      t.status==='closed'?'<span class="num">'+esc(t.exit)+'</span> <span class="chip">'+esc(t.reason||'')+'</span>':'<span class="chip open">OPEN, now '+(t.px==null?'n/a':IN(t.px,2))+'</span>',money(t.pnl)]}),[2,3,4,5,7]);
  $('picksFor').textContent=D.picksDay?'for '+D.picksDay:'';
  $('picksBox').innerHTML=table(['#','Stock','Bias','Score','Use'],D.picks.map(function(p){
    return ['<span class="dim">'+p.rank+'</span>','<b style="font-weight:600">'+esc(p.symbol)+'</b>',side(p.bias),p.score.toFixed(2),'<span class="chip '+p.use+'">'+p.use+'</span>']}),[3]);
  $('rep').textContent=D.report;
  var beat=document.querySelector('.beat');beat.className='beat'+(D.live?'':' off');
  beatTxt();
  tabs();
}
function beatTxt(){var m=$('hb');m.className='msg'+(D.live?'':' off');m.textContent=D.live?'SYSTEM LIVE - HB: '+pad(hbAge)+'s':D.beatMsg}
function tabs(){
  $('tabs').innerHTML=D.watch.length?D.watch.map(function(s){var ch=D.chg[s];
    return '<a class="tab" role="tab" href="?s='+encodeURIComponent(s)+'&amp;p='+(S.pat?1:0)+'&amp;v=single" data-s="'+esc(s)+'" aria-selected="'+(D.view!=='grid'&&s===S.sym)+'">'+esc(s)+(ch==null?'':'<small class="'+cls(ch)+'">'+(ch>0?'+':'\u2212')+Math.abs(ch).toFixed(1)+'%</small>')+'</a>'}).join(''):'<p class="dim">No watched stocks for today yet.</p>'}

/* ---------- charts (one engine, many instances) ---------- */
var CH=[],PADL=10,PADR=68,PADT=14,PADB=30,enc=encodeURIComponent;
function Chart(host,sym,compact){
  host.innerHTML='<canvas></canvas><canvas class="ov"></canvas><div class="tip"></div>';
  var cv=host.children[0],ov=host.children[1],tip=host.children[2],ctx=cv.getContext('2d'),octx=ov.getContext('2d');
  var W=0,H=0,DPR=1,geo={X:function(){return 0},T:0,B:0,step:1,L:0,n:0},me={sym:sym,prog:1,hover:-1},raf=0,hx=null,hraf=0,rz=0;
  function chip(x,y,txt,col){
    ctx.fillStyle=col;ctx.beginPath();ctx.roundRect(x,y-8,PADR-8,16,8);ctx.fill();
    ctx.fillStyle='#ffffff';ctx.font='500 10.5px Helvetica Neue Light, Helvetica, Arial, sans-serif';ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillText(txt,x+(PADR-8)/2,y+.5)}
  me.size=function(){DPR=Math.min(window.devicePixelRatio||1,2);W=host.clientWidth;H=host.clientHeight;cv.width=W*DPR;cv.height=H*DPR;ov.width=W*DPR;ov.height=H*DPR;me.draw();me.drawOv()};
  me.drawOv=function(){octx.setTransform(DPR,0,0,DPR,0,0);octx.clearRect(0,0,W,H);
    if(me.hover>=0){var x=geo.X(me.hover);octx.strokeStyle=TH.cross;octx.lineWidth=1;octx.setLineDash([3,4]);octx.beginPath();octx.moveTo(x,geo.T);octx.lineTo(x,geo.B);octx.stroke();octx.setLineDash([])}};
  me.draw=function(){
    ctx.setTransform(DPR,0,0,DPR,0,0);ctx.clearRect(0,0,W,H);
    var b=BARS[sym];
    if(!b){ctx.fillStyle=TH.neutral;ctx.font='13px Helvetica Neue Light, Helvetica, Arial, sans-serif';ctx.textAlign='center';ctx.textBaseline='middle';
      ctx.fillText('No bars available (market closed or fetch failed).',W/2,H/2);return}
    var n=b.length,trs=D.trades.filter(function(t){return t.symbol===sym}),De=derived(sym),vw=De.vw,lo=Infinity,hi=-Infinity,i;
    b.forEach(function(x){lo=Math.min(lo,x.l);hi=Math.max(hi,x.h)});
    trs.forEach(function(t){[t.entry,t.stop,t.target].forEach(function(v){if(v!=null){lo=Math.min(lo,v);hi=Math.max(hi,v)}})});
    if(hi===lo){hi+=1;lo-=1}
    var pd=(hi-lo)*.09;lo-=pd;hi+=pd;
    var slots=n+7,L=PADL,R=W-PADR,step=(R-L)/slots,T=PADT,B=H-PADB;
    var X=function(i){return L+(i+.5)*step},Y=function(v){return T+(hi-v)/(hi-lo)*(B-T)};
    geo={X:X,Y:Y,step:step,L:L,R:R,T:T,B:B,n:n};
    var dec=hi>1000?1:2,cy=[Y(b[n-1].c)];if(vw)cy.push(Y(vw[n-1]));
    trs.forEach(function(t){[t.entry,t.stop,t.target].forEach(function(v){if(v!=null)cy.push(Y(v))})});
    ctx.font='11px Helvetica Neue Light, Helvetica, Arial, sans-serif';ctx.textBaseline='middle';
    for(var g=0;g<=(compact?4:5);g++){var v=lo+(hi-lo)*g/(compact?4:5),y=Y(v);
      ctx.strokeStyle=TH.grid;ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(L,y);ctx.lineTo(R,y);ctx.stroke();
      if(!cy.some(function(c){return Math.abs(c-y)<13})){ctx.fillStyle=TH.label;ctx.textAlign='left';ctx.fillText(IN(v,dec),R+8,y)}}
    for(i=0;i<slots;i+=(compact?9:6)){ctx.fillStyle=TH.label;ctx.textAlign='center';ctx.fillText(tstr(sym,i),X(i),H-10)}
    var shown=Math.min(n,Math.ceil(me.prog*n)),fade=Math.min(1,me.prog*1.6);
    ctx.save();ctx.globalAlpha=fade;
    if(n>=D.orBars){
      var orh=-Infinity,orl=Infinity;for(i=0;i<D.orBars;i++){orh=Math.max(orh,b[i].h);orl=Math.min(orl,b[i].l)}
      ctx.strokeStyle=TH.or;ctx.lineWidth=1;ctx.setLineDash([1.5,4]);
      [orh,orl].forEach(function(v){ctx.beginPath();ctx.moveTo(L,Y(v));ctx.lineTo(R,Y(v));ctx.stroke()});ctx.setLineDash([])}
    var chips=[];
    trs.forEach(function(t){[['Entry',t.entry,'#3b6ea5'],['Stop',t.stop,'#c4503f'],['Target',t.target,'#2f8f5b']].forEach(function(l){
      if(l[1]==null)return;
      ctx.strokeStyle=l[2];ctx.lineWidth=1.2;ctx.setLineDash([6,5]);ctx.beginPath();ctx.moveTo(L,Y(l[1]));ctx.lineTo(R,Y(l[1]));ctx.stroke();ctx.setLineDash([]);
      chips.push([Y(l[1]),IN(l[1],2),l[2]])})});
    if(vw){ctx.strokeStyle='#b8803f';ctx.lineWidth=1.6;ctx.setLineDash([7,5]);ctx.beginPath();
      for(i=0;i<shown;i++){i?ctx.lineTo(X(i),Y(vw[i])):ctx.moveTo(X(i),Y(vw[i]))}ctx.stroke();ctx.setLineDash([])}
    ctx.restore();
    var cw=Math.max(2,step*.62);
    for(i=0;i<shown;i++){var x=b[i],col=x.c>=x.o?'#2f8f5b':'#c4503f';
      ctx.strokeStyle=col;ctx.fillStyle=col;ctx.lineWidth=1.2;
      ctx.beginPath();ctx.moveTo(X(i),Y(x.h));ctx.lineTo(X(i),Y(x.l));ctx.stroke();
      ctx.fillRect(X(i)-cw/2,Y(Math.max(x.o,x.c)),cw,Math.max(1.5,Math.abs(Y(x.o)-Y(x.c))))}
    if(S.pat&&me.prog>=1){ctx.font='9px Helvetica Neue Light, Helvetica, Arial, sans-serif';ctx.textAlign='center';
      var lastLab=-9;
      De.pats.forEach(function(p){var x=b[p[0]],showLab=!compact&&p[0]-lastLab>3;if(showLab)lastLab=p[0];var c=p[2]==='bull'?'#2f8f5b':p[2]==='bear'?'#c4503f':TH.neutral,px=X(p[0]);
        ctx.fillStyle=c;ctx.beginPath();
        if(p[2]==='bull'){var y=Y(x.l)+8;ctx.moveTo(px,y-4);ctx.lineTo(px-3.5,y+2);ctx.lineTo(px+3.5,y+2);ctx.fill();if(showLab){ctx.textBaseline='top';ctx.globalAlpha=.75;ctx.fillText(p[1],px,y+5);ctx.globalAlpha=1}}
        else{var y2=Y(x.h)-8;if(p[2]==='bear'){ctx.moveTo(px,y2+4);ctx.lineTo(px-3.5,y2-2);ctx.lineTo(px+3.5,y2-2);ctx.fill()}else{ctx.arc(px,y2,2.5,0,6.3);ctx.fill()}if(showLab){ctx.textBaseline='bottom';ctx.globalAlpha=.75;ctx.fillText(p[1],px,y2-5);ctx.globalAlpha=1}}})}
    if(me.prog>=1){
      trs.forEach(function(t){if(t.bar==null||t.bar>=n)return;var tx=X(t.bar),ty=Y(t.entry),lg=t.side==='LONG';
        ctx.fillStyle='#3b6ea5';ctx.strokeStyle='#fff';ctx.lineWidth=1;ctx.beginPath();
        if(lg){ctx.moveTo(tx,ty-9);ctx.lineTo(tx-8,ty+6);ctx.lineTo(tx+8,ty+6)}else{ctx.moveTo(tx,ty+9);ctx.lineTo(tx-8,ty-6);ctx.lineTo(tx+8,ty-6)}
        ctx.closePath();ctx.fill();ctx.stroke()});
      chips.forEach(function(c){chip(R+4,c[0],c[1],c[2])});
      if(vw)chip(R+4,Y(vw[n-1]),IN(vw[n-1],2),'#b8803f');
      chip(R+4,Y(b[n-1].c),IN(b[n-1].c,2),b[n-1].c>=b[n-1].o?'#2f8f5b':'#c4503f')}
  };
  me.replay=function(ms){cancelAnimationFrame(raf);if(RM){me.prog=1;me.draw();return}me.prog=0;var t0=null;
    (function f(t){t0=t0||t;var k=Math.min((t-t0)/ms,1);me.prog=1-Math.pow(1-k,3);me.draw();if(k<1)raf=requestAnimationFrame(f);else{me.prog=1;me.draw()}})(performance.now())};
  function hoverFrame(){hraf=0;if(hx===null||!BARS[sym])return;
    var i=Math.round((hx-geo.L)/geo.step-.5);
    if(i<0||i>=geo.n||me.prog<1){me.hoverOff();return}
    if(i===me.hover)return;
    me.hover=i;var x=BARS[sym][i],pt=derived(sym).pats.filter(function(p){return p[0]===i})[0];
    tip.innerHTML='<b>'+tstr(sym,i)+'</b> IST<br>O '+IN(x.o,2)+' &nbsp;H '+IN(x.h,2)+'<br>L '+IN(x.l,2)+' &nbsp;C '+IN(x.c,2)+(x.v?'<br>Vol '+IN(x.v,0):'')+(S.pat&&pt?'<br><span style="color:#b8803f">'+pt[1]+'</span>':'');
    var tx=geo.X(i)+14;if(tx+150>W)tx=geo.X(i)-150;tip.style.transform='translate('+tx+'px,8px)';tip.style.opacity=1;me.drawOv()}
  me.hoverOff=function(){hx=null;if(me.hover!==-1){me.hover=-1;tip.style.opacity=0;me.drawOv()}};
  ov.addEventListener('mousemove',function(e){hx=e.clientX-ov.getBoundingClientRect().left;if(!hraf)hraf=requestAnimationFrame(hoverFrame)});
  ov.addEventListener('mouseleave',me.hoverOff);
  var ro=new ResizeObserver(function(){if(rz)return;rz=requestAnimationFrame(function(){rz=0;me.size()})});ro.observe(host);
  me.destroy=function(){ro.disconnect();cancelAnimationFrame(raf);cancelAnimationFrame(hraf);cancelAnimationFrame(rz)};
  return me;
}
function lastInfo(sym){var b=BARS[sym];if(!b)return null;var cl=b[b.length-1].c;return{px:cl,ch:(cl/b[0].o-1)*100}}
function chgHTML(ch){return(ch>0?'+':'\u2212')+Math.abs(ch).toFixed(2)+'%'}
function build(inPlace){
  var body=$('cbody'),P=S.pat?1:0,cs=$('chartSec');
  CH.forEach(function(c){c.destroy()});CH=[];
  $('patBtn').style.display='';$('vseg').style.display='';document.querySelector('.legend').style.display='';
  var grid=D.view==='grid'&&D.watch.length,WL=D.watch.slice(0,8);
  /* moving a node restarts its CSS entrance animation, so switch it off when moving after first paint */
  function put(before){if(cs.nextElementSibling===before)return;if(inPlace)cs.style.animation='none';before.parentNode.insertBefore(cs,before)}
  if(grid){
    var g=document.querySelector('.grid');put(g);cs.style.marginBottom='20px';
    $('symName').textContent='All watched stocks';$('symName').style.fontSize='28px';$('symPx').textContent='';$('symChg').textContent='';
    body.className='cgrid';
    body.innerHTML=WL.map(function(s,i){var inf=lastInfo(s),open=D.trades.some(function(t){return t.symbol===s&&t.status==='open'});
      return '<div class="mini"><div class="mhead"><a class="msym" data-s="'+esc(s)+'" href="?s='+enc(s)+'&amp;p='+P+'&amp;v=single">'+esc(s)+'</a>'+(inf?'<span class="num mpx">'+IN(inf.px,2)+'</span><span class="num mchg '+cls(inf.ch)+'">'+chgHTML(inf.ch)+'</span>':'')+(open?'<span class="chip open">open trade</span>':'')+'</div><div class="cw compact" id="cw'+i+'"></div></div>'}).join('');
    WL.forEach(function(s,i){CH.push(Chart($('cw'+i),s,true))});
  }else{
    put($('tradesSec'));cs.style.marginBottom='';$('symName').style.fontSize='';
    body.className='';
    if(S.sym){body.innerHTML='<div class="cw" id="cw0"></div>';CH.push(Chart($('cw0'),S.sym,false));
      var inf=lastInfo(S.sym);$('symName').textContent=S.sym;
      if(inf){$('symPx').textContent=IN(inf.px,2);$('symChg').className='chg num '+cls(inf.ch);$('symChg').textContent=chgHTML(inf.ch)}}
    else{body.innerHTML='<p class="dim">No watched stocks for today yet.</p>';$('symName').textContent='';$('patBtn').style.display='none';$('vseg').style.display='none';document.querySelector('.legend').style.display='none'}
  }
}
$('patBtn').addEventListener('click',function(){S.pat=!S.pat;this.setAttribute('aria-pressed',S.pat);this.textContent='patterns: '+(S.pat?'on':'off');
  try{history.replaceState(null,'','?s='+enc(S.sym||'')+'&p='+(S.pat?1:0)+'&v='+D.view)}catch(e){}
  tabs();viewLinks();CH.forEach(function(c){c.draw();c.hoverOff()})});

/* ---------- in-place navigation: tabs, Single / All charts and mini-chart titles swap only the chart section ---------- */
var navSeq=0,want={sym:S.sym,view:D.view};
function mark(sym,view){
  [].forEach.call(document.querySelectorAll('.tab'),function(a){a.setAttribute('aria-selected',view!=='grid'&&a.dataset.s===sym)});
  $('vSingle').setAttribute('aria-pressed',view!=='grid');$('vGrid').setAttribute('aria-pressed',view==='grid')}
function go(sym,view){
  if(view===want.view&&(view==='grid'||sym===want.sym))return;
  want={sym:sym,view:view};mark(sym,view);
  var q='?s='+enc(sym||'')+'&p='+(S.pat?1:0)+'&v='+view,my=++navSeq,body=$('cbody');
  body.classList.add('busy');
  fetch('/data'+q,{cache:'no-store'}).then(function(r){return r.json()}).then(function(nd){
    if(my!==navSeq)return;                                  // a newer click is already in flight
    D=nd;S.sym=D.sel;want={sym:S.sym,view:D.view};loadBars();
    try{history.replaceState(null,'',q)}catch(e){}
    body.classList.remove('busy');build(true);tabs();viewLinks();
    requestAnimationFrame(function(){CH.forEach(function(c){c.size();c.replay(650)})})
  }).catch(function(){location.href=q})}                    // fall back to a normal page load
function navClick(e,sym,view){
  if(e.defaultPrevented||e.button||e.metaKey||e.ctrlKey||e.shiftKey||e.altKey)return;   // let new-tab clicks through
  e.preventDefault();go(sym,view)}
$('tabs').addEventListener('click',function(e){var a=e.target.closest('.tab');if(a)navClick(e,a.dataset.s,'single')});
$('vseg').addEventListener('click',function(e){var a=e.target.closest('a');if(a)navClick(e,want.sym,a.id==='vGrid'?'grid':'single')});
$('cbody').addEventListener('click',function(e){var a=e.target.closest('a.msym');if(a)navClick(e,a.dataset.s,'single')});
function viewLinks(){var P=S.pat?1:0,s=enc(S.sym||'');
  $('vSingle').href='?s='+s+'&p='+P+'&v=single';$('vGrid').href='?s='+s+'&p='+P+'&v=grid';
  $('vSingle').setAttribute('aria-pressed',D.view!=='grid');$('vGrid').setAttribute('aria-pressed',D.view==='grid')}

/* ---------- heartbeat counter (text only) ---------- */
setInterval(function(){if(document.hidden)return;if(D.live&&hbAge!=null){hbAge++;beatTxt()}},1000);

/* ---------- theme toggle ---------- */
$('themeBtn').addEventListener('click',function(){var t=root.dataset.theme==='dark'?'light':'dark';root.dataset.theme=t;
  try{localStorage.setItem('nsetheme',t)}catch(e){}readTheme();CH.forEach(function(c){c.draw();c.drawOv()})});

/* ---------- live data: fetch JSON and update in place (no page reload, video keeps playing) ---------- */
function sig(d){return Object.keys(d.bars).join(',')+'|'+d.nOpen+'|'+d.view+'|'+d.watch.join(',')}
function headers(){
  if(D.view==='grid'){[].forEach.call(document.querySelectorAll('.mini'),function(m,i){var inf=D.watch[i]&&lastInfo(D.watch[i]);if(!inf)return;
    var p=m.querySelector('.mpx'),c=m.querySelector('.mchg');if(p)p.textContent=IN(inf.px,2);if(c){c.className='num mchg '+cls(inf.ch);c.textContent=chgHTML(inf.ch)}})}
  else if(S.sym){var inf=lastInfo(S.sym);if(inf){$('symPx').textContent=IN(inf.px,2);$('symChg').className='chg num '+cls(inf.ch);$('symChg').textContent=chgHTML(inf.ch)}}}
function refresh(){
  if(document.hidden)return;
  var q0=location.search;
  fetch('/data'+q0,{cache:'no-store'}).then(function(r){return r.json()}).then(function(nd){
    if(location.search!==q0)return;                         // view changed while this request was in flight
    var same=sig(nd)===sig(D);D=nd;hbAge=D.hbAge;loadBars();render();
    if(same){headers();CH.forEach(function(c){c.draw()})}else build()}).catch(function(){})}
setInterval(refresh,30000);
document.addEventListener('visibilitychange',function(){if(!document.hidden)refresh()});

/* ---------- boot ---------- */
$('patBtn').setAttribute('aria-pressed',S.pat);$('patBtn').textContent='patterns: '+(S.pat?'on':'off');
var rp=false;try{rp=sessionStorage.getItem('nsereplay')==='1';sessionStorage.removeItem('nsereplay')}catch(e){}
readTheme();render();booted=true;viewLinks();build();
[].forEach.call(document.querySelectorAll('.rise'),function(el,i){el.style.setProperty('--i',i)});
requestAnimationFrame(function(){CH.forEach(function(c,i){c.size();if(!SEEN)setTimeout(function(){c.replay(1300)},i*120);else if(rp)c.replay(650)})});
})();
"""

TEMPLATE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>NSE Intraday Paper Trader</title>
%%LINKS%%
<script>%%HEADJS%%</script><style>%%CSS%%</style></head><body>
<div class="bg" id="bg" aria-hidden="true"></div>
<div class="stage">
%%VIDEO%%
<div class="wrap">
  <header class="rise">
    <span class="pill" id="livePill"><span class="dot" id="pillDot"></span><span id="pillTxt"></span></span>
    <span class="spacer"></span>
    <span class="pill hide-m">updated <span id="upd" class="num"></span></span>
    <button class="pill themebtn" id="themeBtn" type="button" aria-label="Toggle dark mode"><svg class="i-moon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z"/></svg><svg class="i-sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg></button>
  </header>
  <section class="hero" aria-label="Account summary">
    <div class="rise balcard">
      <div class="eyebrow">Paper balance</div>
      <div class="big" id="bal"></div>
      <p class="herosub" id="heroSub"></p>
    </div>
    <div class="stats rise">
      <div class="stat"><div><span class="k">Today P&amp;L</span><span class="s" id="todaySub"></span></div><span class="v" id="today"></span></div>
      <div class="stat"><div><span class="k">Open positions</span><span class="s" id="openSub"></span></div><span class="v" id="open"></span></div>
      <div class="stat"><div><span class="k">Win rate &middot; today</span><span class="s" id="winSub"></span></div><span class="v" id="win"></span></div>
    </div>
  </section>
</div>
</div>
<div class="wrap main">
  <div class="grid">
    <div class="col">
      <section class="glass rise" id="chartSec" aria-label="Charts">
        <div class="chart-head">
          <div>
            <div class="sym"><span id="symName"></span><span class="px num" id="symPx"></span><span class="chg num" id="symChg"></span></div>
            <div class="meta">Live 5 min &middot; IST &middot; today</div>
          </div>
          <div class="ctl">
            <div class="seg" id="vseg"><a id="vSingle" href="?v=single" aria-pressed="true">Single</a><a id="vGrid" href="?v=grid" aria-pressed="false">All charts</a></div>
            <button class="btn" id="patBtn" aria-pressed="true">patterns: on</button>
          </div>
        </div>
        <div id="cbody"></div>
        <div class="legend">
          <span><i style="border-color:#b8803f"></i>VWAP</span>
          <span><i style="border-color:#6b7a6c;border-top-style:dotted"></i>Opening range</span>
          <span><i style="border-color:#3b6ea5"></i>Entry</span>
          <span><i style="border-color:#c4503f"></i>Stop</span>
          <span><i style="border-color:#2f8f5b"></i>Target</span>
          <span class="dim">Charts are display only. Patterns are not used by the trading rules.</span>
        </div>
      </section>
      <section class="glass rise" id="tradesSec">
        <h2>Today's trades <i id="today-date"></i></h2>
        <div id="tradesBox"></div>
      </section>
    </div>
    <div class="col">
      <section class="glass rise"><h2>Watchlist</h2><div class="tabs" id="tabs" role="tablist" aria-label="Watchlist"></div></section>
      <section class="glass rise">
        <h2>Engine</h2>
        <div class="beat">
          <div class="pulse"><i class="ringfx"></i><svg viewBox="0 0 100 100" aria-hidden="true"><circle cx="50" cy="50" r="40" fill="none" stroke="#2f8f5b" stroke-width="2" opacity=".35"/><circle cx="50" cy="50" r="30" fill="rgba(47,143,91,.12)" stroke="#2f8f5b" stroke-width="2"/><path d="M22 52h14l6-14 8 28 6-14h22" fill="none" stroke="#2f8f5b" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg></div>
          <div><div class="msg" id="hb"></div><div class="sub">Heartbeat file refreshed every 5 min. Idle after 7.</div></div>
        </div>
      </section>
      <section class="glass rise"><h2>Top picks <i id="picksFor"></i></h2><div id="picksBox"></div></section>
    </div>
  </div>
  <section class="glass full rise"><h2>Readiness</h2><pre id="rep"></pre></section>
</div>
<script>window.__D=%%DATA%%;</script>
<script>%%JS%%</script>
<script>%%VIDEOJS%%</script></body></html>"""


LINKS = r"""<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='9' fill='%230b2418'/%3E%3Cpath d='M5 18h6l3-7 4 14 3-7h6' fill='none' stroke='%234cd27a' stroke-width='2.4' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E">
<link href="https://db.onlinewebfonts.com/c/0e6de1ec911a2e267ff136bbdd384a44?family=Helvetica+Neue+Light" rel="stylesheet">"""

VIDEO = r"""  <video id="v0" autoplay muted loop playsinline preload="auto" aria-hidden="true" src="https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260820_010308_b1636845-4c15-4ab6-b0c9-9a29bfb0c6e3.mp4"></video>
  <video id="v1" muted playsinline preload="auto" aria-hidden="true" src="https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260820_010308_b1636845-4c15-4ab6-b0c9-9a29bfb0c6e3.mp4"></video>"""

VIDEO_JS = r"""/* endless-zoom background: there is no visible loop point. Shortly before the clip ends, the old picture keeps pushing
   in (zooms to Z x) while a second copy, starting from frame 0, fades in over it, then the roles swap.
   F = blend length in seconds, Z = how far the old picture keeps zooming during the blend. */
(function(){var V=[document.getElementById('v0'),document.getElementById('v1')],F=2.5,Z=1.35,cur=0,busy=false;
if(!V[0]||!V[1])return;V[0].loop=false;
function play(v){var p=v.play();if(p&&p.catch)p.catch(function(){})}
play(V[0]);
setInterval(function(){
  if(document.hidden||busy)return;
  var o=V[cur],n=V[1-cur],d=o.duration;
  if(!(d>F*3)||o.currentTime<d-F-.15)return;
  busy=true;n.currentTime=0;n.style.transition='none';n.style.opacity=0;n.style.zIndex=2;play(n);
  void n.offsetWidth;n.style.transition='opacity '+F+'s linear';n.style.opacity=1;
  o.style.transition='transform '+F+'s cubic-bezier(.45,0,.9,.6)';o.style.transform='scale('+Z+')';
  setTimeout(function(){o.pause();o.style.transition='none';o.style.transform='';o.style.opacity=0;o.style.zIndex=0;n.style.zIndex=1;cur=1-cur;busy=false},F*1000+80)
},100)})();"""

# ---------------------------------------------------------------- desktop widget (served at /widget)
WCSS = r"""
html,body{height:100%;overflow:hidden}
.wstage{position:fixed;inset:0;min-height:0;border-radius:0}
.wbody{position:relative;z-index:10;height:100%;display:flex;flex-direction:column;gap:10px;padding:12px}
.wbody .glass{padding:14px 16px;border-radius:20px}
.wtop{display:flex;align-items:center;gap:8px}
.wtop .pill{padding:6px 12px;font-size:12px;min-width:0}
.wtop .sp{flex:1}
.wtop .themebtn{padding:6px 9px}
#wPillTxt{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.wbal{display:flex;justify-content:space-between;align-items:flex-end;gap:12px}
.wbal .k{font-size:10px;letter-spacing:.2em;text-transform:uppercase;color:var(--dim);margin-bottom:8px}
.wbig{font-size:34px;line-height:1;letter-spacing:-.03em;color:var(--bignum);white-space:nowrap;font-variant-numeric:tabular-nums}
.wbig .cur{font-size:.45em;color:var(--green);margin-right:.2em;vertical-align:.45em}
.wbig .dec{color:var(--green)}
.wpl{text-align:right}
.wpl .v{font-size:22px;letter-spacing:-.02em;line-height:1;white-space:nowrap;font-variant-numeric:tabular-nums}
#wCard{flex:1;min-height:0;display:flex;flex-direction:column;transition:opacity .25s}
#wCard.out{opacity:0}
.wlist{flex:1;min-height:0;overflow:auto;margin:0 -4px;padding:0 4px;scrollbar-width:none}
.wlist::-webkit-scrollbar{display:none}
.wrow{display:grid;grid-template-columns:minmax(0,1fr) 64px 70px 58px;align-items:center;gap:8px;padding:9px 0;border-top:1px solid var(--line);font-size:13px}
.wrow:first-child,.trow:first-child{border-top:0}
.wsym{display:flex;align-items:center;gap:6px;min-width:0}
.wsym b{font-weight:600;overflow:hidden;text-overflow:ellipsis}
.od{width:6px;height:6px;border-radius:50%;background:var(--accent);flex:none}
.wpx,.wch{text-align:right}.wch{font-size:12px}
.spk{display:block}
.wtop,.wbal{cursor:grab}body{user-select:none;-webkit-user-select:none}
body:has(#wPin[aria-pressed=true]) .wtop,body:has(#wPin[aria-pressed=true]) .wbal{cursor:default}
#wPin[aria-pressed=true]{background:var(--ink);color:var(--onink)}
.trow{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:2px 12px;align-items:center;padding:10px 0;border-top:1px solid var(--line);font-size:13px}
.trow .meta{margin-top:2px}.trow .tr{text-align:right}
.rng{grid-column:1/-1;position:relative;height:4px;margin-top:6px;border-radius:2px;opacity:.85;background:linear-gradient(90deg,var(--neg),var(--edge) 50%,var(--pos))}
.rng i{position:absolute;top:-3px;width:2px;height:10px;border-radius:1px;background:var(--ink);transform:translateX(-1px)}
"""

WJS = r"""(function(){
'use strict';
var D=window.__D,mode=null,root=document.documentElement;
var $=function(id){return document.getElementById(id)};
function esc(x){return String(x).replace(/[&<>"']/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]})}
var IN=function(v,d){return Number(v).toLocaleString('en-IN',{minimumFractionDigits:d,maximumFractionDigits:d})};
function signed(v,d){return(v>0?'+':v<0?'\u2212':'')+IN(Math.abs(v),d==null?2:d)}
function cls(v){return v>0?'pos':v<0?'neg':''}
function money(v){return v==null?'<span class="dim">n/a</span>':'<span class="num '+cls(v)+'">'+signed(v)+'</span>'}
function bigHTML(v){var s=IN(v,2).split('.');return '<span class="cur">Rs</span>'+s[0]+'<span class="dec">.'+s[1]+'</span>'}
function side(s){return '<span class="tag '+(s==='LONG'?'pos':'neg')+'">'+esc(s)+'</span>'}
function spark(c,up){
  if(!c||c.length<2)return '<span></span>';
  var lo=Math.min.apply(null,c),hi=Math.max.apply(null,c),r=hi-lo||1,w=64,h=22;
  var pts=c.map(function(v,i){return(i/(c.length-1)*w).toFixed(1)+','+(h-2-(v-lo)/r*(h-4)).toFixed(1)}).join(' ');
  return '<svg class="spk" viewBox="0 0 '+w+' '+h+'" width="'+w+'" height="'+h+'"><polyline points="'+pts+'" fill="none" stroke="'+(up?'var(--pos)':'var(--neg)')+'" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"/></svg>'}

function head(){
  $('wPillTxt').textContent=D.live?'live engine running':String(D.beatMsg||'engine idle').toLowerCase();
  $('pillDot').className='dot'+(D.live?'':' off');
  $('wPill').title='updated '+D.updated;
  $('wBal').innerHTML=bigHTML(D.balance);
  $('wToday').className='v '+cls(D.total);
  $('wToday').innerHTML=D.total==null?'<span class="dim">n/a</span>':signed(D.total)}

function watchHTML(){
  if(!D.watch.length)return '<p class="dim">No watched stocks for today yet.</p>';
  return D.watch.slice(0,8).map(function(s){
    var b=D.bars[s],open=D.trades.some(function(t){return t.symbol===s&&t.status==='open'}),px=null,ch=null;
    if(b&&b.c.length){px=b.c[b.c.length-1];ch=(px/b.o[0]-1)*100}
    return '<div class="wrow"><div class="wsym"><b>'+esc(s)+'</b>'+(open?'<i class="od" title="open trade"></i>':'')+'</div>'+
      (b?spark(b.c,ch>=0):'<span></span>')+
      '<div class="wpx num">'+(px==null?'<span class="dim">n/a</span>':IN(px,2))+'</div>'+
      '<div class="wch num '+cls(ch)+'">'+(ch==null?'':(ch>0?'+':'\u2212')+Math.abs(ch).toFixed(2)+'%')+'</div></div>'}).join('')}

function liveHTML(){
  var ts=D.trades.slice().sort(function(a,b){return(a.status==='open'?0:1)-(b.status==='open'?0:1)});
  return ts.map(function(t){
    var open=t.status==='open',bar='';
    if(open&&t.px!=null&&t.stop!=null&&t.target!=null&&t.target!==t.stop){      // where the price sits between stop and target
      var k=Math.max(0,Math.min(1,(t.px-t.stop)/(t.target-t.stop)));bar='<div class="rng"><i style="left:'+(k*100).toFixed(1)+'%"></i></div>'}
    return '<div class="trow"><div><b>'+esc(t.symbol)+'</b> '+side(t.side)+'<div class="meta num">'+t.qty+' @ '+IN(t.entry,2)+'</div></div>'+
      '<div class="tr"><div class="num">'+(open?(t.px==null?'<span class="dim">n/a</span>':IN(t.px,2)):'<span class="chip">'+esc(t.reason||'closed')+'</span>')+'</div><div>'+money(t.pnl)+'</div></div>'+bar+'</div>'}).join('')}

function fill(m){
  var box=$('wCard'),old=box.querySelector('.wlist'),top=old?old.scrollTop:0,live=m==='live';
  var note=live?D.nOpen+' open':(D.live?'live \u00b7 waiting for entries':D.today);
  box.innerHTML='<h2>'+(live?'Live trades':'Watchlist')+'<i>'+esc(note)+'</i></h2><div class="wlist">'+(live?liveHTML():watchHTML())+'</div>';
  box.querySelector('.wlist').scrollTop=top}

/* live engine running AND trades exist -> live trades; otherwise the watchlist. Fades when it switches. */
function draw(){
  head();
  var m=D.live&&D.trades.length?'live':'watch',box=$('wCard');
  if(mode!==null&&m!==mode){box.classList.add('out');setTimeout(function(){fill(m);box.classList.remove('out')},260)}
  else fill(m);
  mode=m}

function refresh(){
  if(document.hidden)return;
  fetch('/data?v=grid',{cache:'no-store'}).then(function(r){return r.json()}).then(function(nd){D=nd;draw()})
    .catch(function(){$('pillDot').className='dot off';$('wPillTxt').textContent='dashboard offline';if(!D)setTimeout(refresh,3000)})}
setInterval(refresh,20000);
document.addEventListener('visibilitychange',function(){if(!document.hidden)refresh()});

$('themeBtn').addEventListener('click',function(){var t=root.dataset.theme==='dark'?'light':'dark';root.dataset.theme=t;try{localStorage.setItem('nsetheme',t)}catch(e){}});
/* drag to move: mouse travel is sent to Python, which moves the window (only inside the pywebview window) */
var drag=null,pend=null,busy=false;
function pump(){if(busy||!pend)return;var p=pend;pend=null;busy=true;
  pywebview.api.drag_to(p[0],p[1]).then(function(){busy=false;pump()},function(){busy=false})}
document.addEventListener('mousedown',function(e){
  if($('wPin').getAttribute('aria-pressed')==='true')return;   // pinned = locked in place
  if(e.button||e.target.closest('button,.wlist')||!(window.pywebview&&pywebview.api&&pywebview.api.drag_start))return;
  var d=drag={sx:e.screenX,sy:e.screenY,ready:false};pend=null;
  pywebview.api.drag_start().then(function(){d.ready=true});e.preventDefault()});
document.addEventListener('mousemove',function(e){
  if(!drag||!drag.ready)return;var k=window.devicePixelRatio||1;pend=[(e.screenX-drag.sx)*k,(e.screenY-drag.sy)*k];pump()});
document.addEventListener('mouseup',function(){drag=null});
/* pin button: on = sits behind all other windows and is locked, off = floats on top and can be dragged */
window.addEventListener('pywebviewready',function(){$('wPin').style.display='';pywebview.api.apply_pin()});
window.addEventListener('focus',function(){if($('wPin').getAttribute('aria-pressed')==='true'&&window.pywebview&&pywebview.api&&pywebview.api.apply_pin)pywebview.api.apply_pin()});
$('wPin').addEventListener('click',function(){var b=this;
  if(window.pywebview&&pywebview.api&&pywebview.api.toggle_top)pywebview.api.toggle_top().then(function(on){b.setAttribute('aria-pressed',!!on);b.title=on?'Pinned to the bottom (locked). Click to float and move':'Floating on top. Click to pin to the bottom'})});
$('wClose').addEventListener('click',function(){if(window.pywebview&&pywebview.api&&pywebview.api.close)pywebview.api.close();else window.close()});
if(D)draw();else{$('wPillTxt').textContent='loading\u2026';$('wCard').innerHTML='<p class="dim">Loading prices\u2026</p>';refresh()}
})();
"""

WIDGET = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>NSE Widget</title>
%%LINKS%%
<script>%%HEADJS%%</script><style>%%CSS%%</style></head><body>
<div class="stage wstage">
%%VIDEO%%
  <div class="wbody">
    <div class="wtop">
      <span class="pill" id="wPill"><span class="dot" id="pillDot"></span><span id="wPillTxt"></span></span>
      <span class="sp"></span>
      <button class="pill themebtn" id="themeBtn" type="button" aria-label="Toggle dark mode"><svg class="i-moon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z"/></svg><svg class="i-sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg></button>
      <button class="pill themebtn" id="wPin" type="button" aria-pressed="true" aria-label="Pin widget to the bottom" title="Pinned to the bottom (locked). Click to float and move" style="display:none"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 17v5M9 3h6l-1 6 3 4H7l3-4-1-6Z"/></svg></button>
      <button class="pill themebtn" id="wClose" type="button" aria-label="Close widget"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg></button>
    </div>
    <section class="glass wbal">
      <div><div class="k">Paper balance</div><div class="wbig" id="wBal"></div></div>
      <div class="wpl"><div class="k">Today P&amp;L</div><div class="v" id="wToday"></div></div>
    </section>
    <section class="glass" id="wCard"></section>
  </div>
</div>
<script>window.__D=%%DATA%%;</script>
<script>%%WJS%%</script>
<script>%%VIDEOJS%%</script></body></html>"""

# ---------------------------------------------------------------- data for the page
def r2(series):
    return [round(float(v), 2) for v in series]


def _naive_index(df):
    return df.index.tz_localize(None) if df.index.tz is not None else df.index


def bars_payload(df):
    """Columns the browser needs to draw the chart. None if there are no bars."""
    if df is None:
        return None
    idx = _naive_index(df)
    vol = df.volume if "volume" in df else [0] * len(df)
    return {"t": [x.strftime("%H:%M") for x in idx], "o": r2(df.open), "h": r2(df.high), "l": r2(df.low),
            "c": r2(df.close), "v": [int(v) if v == v else 0 for v in vol]}


def bar_index(df, ts):
    """Index of the bar nearest to a trade's entry_time, or None."""
    try:
        t = pd.Timestamp(ts)
        t = t.tz_localize(None) if t.tzinfo else t
        pos = int(_naive_index(df).get_indexer([t], method="nearest")[0])
        return pos if pos >= 0 else None
    except Exception:
        return None


def payload(cfg, qs=None):
    qs = qs or {}
    c = db.connect()
    today = str(date.today())
    realized_all, funds = db.realized(c), db.funds(c)
    day = sorted(db.day_trades(c, today), key=lambda x: x["entry_time"])
    n = cfg["picks_per_night"]

    # stocks to chart: today's traded symbols first, then today's watched picks
    watch = []
    for t in day:
        if t["symbol"] not in watch:
            watch.append(t["symbol"])
    for r in c.execute("SELECT symbol FROM picks WHERE day=? ORDER BY rank LIMIT ?", (today, n)).fetchall():
        if r["symbol"] not in watch:
            watch.append(r["symbol"])
    sel = qs.get("s", [None])[0]
    sel = sel if sel in watch else (watch[0] if watch else None)
    show_pat = qs.get("p", ["1"])[0] != "0"
    grid = qs.get("v", ["single"])[0] == "grid"
    chart_syms = (watch[:8] if grid else [sel]) if watch else []      # grid view charts every watched stock (max 8)
    dfs = fetch_all_bars(chart_syms)

    trades, realized_today, unreal, unreal_ok, n_open, wins, n_closed = [], 0.0, 0.0, True, 0, 0, 0
    for t in day:
        row = {"symbol": t["symbol"], "side": t["side"], "qty": t["qty"], "entry": t["entry_price"],
               "stop": t["stop"], "target": t["target"], "status": t["status"], "bar": None}
        if dfs.get(t["symbol"]) is not None:
            row["bar"] = bar_index(dfs[t["symbol"]], t["entry_time"])
        if t["status"] == "closed":
            net = t["net"] or 0
            realized_today += net
            n_closed += 1
            wins += net > 0
            row.update(exit=t["exit_price"], reason=t["exit_reason"], pnl=t["net"])
        else:
            n_open += 1
            px = last_price(t["symbol"])
            u = None if px is None else (1 if t["side"] == "LONG" else -1) * (px - t["entry_price"]) * t["qty"]
            unreal_ok &= u is not None
            unreal += u or 0
            row.update(px=px, pnl=u)
        trades.append(row)

    hb = "data/heartbeat.txt"
    age = time.time() - os.path.getmtime(hb) if os.path.exists(hb) else None
    live_on = age is not None and age < 420
    if live_on:
        pill, beat_msg = "live engine running", ""
    elif age is not None:
        pill = f"live engine idle (last run {datetime.fromtimestamp(os.path.getmtime(hb)):%d %b %H:%M})"
        beat_msg = "ENGINE IDLE"
    else:
        pill, beat_msg = "live engine has not run yet", "ENGINE NOT RUN YET"

    nxt = c.execute("SELECT MAX(day) FROM picks").fetchone()[0]
    picks = c.execute("SELECT symbol, rank, score, bias FROM picks WHERE day=? ORDER BY rank", (nxt,)).fetchall() if nxt else []
    rep = report.render(report.stats(db.closed_trades(c, cfg["rule_version"]), cfg), cfg)

    chg = {}                                    # day change for tabs, only where bars are already cached (no extra fetches)
    for s in watch:
        hit = _bars.get(s)
        if hit and hit[1] is not None and len(hit[1]):
            chg[s] = round((float(hit[1].close.iloc[-1]) / float(hit[1].open.iloc[0]) - 1) * 100, 2)

    total = realized_today + unreal
    return {
        "capital": cfg["capital"], "funds": funds, "realizedAll": realized_all,
        "balance": cfg["capital"] + funds + realized_all,
        "today": today, "rule": str(cfg["rule_version"]), "updated": f"{datetime.now():%d %b %H:%M:%S}",
        "live": live_on, "pill": pill, "beatMsg": beat_msg, "hbAge": int(age) if live_on else None,
        "realizedToday": realized_today, "unreal": unreal if unreal_ok else None, "total": total if unreal_ok else None,
        "nOpen": n_open, "nClosed": n_closed, "wins": int(wins), "trades": trades,
        "watch": watch, "sel": sel, "showPat": show_pat, "chg": chg, "orBars": int(cfg.get("or_bars", 3)),
        "view": "grid" if grid else "single", "bars": {s: bars_payload(df) for s, df in dfs.items()},
        "picksDay": str(nxt) if nxt else "",
        "picks": [{"rank": p["rank"], "symbol": p["symbol"], "bias": "LONG" if p["bias"] > 0 else "SHORT",
                   "score": float(p["score"]), "use": "watching" if p["rank"] <= n else "extra"} for p in picks],
        "report": rep, "photo": False,
    }


def page(cfg, qs=None):
    blob = json.dumps(payload(cfg, qs), default=str).replace("</", "<\\/").replace("<!--", "<\\!--")
    return (TEMPLATE.replace("%%HEADJS%%", HEAD_JS).replace("%%CSS%%", CSS).replace("%%LINKS%%", LINKS)
            .replace("%%VIDEO%%", VIDEO).replace("%%VIDEOJS%%", VIDEO_JS).replace("%%JS%%", JS).replace("%%DATA%%", blob))


def make_server(cfg, port=8765):
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            t0 = time.time()
            u = urlparse(self.path)
            if u.path == "/data":                                       # JSON for in-place updates
                body, ctype = json.dumps(payload(cfg, parse_qs(u.query)), default=str).encode(), "application/json"
            elif u.path == "/widget":                                   # compact desktop-widget page
                body, ctype = widget_page(cfg).encode(), "text/html; charset=utf-8"
            else:
                body, ctype = page(cfg, parse_qs(u.query)).encode(), "text/html; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            if time.time() - t0 > 3:
                print(f"slow request {u.path}: {time.time() - t0:.1f}s (Yahoo fetch)", flush=True)

        def log_message(self, *a):
            pass

    return ThreadingHTTPServer(("127.0.0.1", port), H)


def serve(cfg, port=8765):
    try:
        srv = make_server(cfg, port)
    except OSError:                                              # port taken: the widget (or another dash) is already serving it
        import webbrowser
        print(f"Dashboard is already running: http://127.0.0.1:{port}")
        webbrowser.open(f"http://127.0.0.1:{port}")
        return
    print(f"Dashboard: http://127.0.0.1:{port}   (Ctrl+C to stop)")
    import webbrowser
    webbrowser.open(f"http://127.0.0.1:{port}")
    srv.serve_forever()


def widget_page(cfg):
    blob = "null"                                                  # data is fetched by the page, so the window opens instantly
    return (WIDGET.replace("%%HEADJS%%", HEAD_JS).replace("%%CSS%%", CSS + WCSS).replace("%%LINKS%%", LINKS)
            .replace("%%VIDEO%%", VIDEO).replace("%%VIDEOJS%%", VIDEO_JS).replace("%%WJS%%", WJS).replace("%%DATA%%", blob))


class _WidgetApi:
    """Exposed to the page as pywebview.api. The window is frameless, so close, pin and drag are done here with plain
    Win32 calls (pywebview's own setters/easy_drag misbehave when called from the page's worker thread).
    Names starting with _ are not exposed to the page."""
    _top = True                                                  # pinned (bottom of the stack + locked); starts pinned
    _org = (0, 0)                                                # window position when a drag started

    def _win(self):
        import ctypes
        from ctypes import wintypes
        u = ctypes.windll.user32
        u.FindWindowW.restype = wintypes.HWND
        u.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        u.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
        return u, u.FindWindowW(None, "NSE Widget"), wintypes

    def close(self):
        import webview
        for w in list(webview.windows):
            w.destroy()

    def _apply(self):
        """Pinned = sits behind every other window (bottom of the stack) and cannot be moved.
        Unpinned = floats on top of other apps and can be dragged."""
        u, hwnd, wt = self._win()
        if hwnd:
            # HWND_BOTTOM = 1, HWND_TOPMOST = -1; flags = SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE
            u.SetWindowPos(hwnd, wt.HWND(1 if self._top else -1), 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)
        return self._top

    def toggle_top(self):                                        # _top now means "pinned"
        self._top = not self._top
        return self._apply()

    _hid = False

    def _hide_from_taskbar(self):                                # tool-window style: no taskbar button, no Alt+Tab entry
        u, hwnd, wt = self._win()
        if hwnd and not self._hid:
            self._hid = True
            u.GetWindowLongW.argtypes = [wt.HWND, __import__("ctypes").c_int]
            u.SetWindowLongW.argtypes = [wt.HWND, __import__("ctypes").c_int, __import__("ctypes").c_long]
            st = u.GetWindowLongW(hwnd, -20)                     # GWL_EXSTYLE
            u.SetWindowLongW(hwnd, -20, (st | 0x80) & ~0x40000)  # + WS_EX_TOOLWINDOW, - WS_EX_APPWINDOW
            u.ShowWindow(hwnd, 0)                                # hide + show so Windows re-reads the style
            u.ShowWindow(hwnd, 8)                                # SW_SHOWNA: show without stealing focus

    def apply_pin(self):                                         # re-sink to the bottom (on start and on focus)
        self._hide_from_taskbar()
        return self._apply()

    def drag_start(self):
        if self._top:                                            # pinned: no moving
            return False
        import ctypes
        u, hwnd, wt = self._win()
        r = wt.RECT()
        if hwnd and u.GetWindowRect(hwnd, ctypes.byref(r)):
            self._org = (r.left, r.top)
        return True

    def drag_to(self, dx, dy):                                   # dx, dy = mouse travel since drag_start, in screen pixels
        if self._top:                                            # pinned: no moving
            return False
        u, hwnd, wt = self._win()
        if hwnd:                                                 # SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE
            u.SetWindowPos(hwnd, wt.HWND(0), int(self._org[0] + dx), int(self._org[1] + dy), 0, 0, 0x0001 | 0x0004 | 0x0010)
        return True


def widget(cfg, port=8765, width=380, height=620):
    """Desktop widget: frameless, always-on-top window showing /widget (same theme + video as the dashboard).
    Run: python main.py widget   (needs: pip install pywebview; without it, falls back to an Edge app window)."""
    import threading
    srv = make_server(cfg, 0)                                     # own server on a free port, so it never clashes with `dash` (8765) or a stale process
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{port}/widget"
    try:
        import webview
    except ImportError:
        import shutil
        import subprocess
        import webbrowser
        edge = next((p for p in (shutil.which("msedge"), r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                                 r"C:\Program Files\Microsoft\Edge\Application\msedge.exe") if p and os.path.exists(p)), None)
        if edge:
            subprocess.Popen([edge, f"--app={url}", f"--window-size={width},{height}"])
        else:
            webbrowser.open(url)
        print("Widget opened in a normal window. For a frameless, always-on-top widget: pip install pywebview")
        while True:                                              # keep the server thread alive
            time.sleep(3600)
        return
    webview.create_window("NSE Widget", url, width=width, height=height, frameless=True, easy_drag=False, on_top=False,
                          resizable=False, js_api=_WidgetApi(), background_color="#0d1710")
    webview.start(private_mode=False)                            # private_mode off so the theme choice is remembered
