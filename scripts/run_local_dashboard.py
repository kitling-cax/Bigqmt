"""Serve the read-only BigQMT dashboard on loopback only.

This candidate has no order, cancel, Redis, or QMT RPC endpoints.  It is safe
to run while QMT is unavailable and is intended to be opened by BigQMT Tray.
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from kitling_bigqmt.dashboard_status import build_dashboard_status  # noqa: E402


def dashboard_build_id(source: Path | None = None) -> str:
    """Identify the code revision this process is serving.

    A dashboard restarted by hand while an older process still held the port used
    to silently serve stale HTML; the build id makes that visible in the response
    headers instead of only in a browser.
    """
    stat = (source or Path(__file__)).stat()
    return "%x-%x" % (int(stat.st_mtime), stat.st_size)


def dashboard_already_listening(port: int, timeout: float = 0.4) -> bool:
    """True when something already accepts connections on the loopback port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(timeout)
        return probe.connect_ex(("127.0.0.1", port)) == 0


BUILD_ID = dashboard_build_id()


HTML = """<!doctype html><html lang='zh-CN'><meta charset='utf-8'><title>BigQMT 控制台</title>
<style>*{box-sizing:border-box}body{margin:0;background:#0b1020;color:#e9eef9;font:14px 'Segoe UI',system-ui,sans-serif}.top{height:64px;padding:0 30px;display:flex;align-items:center;justify-content:space-between;background:#101a30;border-bottom:1px solid #263553}.brand{font-size:20px;font-weight:700}.sub{color:#91a4c6;margin-left:10px;font-size:12px}.badge{border:1px solid #536987;border-radius:99px;padding:6px 10px;font-size:12px}.lock{color:#ffc979;border-color:#7a6032}.layout{display:grid;grid-template-columns:210px 1fr;min-height:calc(100vh - 64px)}aside{background:#0e1729;padding:22px 14px;border-right:1px solid #263553}.nav{padding:11px 14px;color:#a6b7d4;border-radius:7px;margin-bottom:4px}.nav.on{background:#24375c;color:#fff}.nav.locked{margin-top:18px;color:#ffbd6b;background:#2f261a}main{padding:26px;max-width:1500px}.title{display:flex;align-items:baseline;gap:12px}.title h1{font-size:24px;margin:0}.muted{color:#91a4c6}.grid{display:grid;grid-template-columns:repeat(4,minmax(155px,1fr));gap:14px;margin:20px 0}.card{background:#131f36;border:1px solid #2a3b5b;border-radius:10px;padding:16px}.label{color:#92a6c7;font-size:12px}.value{font-size:22px;margin-top:8px;font-weight:650}.ok{color:#67d7a4}.warn{color:#ffcb75}.bad{color:#ff8794}.row{display:grid;grid-template-columns:1.3fr 1fr;gap:14px;margin-top:14px}h2{font-size:15px;margin:0 0 14px}.notice{line-height:1.6;color:#ffd083;background:#282419;border:1px solid #695730;border-radius:8px;padding:12px}.table{width:100%;border-collapse:collapse}.table td,.table th{padding:9px 4px;border-bottom:1px solid #273854;text-align:left}.table th{font-size:12px;color:#94a8c9;font-weight:500}.empty{height:178px;display:grid;place-items:center;color:#7185a7;border:1px dashed #344767;border-radius:7px}.tiny{font-size:12px}.foot{margin-top:18px;color:#7084a7;font-size:12px}@media(max-width:900px){.layout{grid-template-columns:1fr}aside{display:none}.grid{grid-template-columns:repeat(2,1fr)}.row{grid-template-columns:1fr}}</style>
<div class='top'><div><span class='brand'>BigQMT 控制台</span><span class='sub'>__DASHBOARD_SUBTITLE__</span></div><div><span class='badge'>本机只读 Dashboard</span> <span class='badge lock'>🔒 订单锁定</span></div></div>
<div class='layout'><aside><div class='nav on' data-route='overview'>运行总览</div><div class='nav' data-route='strategies'>策略账户</div><div class='nav' data-route='account'>账户与持仓</div><div class='nav' data-route='orders'>委托与成交</div><div class='nav' data-route='market'>行情健康度</div><div class='nav' data-route='audit'>审计与日志</div><div class='nav locked'>订单执行已锁定</div></aside><main><div class='title'><h1>运行总览</h1><span id='time' class='muted tiny'></span></div><div id='app'>读取本机状态…</div></main></div>
<script>const n=x=>x==null?'—':Number(x).toLocaleString('zh-CN',{maximumFractionDigits:2});const esc=x=>String(x??'—').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));function render(s){let x=s.snapshot||{},q=s.quote_summary||{},p=Object.entries(x.positions||{}),b=s.active_blockers||[],t=s.recent_tests||[];let fresh=q.states?.FRESH||0,stale=q.states?.STALE||0;document.querySelector('#time').textContent='自动刷新 · '+new Date().toLocaleTimeString();document.querySelector('#app').innerHTML=`<div class='grid'><div class='card'><div class='label'>运行环境</div><div class='value'>${esc(s.environment)}</div><div class='muted tiny'>${esc(s.stage)}</div></div><div class='card'><div class='label'>QMT Bridge</div><div class='value ${String(s.bridge).includes('RUNNING')?'ok':'bad'}'>${esc(s.bridge)}</div><div class='muted tiny'>账户 ${esc(s.account?.display_id)}</div></div><div class='card'><div class='label'>账户总资产</div><div class='value'>¥ ${n(x.total_asset)}</div><div class='muted tiny'>可用资金 ¥ ${n(x.cash)}</div></div><div class='card'><div class='label'>订单安全状态</div><div class='value warn'>LOCKED</div><div class='muted tiny'>不暴露下单/撤单入口</div></div></div><div class='row'><section class='card'><h2>账户持仓（QMT 只读快照）</h2><table class='table'><tr><th>证券</th><th>数量</th><th>可用</th><th>市值</th></tr>${p.slice(0,8).map(([c,v])=>`<tr><td>${esc(c)}</td><td>${n(v.volume)}</td><td>${n(v.available)}</td><td>¥ ${n(v.market_value)}</td></tr>`).join('')||'<tr><td colspan=4 class=muted>暂无快照</td></tr>'}</table><div class='foot'>策略归属尚未建立；现有券商持仓保持外部基线，不自动归属策略。</div></section><section class='card'><h2>运行链路</h2><table class='table'><tr><th>组件</th><th>状态</th></tr><tr><td>BigQMT Tray</td><td class='warn'>候选 / 未部署</td></tr><tr><td>Redis Bus</td><td class='muted'>由运行预检确认</td></tr><tr><td>QMT Bridge</td><td>${esc(s.bridge)}</td></tr><tr><td>行情门禁</td><td class='${stale?'warn':'ok'}'>新鲜 ${fresh} / 陈旧 ${stale}</td></tr></table><h2 style='margin-top:18px'>下一门禁</h2><div class='notice'>${esc(s.next_gate)}</div></section></div><div class='row'><section class='card'><h2>策略袖套与收益</h2><div class='empty'>v1.1.15 策略袖套、净值曲线和多策略归属将在<br>P08/P09 的可归属真实成交后显示</div></section><section class='card'><h2>活动阻塞与最近验证</h2><table class='table'>${b.map(i=>`<tr><td class='warn'>${esc(i.id)}</td><td class='tiny'>${esc(i.description)}</td></tr>`).join('')||'<tr><td class=ok>无活动阻塞</td></tr>'}</table><div class='foot'>最近：${t.map(i=>esc(i.name)+' · '+esc(i.status)).join(' ｜ ')}</div></section></div>`}async function load(){try{render(await fetch('/api/status',{cache:'no-store'}).then(r=>r.json()))}catch(e){document.querySelector('#app').textContent='无法读取本机状态：'+e}}load();setInterval(load,5000)</script>"""


HTML += """<script>
async function loadSleeves(){try{
  const status=await fetch('/api/status',{cache:'no-store'}).then(r=>r.json());
  const card=[...document.querySelectorAll('section.card')].find(e=>e.querySelector('h2')?.textContent==='策略袖套与收益');
  if(!card)return;
  const rows=(status.strategy_sleeves||[]).map(v=>{const s=v.summary||{};const pts=(v.nav_series||[]).length;return `<tr><td>${esc(s.strategy_id)}</td><td>¥ ${n(s.initial_capital)}</td><td>¥ ${n(s.net_asset_value)}</td><td>${n((Number(s.return_rate||0))*100)}%</td><td>${n(pts)}</td></tr>`}).join('');
  card.innerHTML=`<h2>策略袖套与收益</h2><table class='table'><tr><th>策略</th><th>初始资金</th><th>NAV</th><th>收益率</th><th>NAV点数</th></tr>${rows||'<tr><td colspan=5 class=muted>暂无策略袖套</td></tr>'}</table><div class='foot'>策略归属与收益来自本地 SQLite WAL；订单入口保持锁定。</div>`;
}catch(_){}}
loadSleeves();setInterval(loadSleeves,15000);
</script>"""

HTML += """<style>
body.light-dashboard{background:#f5f7fb;color:#172033;font-family:"Segoe UI","Microsoft YaHei",system-ui,sans-serif}
body.light-dashboard .top{background:#fff;color:#172033;border-bottom:1px solid #e6eaf0;box-shadow:0 1px 8px rgba(31,45,61,.05)}
body.light-dashboard .brand{color:#172033}.light-dashboard .sub{color:#718096}
body.light-dashboard .badge{background:#f8fafc;color:#526174;border-color:#d7dee8}
body.light-dashboard .badge.lock{background:#fff7e6;color:#9a6500;border-color:#f0d18d}
body.light-dashboard aside{background:#fff;border-right:1px solid #e6eaf0}
body.light-dashboard .nav{color:#64748b}.light-dashboard .nav.on{background:#e9f2ff;color:#1455a0}.light-dashboard .nav.locked{background:#fff7e6;color:#9a6500}
body.light-dashboard main{max-width:1500px;background:#f5f7fb}.light-dashboard .title h1{color:#172033}
body.light-dashboard .muted,.light-dashboard .tiny{color:#718096}
body.light-dashboard .card{background:#fff;border:1px solid #e3e8ef;border-radius:12px;box-shadow:0 2px 9px rgba(31,45,61,.045)}
body.light-dashboard .label{color:#718096}.light-dashboard .value{color:#172033}.light-dashboard .ok{color:#16845b}.light-dashboard .warn{color:#a66a00}.light-dashboard .bad{color:#b42318}
body.light-dashboard .table td,.light-dashboard .table th{border-bottom-color:#edf0f4;color:#334155}.light-dashboard .table th{color:#718096}
body.light-dashboard .notice{background:#fff8e8;border-color:#f1d99e;color:#8a5b00}
body.light-dashboard .empty{border-color:#d9e1eb;color:#718096}.light-dashboard .foot{color:#718096}
.light-dashboard .light-status{display:inline-flex;align-items:center;gap:7px;padding:5px 9px;border-radius:999px;font-size:12px;font-weight:600;background:#ecfdf3;color:#147a50}
.light-dashboard .light-status.wait{background:#fff8e8;color:#966000}.light-dashboard .light-status.lock{background:#fff1f2;color:#a61b29}
.light-dashboard .light-metrics{display:grid;grid-template-columns:repeat(4,minmax(170px,1fr));gap:14px;margin:20px 0}
.light-dashboard .light-metric{padding:17px 18px;background:#fff;border:1px solid #e3e8ef;border-radius:12px;box-shadow:0 2px 9px rgba(31,45,61,.045)}
.light-dashboard .light-metric .k{font-size:12px;color:#718096}.light-dashboard .light-metric .v{margin-top:8px;font-size:22px;font-weight:600;color:#172033}.light-dashboard .light-metric .s{margin-top:5px;font-size:12px;color:#718096}
.light-dashboard .light-grid{display:grid;grid-template-columns:1.25fr 1fr;gap:14px;margin-top:14px;min-width:0}.light-dashboard .light-section{padding:18px;min-width:0;max-width:100%;scroll-margin-top:20px}.light-dashboard .light-section h2{color:#172033;margin-bottom:14px}
.light-dashboard .light-table-wrap{min-width:0;max-width:100%;overflow-x:auto}.light-dashboard .light-empty{padding:24px 0;color:#718096;text-align:center}
.light-dashboard .nav-button{display:block;width:100%;border:0;font:inherit;text-align:left;cursor:pointer}.light-dashboard .nav-button:focus-visible{outline:2px solid #4f8bd6;outline-offset:2px}
@media(max-width:900px){.light-dashboard .layout{grid-template-columns:minmax(0,1fr)}.light-dashboard main{min-width:0;width:100%}.light-dashboard .light-metrics{grid-template-columns:repeat(2,minmax(150px,1fr))}.light-dashboard .light-grid{grid-template-columns:minmax(0,1fr)}}
@media(max-width:520px){.light-dashboard .light-metrics{grid-template-columns:minmax(0,1fr)}.light-dashboard main{padding:18px;min-width:0}.light-dashboard .light-section{padding:14px}}
</style>"""

HTML += """<script>
document.body.classList.add('light-dashboard');
const lightText={simulation:'模拟盘',production:'正式盘',RUNNING_READ_ONLY_AFTER_HOURS:'运行中 · 非交易时段',RUNNING_READ_ONLY_PRECHECK_PASSED:'运行中 · 预检通过',RUNNING_READ_ONLY:'运行中 · 只读',LOCKED:'已锁定',P12_SIMULATION_ACCEPTANCE:'模拟验收'};
const lightBlocker={SIMULATION_QMT_AFTER_HOURS_QUOTE_FRESHNESS:'当前非交易时段，行情将在下一个交易时段刷新；订单能力保持锁定。'};
function lightLabel(v){return lightText[String(v)]||String(v??'—')}
function lightBlock(item){return lightBlocker[item.id]||String(item.description||'需要进一步检查。')}
function renderLight(s){
  const x=s.snapshot||{}, q=s.quote_summary||{}, p=Object.entries(x.positions||{}), sleeves=s.strategy_sleeves||[], blockers=s.active_blockers||[], lake=s.lake_cycle||{}, raw=s.bigqmt_raw_release||{}, research=s.bigqmt_research_pit_release||{}, ops=s.ops_alerts||{}, formalRecovery=s.formal_strategy_recovery||{};
  const fresh=q.states?.FRESH||0, stale=q.states?.STALE||0;
  const bridge=lightLabel(s.bridge), stage=lightLabel(s.stage), lock=s.orders_enabled?'异常：订单开关已打开':'已锁定', captured=x.captured_at||'未采集', captureRun=x.run_id||'—';
  document.querySelector('#time').textContent='自动刷新 · '+new Date().toLocaleTimeString();
  document.querySelector('#app').innerHTML=`
  <div class='light-metrics'>
    <div class='light-metric'><div class='k'>运行环境</div><div class='v'>${esc(lightLabel(s.environment))}</div><div class='s'>${esc(stage)}</div></div>
    <div class='light-metric'><div class='k'>QMT 状态</div><div class='v'><span class='light-status ${String(s.bridge).includes('AFTER_HOURS')?'wait':''}'>${esc(bridge)}</span></div><div class='s'>账户 ${esc(s.account?.display_id)}</div></div>
    <div class='light-metric'><div class='k'>账户总资产</div><div class='v'>¥ ${n(x.total_asset)}</div><div class='s'>可用资金 ¥ ${n(x.cash)}</div></div>
    <div class='light-metric'><div class='k'>交易安全</div><div class='v'><span class='light-status ${s.orders_enabled?'lock':''}'>${esc(lock)}</span></div><div class='s'>${s.order_actions_exposed?'请立即检查配置':'不提供下单/撤单入口'}</div></div>
    ${s.profile==='production_readonly'?`<div class='light-metric'><div class='k'>正式策略恢复</div><div class='v'><span class='light-status ${formalRecovery.recovery_intent_enabled?'wait':''}'>${esc(formalRecovery.status||'NOT_AUTHORIZED')}</span></div><div class='s'>已准入策略 ${n(formalRecovery.admitted_strategy_count||0)} · 订单仍锁定</div></div>`:''}
    <div class='light-metric'><div class='k'>数据快照</div><div class='v'><span class='light-status'>${esc(x.capture_status||'未采集')}</span></div><div class='s'>${esc(captured)} · ${esc(captureRun).slice(0,12)}</div></div>
    <div class='light-metric'><div class='k'>数据湖周期</div><div class='v'><span class='light-status ${lake.status==='PASSED'?'':'wait'}'>${esc(lake.status||'未运行')}</span></div><div class='s'>运行 ${n(lake.run_count||0)} · 待清理 ${n(lake.candidate_count||0)}</div></div>
    <div class='light-metric'><div class='k'>BigQMT Raw 入库</div><div class='v'><span class='light-status ${raw.status==='PUBLISHED_ISOLATED_RAW_VERIFIED'?'':'wait'}'>${esc(raw.status||'未发布')}</span></div><div class='s'>日线 ${n(raw.daily_rows)} · 分钟 ${n(raw.intraday_rows)} · PIT ${esc(raw.pit_status||'—')}</div></div>
    <div class='light-metric'><div class='k'>ETF 研究 PIT</div><div class='v'><span class='light-status ${research.status==='PUBLISHED_ISOLATED_RESEARCH_PIT'?'':'wait'}'>${esc(research.status||'未发布')}</span></div><div class='s'>U25 · ${n(research.codes)} 标的 · ${n(research.rows)} 行 · 非全局 LATEST</div></div>
    <div class='light-metric'><div class='k'>运维告警</div><div class='v'><span class='light-status ${ops.alert_count?'lock':''}'>${n(ops.alert_count||0)} 条</span></div><div class='s'>最高级别 ${esc(ops.highest_severity||'INFO')}</div></div>
  </div>
  <div class='light-grid'>
    <section class='card light-section'><h2>账户持仓 <span class='muted tiny'>· QMT 只读快照</span></h2><div class='light-table-wrap'><table class='table'><tr><th>证券</th><th>数量</th><th>可用</th><th>市值</th></tr>${p.slice(0,12).map(([c,v])=>`<tr><td>${esc(c)}</td><td>${n(v.volume)}</td><td>${n(v.available)}</td><td>¥ ${n(v.market_value)}</td></tr>`).join('')||'<tr><td colspan=4 class=muted>暂无快照</td></tr>'}</table></div><div class='foot'>账户原有持仓按外部基线记录，不自动归属策略。</div></section>
    <section class='card light-section'><h2>运行链路</h2><table class='table'><tr><th>组件</th><th>状态</th></tr><tr><td>BigQMT Tray</td><td class='warn'>候选 · 未部署</td></tr><tr><td>Redis 总线</td><td class='muted'>由运行预检确认</td></tr><tr><td>QMT Bridge</td><td>${esc(bridge)}</td></tr><tr><td>行情门禁</td><td class='${stale?'warn':'ok'}'>新鲜 ${fresh} · 陈旧 ${stale}</td></tr></table><h2 style='margin-top:18px'>当前提示</h2><div class='notice'>${esc(blockers.length?lightBlock(blockers[0]):s.next_gate||'系统运行正常。')}</div></section>
  </div>
  <div class='light-grid'>
    <section class='card light-section'><h2>策略袖套与收益</h2><div class='light-table-wrap'><table class='table'><tr><th>策略</th><th>初始资金</th><th>NAV</th><th>收益率</th><th>NAV点数</th></tr>${sleeves.map(v=>{const z=v.summary||{};return `<tr><td>${esc(z.strategy_id)}</td><td>¥ ${n(z.initial_capital)}</td><td>¥ ${n(z.net_asset_value)}</td><td>${n(Number(z.return_rate||0)*100)}%</td><td>${n((v.nav_series||[]).length)}</td></tr>`}).join('')||'<tr><td colspan=5 class=muted>暂无策略袖套</td></tr>'}</table></div><div class='foot'>收益来自本地 SQLite WAL 估值；订单入口保持锁定。</div></section>
    <section class='card light-section'><h2>验证与安全状态</h2><table class='table'><tr><th>项目</th><th>状态</th></tr><tr><td>只读 Dashboard</td><td class='ok'>正常</td></tr><tr><td>订单/撤单入口</td><td class='warn'>已锁定</td></tr><tr><td>正式账户</td><td class='ok'>只读</td></tr><tr><td>模拟账户</td><td class='warn'>等待交易时段预检</td></tr></table><div class='foot'>最近验证：${(s.recent_tests||[]).slice(-3).map(i=>esc(i.name)+' · '+esc(i.status)).join(' ｜ ')||'暂无'}</div></section>
  </div>`;
}
async function loadLight(){try{renderLight(await fetch('/api/status',{cache:'no-store'}).then(r=>r.json()))}catch(e){document.querySelector('#app').innerHTML='<div class="card light-section"><div class="light-status lock">Dashboard 暂时无法读取本机状态</div><div class="foot">请确认本机 Dashboard 服务仍在运行。</div></div>'}}
// Route-aware renderer is registered below before the first refresh is scheduled.
</script>"""


HTML += """<script>
function wireSidebar(){
  const fallbackRoutes=['overview','strategies','account','orders','market','audit'];
  document.querySelectorAll('aside .nav:not(.locked)').forEach((node,index)=>{
    const target=node.dataset.route||fallbackRoutes[index];
    if(!target||node.dataset.sidebarWired)return;
    node.dataset.sidebarWired='1';node.classList.add('nav-button');node.setAttribute('role','button');node.setAttribute('tabindex','0');
    const activate=()=>{
      history.pushState({},'', '/'+(window.__bigqmtRoutePrefix||'simulation')+'/'+target);
      renderLight(window.__bigqmtStatus||{});
    };
    node.addEventListener('click',activate);node.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();activate()}});
  });
}
wireSidebar();
window.addEventListener('popstate',()=>renderLight(window.__bigqmtStatus||{}));
</script>"""

HTML += """<script>
const securityDisplayNames={'510300.SH':'华泰柏瑞沪深300ETF','511010.SH':'国债ETF','511990.SH':'华宝添益','513100.SH':'纳指ETF','513500.SH':'标普500ETF','518880.SH':'黄金ETF'};
function decorateSecurityNames(){
  const section=[...document.querySelectorAll('#app .card')].find(x=>x.querySelector('h2')?.textContent.includes('账户持仓'));
  if(!section)return;
  section.querySelectorAll('table tr').forEach((row,index)=>{
    if(index===0)return;
    const cell=row.firstElementChild;if(!cell)return;
    const code=cell.dataset.stockCode||cell.textContent.trim();const name=securityDisplayNames[code];
    if(name){cell.dataset.stockCode=code;cell.innerHTML=name+"<br><span class='muted tiny light-security-code'>"+code+"</span>";}
  });
}
decorateSecurityNames();setInterval(decorateSecurityNames,1000);
</script>"""

HTML += """<script>
const bigqmtRouteTitles={overview:'运行总览',strategies:'策略账户',account:'账户与持仓',orders:'委托与成交',market:'行情健康度',audit:'审计与日志'};
function bigqmtRoute(){const name=location.pathname.split('/').filter(Boolean).pop()||'overview';return bigqmtRouteTitles[name]?name:'overview'}
function bigqmtRows(rows){return rows.length?`<div class='light-table-wrap'><table class='table'><tr><th>证券</th><th>名称</th><th>数量</th><th>可用</th><th>市值</th></tr>${rows.map(([code,v])=>`<tr><td>${esc(code)}</td><td>${esc(securityDisplayNames[code]||'-')}</td><td>${n(v.volume)}</td><td>${n(v.available)}</td><td>¥ ${n(v.market_value)}</td></tr>`).join('')}</table></div>`:`<div class='light-empty'>暂无持仓</div>`}
// The original prototype's periodic renderer is superseded by route-aware rendering.
// Keeping it inert prevents an old in-flight refresh from replacing a dedicated page.
render=()=>{};
const renderLightBase=renderLight;
renderLight=(s)=>{
  window.__bigqmtStatus=s;
  renderLightBase(s);
  const route=bigqmtRoute(); if(route==='overview'){const mt=document.querySelector('main .title h1');if(mt)mt.textContent=bigqmtRouteTitles.overview;document.querySelectorAll('aside .nav:not(.locked)').forEach((node,index)=>node.classList.toggle('on',(node.dataset.route||['overview','strategies','account','orders','market','audit'][index])==='overview'));document.title='BigQMT · '+bigqmtRouteTitles.overview;return;}
  const x=s.snapshot||{}, q=s.quote_summary||{}, positions=Object.entries(x.positions||{}), sleeves=s.strategy_sleeves||[], shadows=s.strategy_shadows||[], registry=s.strategy_registry||[], blockers=s.active_blockers||[], orders=x.orders||[], trades=x.trades||[], ops=s.ops_alerts||{};
  const app=document.querySelector('#app'), mainTitle=document.querySelector('main .title h1');
  if(mainTitle)mainTitle.textContent=bigqmtRouteTitles[route];
  document.querySelectorAll('aside .nav:not(.locked)').forEach((node,index)=>node.classList.toggle('on',(node.dataset.route||['overview','strategies','account','orders','market','audit'][index])===route));
  const content={
    strategies:`<div class='light-grid'><section class='card light-section'><h2>策略账本</h2><div class='light-table-wrap'><table class='table'><tr><th>策略</th><th>初始资金</th><th>NAV</th><th>收益率</th><th>NAV点数</th></tr>${sleeves.map(v=>{const z=v.summary||{};return `<tr><td>${esc(z.strategy_id)}</td><td>¥ ${n(z.initial_capital)}</td><td>¥ ${n(z.net_asset_value)}</td><td>${n(Number(z.return_rate||0)*100)}%</td><td>${n((v.nav_series||[]).length)}</td></tr>`}).join('')||'<tr><td colspan=5 class=muted>暂无策略袖套</td></tr>'}</table></div></section><section class='card light-section'><h2>口径说明</h2><div class='notice'>策略袖套是本地 SQLite WAL 的独立核算账本，不会改变券商账户。510300 本次成交仅为桥接验收，不计入 v1.1.15 收益。</div></section></div><section class='card light-section'><h2>v1.1.15 收盘影子信号 <span class='muted tiny'>· 只读 / 不生成委托</span></h2><div class='light-table-wrap'><table class='table'><tr><th>信号日</th><th>当前标的</th><th>目标标的</th><th>原因</th><th>风控</th><th>数据口径</th></tr>${shadows.map(v=>{const z=v.signal||{};return `<tr><td>${esc(v.signal_day||'-')}</td><td>${esc(z.current_qmt||'现金')}</td><td>${esc(z.desired_qmt||'-')}</td><td>${esc(z.reason||'-')}</td><td>${esc(z.risk||'-')}</td><td>${esc(v.adjustment_mode||'-')} / 未完成PTrade复权等价验证</td></tr>`}).join('')||'<tr><td colspan=6 class=muted>暂无收盘影子信号</td></tr>'}</table></div><div class='foot'>影子状态只用于下一收盘日的策略状态延续；它不是订单、成交、袖套持仓或收益记录。</div></section>`,
    account:`<div class='light-metrics'><div class='light-metric'><div class='k'>账户总资产</div><div class='v'>¥ ${n(x.total_asset)}</div></div><div class='light-metric'><div class='k'>可用资金</div><div class='v'>¥ ${n(x.cash)}</div></div><div class='light-metric'><div class='k'>持仓数量</div><div class='v'>${positions.length}</div></div></div><section class='card light-section'><h2>账户持仓 <span class='muted tiny'>· QMT 只读快照</span></h2>${bigqmtRows(positions)}</section>`,
    orders:`<div class='light-grid'><section class='card light-section'><h2>委托 <span class='muted tiny'>· 当日只读</span></h2><div class='light-table-wrap'><table class='table'><tr><th>证券</th><th>方向</th><th>数量</th><th>价格</th><th>状态</th><th>委托号</th></tr>${orders.map(v=>`<tr><td>${esc(v.stock_code||'-')}</td><td>${esc(v.order_type||v.direction||'-')}</td><td>${n(v.order_volume||v.volume)}</td><td>¥ ${n(v.price)}</td><td>${esc(v.order_status||'-')}</td><td>${esc(v.order_sysid||v.order_id||'-')}</td></tr>`).join('')||'<tr><td colspan=6 class=muted>暂无委托记录</td></tr>'}</table></div></section><section class='card light-section'><h2>成交 <span class='muted tiny'>· 当日只读</span></h2><div class='light-table-wrap'><table class='table'><tr><th>证券</th><th>成交数量</th><th>成交价</th><th>成交编号</th></tr>${trades.map(v=>`<tr><td>${esc(v.stock_code||'-')}</td><td>${n(v.traded_volume||v.volume)}</td><td>¥ ${n(v.traded_price||v.price)}</td><td>${esc(v.traded_id||v.trade_id||'-')}</td></tr>`).join('')||'<tr><td colspan=4 class=muted>暂无成交记录</td></tr>'}</table></div></section></div>`,
    market:`<div class='light-metrics'><div class='light-metric'><div class='k'>行情新鲜</div><div class='v'>${n(q.states?.FRESH||0)}</div></div><div class='light-metric'><div class='k'>行情陈旧</div><div class='v'>${n(q.states?.STALE||0)}</div></div><div class='light-metric'><div class='k'>行情缺失</div><div class='v'>${n((q.missing||[]).length)}</div></div></div><section class='card light-section'><h2>行情健康度</h2><div class='notice'>缺失：${esc((q.missing||[]).join(', ')||'无')}<br>陈旧：${esc((q.stale||[]).join(', ')||'无')}<br><br>本页面只读显示，不发起订阅、下载或订单操作。</div></section>`,
    audit:`<div class='light-grid'><section class='card light-section'><h2>运维告警</h2><table class='table'><tr><th>级别</th><th>标识</th><th>说明</th></tr>${(ops.alerts||[]).map(v=>`<tr><td class='${v.severity==='CRITICAL'?'bad':'warn'}'>${esc(v.severity)}</td><td>${esc(v.id)}</td><td>${esc(v.message)}</td></tr>`).join('')||'<tr><td colspan=3 class=ok>无运维告警</td></tr>'}</table></section><section class='card light-section'><h2>最近验证</h2><table class='table'>${(s.recent_tests||[]).map(v=>`<tr><td>${esc(v.name)}</td><td>${esc(v.status)}</td></tr>`).join('')||'<tr><td class=muted>暂无验证记录</td></tr>'}</table><div class='foot'>活动阻塞：${n(blockers.length)} 项；全部告警仅供只读审计，不触发交易动作。</div></section></div>`
  }[route]||'';
  app.innerHTML=content;
  if(route==='strategies'&&registry.length){
    app.insertAdjacentHTML('beforeend',`<section class='card light-section'><h2>策略池登记</h2><div class='light-table-wrap'><table class='table'><tr><th>策略</th><th>来源</th><th>版本</th><th>状态</th><th>证券池</th><th>执行</th></tr>${registry.map(v=>`<tr><td>${esc(v.display_name||v.strategy_id)}</td><td>${esc(v.source_project||'-')}</td><td>${esc(v.version||'-')}</td><td>${esc(v.status||'-')}</td><td>${n((v.universe||{}).qmt_codes?.length||0)}</td><td>${v.execution_enabled?'启用':'关闭'}</td></tr>`).join('')}</table></div><div class='foot'>策略登记来自 strategy_registry.json；正式账户和自动执行仍被禁止。</div></section>`);
  }
  document.title='BigQMT · '+bigqmtRouteTitles[route];
}
loadLight();setInterval(loadLight,15000);
</script>"""

HTML += """<style>
.strategy-account-header{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;margin-bottom:18px}.strategy-account-header h2{margin:0 0 5px}.strategy-account-meta{color:#718096;font-size:12px}.strategy-account-metrics{display:grid;grid-template-columns:repeat(6,minmax(130px,1fr));gap:10px;margin:12px 0 18px}.strategy-account-metric{padding:12px;border:1px solid #e9edf2;border-radius:10px;background:#fbfcfe}.strategy-account-metric .k{font-size:12px;color:#718096}.strategy-account-metric .v{font-size:18px;font-weight:650;color:#172033;margin-top:5px}.strategy-account-metric .v.up{color:#16845b}.strategy-account-metric .v.down{color:#b42318}.strategy-chart{width:100%;height:238px;display:block;background:linear-gradient(180deg,#fbfdff,#fff);border:1px solid #edf0f4;border-radius:10px}.strategy-chart-grid{stroke:#e9eef5;stroke-width:1}.strategy-chart-strategy{fill:none;stroke:#2563eb;stroke-width:3;stroke-linecap:round;stroke-linejoin:round}.strategy-chart-benchmark{fill:none;stroke:#94a3b8;stroke-width:2;stroke-dasharray:6 5;stroke-linecap:round;stroke-linejoin:round}.strategy-chart-dot{fill:#2563eb}.strategy-chart-label{fill:#64748b;font-size:11px}.strategy-legend{display:flex;gap:16px;align-items:center;color:#64748b;font-size:12px;margin:0 0 8px}.strategy-legend i{display:inline-block;width:20px;border-top:3px solid #2563eb;vertical-align:middle;margin-right:5px}.strategy-legend i.benchmark{border-top:2px dashed #94a3b8}.strategy-account-layout{display:grid;grid-template-columns:1.3fr .9fr;gap:14px}.strategy-account-empty{padding:28px;text-align:center;color:#718096;border:1px dashed #d8e0ea;border-radius:10px}.strategy-account-state{white-space:nowrap}@media(max-width:1100px){.strategy-account-metrics{grid-template-columns:repeat(3,minmax(130px,1fr))}.strategy-account-layout{grid-template-columns:1fr}}@media(max-width:600px){.strategy-account-header{display:block}.strategy-account-metrics{grid-template-columns:repeat(2,minmax(120px,1fr))}}</style>
<script>
function strategyCurrency(v){return '¥ '+n(v)}
function strategyPct(v){return v==null?'—':n(Number(v)*100)+'%'}
function strategyClass(v){return Number(v||0)>0?'up':Number(v||0)<0?'down':''}
function strategySvg(navSeries, benchmarkSeries, benchmarkName){
  const source=(navSeries||[]).map(p=>({t:p.snapshot_time,v:Number(p.net_asset_value)})).filter(p=>Number.isFinite(p.v));
  const benchmark=(benchmarkSeries||[]).map(p=>({t:p.snapshot_time,v:Number(p.net_asset_value)})).filter(p=>Number.isFinite(p.v));
  const all=source.concat(benchmark);if(!all.length)return `<div class='strategy-account-empty'>等待每日净值与${esc(benchmarkName||'v1.1.17 ETF池')}基准点</div>`;
  const width=820,height=238,pad={l:52,r:18,t:18,b:30};const min=Math.min(...all.map(p=>p.v)),max=Math.max(...all.map(p=>p.v));const span=Math.max(max-min,Math.max(Math.abs(max)*0.003,1));
  const scale=(items)=>items.map((p,i)=>`${pad.l+(width-pad.l-pad.r)*(items.length===1?.5:i/(items.length-1))},${pad.t+(height-pad.t-pad.b)*(1-(p.v-(min-span*.08))/(span*1.16))}`).join(' ');
  const labels=[min,max].map(v=>`<text x='4' y='${pad.t+(height-pad.t-pad.b)*(1-(v-(min-span*.08))/(span*1.16))+4}' class='strategy-chart-label'>${n(v)}</text>`).join('');
  const grids=[.2,.5,.8].map(k=>`<line x1='${pad.l}' y1='${pad.t+(height-pad.t-pad.b)*k}' x2='${width-pad.r}' y2='${pad.t+(height-pad.t-pad.b)*k}' class='strategy-chart-grid'/>`).join('');
  const end=source[source.length-1];const dot=end?`<circle cx='${scale(source).split(' ').slice(-1)[0].split(',')[0]}' cy='${scale(source).split(' ').slice(-1)[0].split(',')[1]}' r='4' class='strategy-chart-dot'/>`:'';
  return `<svg class='strategy-chart' viewBox='0 0 ${width} ${height}' preserveAspectRatio='none'>${grids}${labels}${benchmark.length?`<polyline points='${scale(benchmark)}' class='strategy-chart-benchmark'/>`:''}<polyline points='${scale(source)}' class='strategy-chart-strategy'/>${dot}<text x='${pad.l}' y='${height-9}' class='strategy-chart-label'>${source[0]?.t?.slice(0,10)||''}</text><text x='${width-112}' y='${height-9}' class='strategy-chart-label'>${source.at(-1)?.t?.slice(0,10)||''}</text></svg>`;
}
function strategyAccountCard(v){
  const s=v.summary||{},m=v.metrics||{},positions=s.positions||[],bench=v.benchmark_series||[];
  return `<section class='card light-section'><div class='strategy-account-header'><div><h2>${esc(v.display_name||s.strategy_id)}</h2><div class='strategy-account-meta'>独立策略账户 · ${esc(v.version||'—')} · 袖套 ID：${esc(s.strategy_id)}</div></div><span class='light-status strategy-account-state ${v.status==='SHADOW_ONLY'?'wait':''}'>${esc(v.status||'ACTIVE_ACCOUNT')}</span></div>
  <div class='strategy-account-metrics'><div class='strategy-account-metric'><div class='k'>初始资金</div><div class='v'>${strategyCurrency(m.initial_capital)}</div></div><div class='strategy-account-metric'><div class='k'>当前净值</div><div class='v'>${strategyCurrency(m.net_asset_value)}</div></div><div class='strategy-account-metric'><div class='k'>累计收益</div><div class='v ${strategyClass(m.return_rate)}'>${strategyPct(m.return_rate)}</div></div><div class='strategy-account-metric'><div class='k'>当日盈亏</div><div class='v ${strategyClass(m.daily_pnl)}'>${strategyCurrency(m.daily_pnl)}</div></div><div class='strategy-account-metric'><div class='k'>最大回撤</div><div class='v down'>${strategyPct(-m.maximum_drawdown)}</div></div><div class='strategy-account-metric'><div class='k'>超额收益 / ${esc(m.benchmark_name||'v1.1.17 ETF池')}</div><div class='v ${strategyClass(m.excess_return_rate)}'>${strategyPct(m.excess_return_rate)}</div></div></div>
  <div class='strategy-account-layout'><div><div class='strategy-legend'><span><i></i>策略净值</span><span><i class='benchmark'></i>${esc(m.benchmark_name||'v1.1.17 ETF池')}</span></div>${strategySvg(v.nav_series,bench,m.benchmark_name)}</div><div class='notice'>策略净值仅由可归属真实成交、手续费和本地 SQLite WAL 估值形成。<br><br>基准为 v1.1.17 U25 无酒 ETF 池的等权日收益链，仅用于比较，不代表策略实际持有整个 ETF 池。</div></div>
<div class='strategy-account-layout' style='margin-top:14px'><div><h2>策略归属持仓</h2><div class='light-table-wrap'><table class='table'><tr><th>证券</th><th>数量</th><th>成本</th><th>现价</th><th>浮动盈亏</th></tr>${positions.map(p=>`<tr><td>${esc(p.display_name||p.stock_code)}<div class='strategy-account-meta'>${esc(p.stock_code)}</div></td><td>${n(p.quantity)}</td><td>¥ ${n(p.cost_amount)}</td><td>¥ ${n(p.market_price)}</td><td class='${strategyClass(p.unrealized_pnl)}'>¥ ${n(p.unrealized_pnl)}</td></tr>`).join('')||'<tr><td colspan=5 class=muted>当前为空仓</td></tr>'}</table></div></div><div><h2>账户资金</h2><table class='table'><tr><td>可用现金</td><td>¥ ${n(s.cash)}</td></tr><tr><td>冻结资金</td><td>¥ ${n(s.frozen_cash)}</td></tr><tr><td>持仓市值</td><td>¥ ${n(s.market_value)}</td></tr><tr><td>已实现盈亏</td><td class='${strategyClass(s.realized_pnl)}'>¥ ${n(s.realized_pnl)}</td></tr><tr><td>基准收益</td><td>${strategyPct(m.benchmark_return_rate)}</td></tr></table></div></div></section>`;
}
const renderLightBaseForSupplement=renderLight;
// Snapshot the base strategies content (shadow signal + pool registry) before
// the strategy-account page replaces #app, so the strategies route stays whole.
function renderLightBeforeStrategyAccounts(status){renderLightBaseForSupplement(status);if(bigqmtRoute()!=='strategies')return;const host=document.querySelector('#app');window.__bigqmtStrategyExtra=host?host.innerHTML:'';}
// Re-append the snapshot after the strategy-account page is drawn. Installed as
// a microtask so it wraps the reassignment of renderLight in this same block.
queueMicrotask(function(){renderLight=(function(prev){return function(status){prev(status);if(bigqmtRoute()!=='strategies')return;const extra=window.__bigqmtStrategyExtra;if(!extra)return;const app=document.querySelector('#app');if(!app)return;const holder=document.createElement('div');holder.innerHTML=extra;Array.prototype.slice.call(holder.querySelectorAll('section')).forEach(function(sec){const h=sec.querySelector('h2');if(h&&h.textContent.indexOf('策略账本')>=0&&sec.parentNode){sec.parentNode.removeChild(sec);}});while(holder.firstChild)app.appendChild(holder.firstChild);};})(renderLight);});
renderLight=(status)=>{renderLightBeforeStrategyAccounts(status);if(bigqmtRoute()!=='strategies')return;const sleeves=status.strategy_sleeves||[],app=document.querySelector('#app');document.querySelector('aside .nav:nth-child(2)').textContent='策略账户';app.innerHTML=`<div class='strategy-account-header'><div><h1 style='margin:0'>策略账户</h1><div class='strategy-account-meta'>每个策略独立核算、独立复利；券商总账户仅用于持仓事实对账。</div></div><span class='light-status'>只读数据投影</span></div>${sleeves.map(strategyAccountCard).join('')||'<section class="card light-section"><div class="strategy-account-empty">暂无已启用的策略账户</div></section>'}`;};
</script>"""


class Handler(BaseHTTPRequestHandler):
    def _send(self, body: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-BigQMT-Dashboard-Build", BUILD_ID)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        profile = str(getattr(self.server, "dashboard_profile", "simulation"))
        route_prefix = "simulation" if profile == "simulation" else "production-readonly"
        if self.path == "/healthz":
            body = json.dumps({"status": "ok", "read_only": True, "profile": profile}).encode("utf-8")
            self._send(body, "application/json")
        elif self.path == "/api/status":
            self._send(json.dumps(build_dashboard_status(ROOT, profile), ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
        elif self.path in ("/", *[f"/{route_prefix}/{name}" for name in ("overview", "strategies", "account", "orders", "market", "audit")]):
            subtitle = "模拟盘运行监控" if profile == "simulation" else "正式盘只读运行监控"
            page = HTML.replace("__DASHBOARD_SUBTITLE__", subtitle)
            page = "<script>window.__bigqmtRoutePrefix=" + json.dumps(route_prefix) + ";</script>" + page
            self._send(page.encode("utf-8"), "text/html; charset=utf-8")
        else:
            self._send(b"not found", "text/plain", 404)

    def log_message(self, *_: object) -> None:
        return


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=17890)
    parser.add_argument("--profile", choices=("simulation", "production_readonly"), default="simulation")
    args = parser.parse_args()
    if dashboard_already_listening(args.port):
        print(
            "BigQMT dashboard not started: port %d is already serving. "
            "Stop the existing dashboard first so it cannot serve a stale build." % args.port,
            file=sys.stderr,
        )
        return 3
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.dashboard_profile = args.profile
    print("BigQMT %s read-only dashboard: http://127.0.0.1:%d/ (build %s)" % (args.profile, args.port, BUILD_ID))
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
