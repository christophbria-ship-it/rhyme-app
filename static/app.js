const $=s=>document.querySelector(s),q=$('#q'),sug=$('#sug'),status=$('#status'),results=$('#results');
let sugIdx=-1,sugTimer,ctrl;
const esc=s=>s.replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
q.addEventListener('input',()=>{clearTimeout(sugTimer);sugTimer=setTimeout(loadSug,120)});
async function loadSug(){const v=q.value.trim();if(document.activeElement!==q){sug.hidden=true;return}if(!v){sug.hidden=true;return}
  try{const r=await fetch('api/suggest?q='+encodeURIComponent(v));const d=await r.json();
    sugIdx=-1;sug.innerHTML=d.suggestions.map((w,i)=>`<li role="option" data-w="${esc(w)}">${esc(w)}</li>`).join('');sug.hidden=!d.suggestions.length}catch(e){sug.hidden=true}}
sug.addEventListener('mousedown',e=>{const li=e.target.closest('li');if(li){q.value=li.dataset.w;sug.hidden=true;search()}});
q.addEventListener('keydown',e=>{const items=[...sug.querySelectorAll('li')];if(sug.hidden||!items.length)return;
  if(e.key==='ArrowDown'||e.key==='ArrowUp'){e.preventDefault();sugIdx=(sugIdx+(e.key==='ArrowDown'?1:-1)+items.length)%items.length;
    items.forEach((li,i)=>li.setAttribute('aria-selected',i===sugIdx));q.value=items[sugIdx].dataset.w}
  else if(e.key==='Escape')sug.hidden=true});
q.addEventListener('blur',()=>setTimeout(()=>sug.hidden=true,150));
$('#f').addEventListener('submit',e=>{e.preventDefault();sug.hidden=true;search()});
['#syl','#pos','#freq','#minl','#maxl','#sort','#tiers'].forEach(s=>$(s).addEventListener('change',()=>q.value.trim()&&search()));
results.addEventListener('click',e=>{const w=e.target.closest('.w');if(w){q.value=w.dataset.w;search();scrollTo(0,0)}});
async function search(){clearTimeout(sugTimer);sug.hidden=true;
  const w=q.value.trim();if(!w){showErr('Please enter a word.');return}
  const p=themeParams(new URLSearchParams({word:w,sort:$('#sort').value,limit:'1000'}));
  [['syllables','#syl'],['pos','#pos'],['min_freq','#freq'],['min_len','#minl'],['max_len','#maxl']].forEach(([k,s])=>{if($(s).value)p.set(k,$(s).value)});
  history.replaceState(null,'','?'+new URLSearchParams({w})+location.hash);
  ctrl&&ctrl.abort();ctrl=new AbortController();
  status.innerHTML='<span class="spinner"></span>Finding rhymes…';status.dataset.state='loading';
  results.innerHTML='<div class="skel"></div><div class="skel" style="width:70%"></div><div class="skel" style="width:85%"></div>';
  try{const r=await fetch('api/rhymes?'+p,{signal:ctrl.signal});const d=await r.json();
    if(!r.ok)throw new Error(d.error||('HTTP '+r.status));render(d)}
  catch(e){if(e.name!=='AbortError')showErr('Something went wrong: '+e.message)}}
function showErr(m){status.dataset.state='error';status.innerHTML=`<div class="err" role="alert">${esc(m)}</div>`;results.innerHTML=''}
function render(d){
  const show=$('#tiers').value,tiers=[['perfect','Perfect rhymes','Same sounds from the last stressed vowel'],['near','Near rhymes','Similar consonant families'],['slant','Slant rhymes','Shared vowels (assonance) or consonants (consonance)']].filter(t=>show==='all'||show===t[0]);
  const total=tiers.reduce((a,t)=>a+(d[t[0]+'_total']||0),0);
  let meta=`<span class="meta">${esc(d.word)}${d.pronunciations.length?' · /'+esc(d.pronunciations[0])+'/':''}${d.guessed_from?` · not in dictionary, pronunciation guessed from “${esc(d.guessed_from)}”`:''} · ${total} results in ${d.elapsed_ms} ms${d.theme?` · <span class="ontheme">✦ ${d.themed_total} on theme</span>`:''}</span>`;
  if(!total){status.dataset.state='empty';status.innerHTML=meta;results.innerHTML=`<div class="empty" id="empty">No rhymes found for “${esc(d.word)}”. Try loosening the filters or another word.</div>`;return}
  status.dataset.state='done';status.innerHTML=meta;
  if(d.theme==='related')setTimeout(()=>loadRelated(d.word));
  results.innerHTML='<div id="relSlot"></div>'+tiers.map(([k,title,desc])=>{const items=d[k];if(!items.length)return'';
    const groups={};items.forEach(it=>(groups[it.syllables]=groups[it.syllables]||[]).push(it));
    return `<section class="tier" data-tier="${k}"><h2>${title}<span class="badge b-${k}">${d[k+'_total']}</span> <small>${desc}</small></h2>`+
      Object.keys(groups).sort((a,b)=>a-b).map(s=>`<div class="group"><h3>${s} syllable${s==1?'':'s'}</h3><div class="words">`+
        groups[s].map(it=>`<span class="w ${it.freq>=4?'common':it.freq<1?'rare':''}${it.conf&&it.conf!=='dict'?' gen':''}${it.themed?' on':''}" data-w="${esc(it.word)}" title="${esc((it.pos.join(', ')||'—')+' · zipf '+it.freq+(it.conf&&it.conf!=='dict'?' · generated pronunciation ('+it.conf+')':'')+(it.themed?' · on theme':''))}">${esc(it.word)}${it.matched_syllables>1?`<sup>×${it.matched_syllables}</sup>`:''}</span>`).join('')+'</div></div>').join('')+'</section>'}).join('')}
const init=new URLSearchParams(location.search).get('w');

// ---------------- tabs ----------------
const TABS=['rhymes','line','pad'];
function showTab(t){if(!TABS.includes(t))t='rhymes';TABS.forEach(x=>{$('#tab-'+x).hidden=x!==t;$('#t-'+x).setAttribute('aria-selected',x===t)});
  document.body.dataset.tab=t;if(t==='pad')padAnalyze()}
addEventListener('hashchange',()=>showTab(location.hash.slice(1)));
// ---------------- themed rhymes toggle ----------------
const tToggle=$('#themeToggle'),tSel=$('#theme'),tOnly=$('#themeOnly');let themesLoaded=false;
let THEMES=[];
async function loadThemes(){if(themesLoaded)return;
  tSel.innerHTML='<option value="related">Related to my word</option>';tSel.value='related';
  try{const r=await fetch('api/themes');const d=await r.json();THEMES=d.themes;
    tSel.innerHTML+='<optgroup label="Mood themes">'+d.themes.map(t=>`<option value="${esc(t.id)}">${esc(t.label)}</option>`).join('')+'</optgroup>';themesLoaded=true;
    fillMoods()}catch(e){}
  const saved=localStorage.getItem('rhymer-theme');if(saved&&(saved==='related'||THEMES.some(t=>t.id===saved)))tSel.value=saved}
function themeParams(p){if(tToggle.checked&&tSel.value){p.set('theme',tSel.value);if(tOnly.checked)p.set('theme_only','1')}return p}
function themeChanged(){tToggle.setAttribute('aria-checked',tToggle.checked);tSel.disabled=tOnly.disabled=!tToggle.checked;
  document.body.classList.toggle('themed',tToggle.checked&&!!tSel.value);localStorage.setItem('rhymer-theme-on',tToggle.checked?'1':'');
  if(tSel.value)localStorage.setItem('rhymer-theme',tSel.value);rerun()}
function rerun(){const t=document.body.dataset.tab;if(t==='line'){if($('#prevLine').value.trim())lineHelp()}else if(q.value.trim())search()}
tToggle.addEventListener('change',async()=>{if(tToggle.checked){await loadThemes();if(!tSel.value)tSel.value='related'}themeChanged()});
tSel.addEventListener('change',themeChanged);tOnly.addEventListener('change',themeChanged);
// ---------------- line helper ----------------
const lineStatus=$('#lineStatus'),lineOut=$('#lineOut');
const meter=l=>!l||!l.words.length?'<span class="meta">—</span>':l.words.map(w=>`<span class="mw${w.known?'':' unk'}" title="${esc(w.stress.replace(/\//g,'DUM ').replace(/u/g,'da ').trim())}"><b>${esc(w.word)}</b><i>${esc(w.stress.replace(/\//g,'●').replace(/u/g,'○'))}</i></span>`).join('');
async function lineHelp(){const prev=$('#prevLine').value.trim();if(!prev){lineStatus.dataset.state='error';lineStatus.innerHTML='<div class="err" role="alert">Write the line you want to rhyme with first.</div>';lineOut.innerHTML='';return}
  lineStatus.dataset.state='loading';lineStatus.innerHTML='<span class="spinner"></span>Counting syllables…';
  const p=themeParams(new URLSearchParams({prev,line:$('#curLine').value,limit:'60'}));
  try{const r=await fetch('api/line?'+p);const d=await r.json();if(!r.ok)throw new Error(d.error||('HTTP '+r.status));renderLine(d)}
  catch(e){lineStatus.dataset.state='error';lineStatus.innerHTML=`<div class="err" role="alert">Something went wrong: ${esc(e.message)}</div>`;lineOut.innerHTML=''}}
function renderLine(d){const all=['perfect','near','slant'].flatMap(t=>d.suggestions[t].map(x=>({...x,tier:t})));
  const need=d.needed?`needs <strong>${d.needed}</strong> more syllable${d.needed==1?'':'s'}`:'is already as long as the first line';
  lineStatus.dataset.state=all.length?'done':'empty';
  lineStatus.innerHTML=`<span class="meta">Rhyming with “${esc(d.end_word)}” · ${d.target_syllables} syllables · your line ${need}${d.needed&&!d.fits_count?' — no rhymes fit exactly, showing any length':''}</span>`;
  lineOut.innerHTML=`<div class="card meters"><div class="mrow"><span class="ml">${d.prev.syllables}</span><div class="mws">${meter(d.prev)}</div></div>
    <div class="mrow"><span class="ml">${d.line.syllables}</span><div class="mws">${meter(d.line)}</div></div></div>`+
    (all.length?['perfect','near','slant'].filter(t=>d.suggestions[t].length).map(t=>`<section class="tier" data-tier="${t}"><h2>${{perfect:'Perfect endings',near:'Near endings',slant:'Slant endings'}[t]}<span class="badge b-${t}">${d.suggestions[t].length}</span></h2><div class="words">`+
      d.suggestions[t].map(x=>`<button type="button" class="w sugw${x.themed?' on':''}${x.conf!=='dict'?' gen':''}" data-w="${esc(x.word)}" title="${x.syllables} syllable${x.syllables==1?'':'s'}${x.themed?' · on theme':''}">${esc(x.word)}<sup>${x.syllables}</sup></button>`).join('')+'</div></section>').join('')
    :`<div class="empty" id="lineEmpty">No endings found for “${esc(d.end_word)}”. Try a different word at the end of the first line.</div>`)}
lineOut.addEventListener('click',e=>{const b=e.target.closest('.sugw');if(!b)return;const c=$('#curLine');c.value=(c.value.trim()+' '+b.dataset.w).trim();c.focus();lineHelp()});
$('#lineGo').addEventListener('click',lineHelp);
['#prevLine','#curLine'].forEach(s=>$(s).addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();lineHelp()}}));
$('#lineSample').addEventListener('click',()=>{$('#prevLine').value='The waves were crashing at my feet';$('#curLine').value='My heart was skipping';lineHelp()});
// ---------------- lyrics pad ----------------
const pad=$('#pad'),padLines=$('#padLines');let padTimer,padSeq=0;
pad.value=localStorage.getItem('rhymer-pad')||'';
pad.addEventListener('input',()=>{localStorage.setItem('rhymer-pad',pad.value);$('#padSaved').textContent='Saved';clearTimeout(padTimer);padTimer=setTimeout(padAnalyze,180)});
const LCOL=['#7A3E1D','#2F6B5E','#6B4C9A','#9A3B52','#3E6A9A','#8A6A1F','#4F7A2E','#A0522D'];
async function padAnalyze(){const seq=++padSeq,text=pad.value;
  try{const r=await fetch('api/analyze',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text})});const d=await r.json();
    if(seq!==padSeq)return;if(!r.ok)throw new Error(d.error);
    padLines.innerHTML=d.lines.map((l,i)=>!l.words.length?'<li class="blank"></li>':`<li data-n="${i+1}"><span class="syl" title="syllables">${l.syllables}</span><span class="let${l.match?' m-'+l.match:''}" style="--c:${LCOL[(l.letter.charCodeAt(0)-65)%LCOL.length]}" title="${l.match?l.match+' rhyme':'new rhyme sound'}">${l.letter}</span><button type="button" class="endw" data-w="${esc(l.end)}">${esc(l.end)}</button></li>`).join('');
    const words=d.lines.reduce((a,l)=>a+l.words.length,0);
    $('#padStats').innerHTML=d.total_lines?`<span id="scheme">Scheme <b>${esc(d.scheme)}</b></span> · ${d.total_lines} line${d.total_lines==1?'':'s'} · ${words} words · ${d.total_syllables} syllables · <span id="density" title="Rhyme density: average length (in vowels) of the longest rhyme each word makes with the 15 words before it. Typical pop lyrics ≈ 0.7–0.9; dense rap 1.1+">Rhyme density <b>${d.rhyme_density.toFixed(2)}</b></span>`:'Your verse analysis will appear here.';
  }catch(e){if(seq===padSeq)$('#padStats').innerHTML=`<div class="err" role="alert">Couldn't analyse lyrics: ${esc(e.message)}</div>`}}
padLines.addEventListener('click',e=>{const b=e.target.closest('.endw');if(!b)return;q.value=b.dataset.w;location.hash='#rhymes';search()});
$('#padClear').addEventListener('click',()=>{if(!pad.value||confirm('Clear the lyrics pad?')){pad.value='';localStorage.removeItem('rhymer-pad');padAnalyze()}});
$('#padCopy').addEventListener('click',async()=>{try{await navigator.clipboard.writeText(pad.value);$('#padSaved').textContent='Copied'}catch(e){pad.select();document.execCommand('copy');$('#padSaved').textContent='Copied'}});
$('#padDownload').addEventListener('click',()=>{const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([pad.value],{type:'text/plain'}));a.download='lyrics.txt';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)});
// restore theme toggle + initial tab
(async()=>{const on=localStorage.getItem('rhymer-theme-on');await loadThemes();  // default: on, "Related to my word"
  if(on===null||on==='1'){tToggle.checked=true;tToggle.setAttribute('aria-checked','true');tSel.disabled=tOnly.disabled=false;document.body.classList.toggle('themed',!!tSel.value)}
  showTab(location.hash.slice(1));if(init){q.value=init;search()}})();

// ---------------- related rhymes card ("Related to my word") + AI brainstorm ----------------
const TIERNAME={perfect:'perfect',near:'near',slant:'slant',assonant:'vowel match'};
const AI_V='6f';const AI_BASE=window.RHYMER_AI_BASE||(window.RHYMER_AI_URL?window.RHYMER_AI_URL.replace(/lines$/,''):'api/ai/');
const GROUPS=[['perfect','Perfect & near','Same ending sound'],['multi','Multi-syllable','Longer words and multi-syllable matches'],['slant','Slant & vowel','Shared vowel, close consonants'],['phrase','Phrases','Multi-word & compound rhymes — tap to copy']];
const bsOn=()=>localStorage.getItem('rhymer-bs')!=='0';
function lsGet(k,maxAge){try{const v=JSON.parse(localStorage.getItem(k));if(v&&Date.now()-v.t<maxAge)return v.d}catch(e){}return null}
function lsSet(k,d){try{localStorage.setItem(k,JSON.stringify({t:Date.now(),d}))}catch(e){try{Object.keys(localStorage).filter(x=>x.startsWith('rhymer-c:')).slice(0,50).forEach(x=>localStorage.removeItem(x))}catch(_){}}}
async function aiGet(kind,body,timeout=30000){const key='rhymer-c:'+AI_V+kind+':'+JSON.stringify(body),hit=lsGet(key,30*864e5);if(hit)return{...hit,cached:true};
  if(navigator.onLine===false)throw new Error('offline');const ac=new AbortController(),to=setTimeout(()=>ac.abort(),timeout);
  try{const q=JSON.stringify(body);const r=AI_BASE.startsWith('http')&&q.length<6000?await fetch(AI_BASE+kind+'?v='+AI_V+'&q='+encodeURIComponent(q),{signal:ac.signal}):
      await fetch(AI_BASE+kind,{method:'POST',headers:{'Content-Type':'application/json'},body:q,signal:ac.signal});
    let d;try{d=await r.json()}catch(e){d={}}if(!r.ok)throw new Error(d.error||('HTTP '+r.status));lsSet(key,d);return d}
  catch(e){throw e.name==='AbortError'?new Error('timed out'):e}finally{clearTimeout(to)}}
function chip(x,ai){const t=x.tier,sym=t==='perfect'?'●':t==='near'?'◐':'○';
  return `<span class="w rel t-${t}${x.conf&&x.conf!=='dict'?' gen':''}${ai?' ai':''}" data-w="${esc(x.word)}" title="${esc(TIERNAME[t]+(x.assoc!=null?' · association '+x.assoc:'')+(x.matched>1?' · '+x.matched+' syllables match':'')+(ai?' · AI brainstorm, verified':''))}">${esc(x.word)}<sup>${ai?'✨':sym}${x.matched>1?'×'+x.matched:''}</sup></span>`}
function phraseBtn(p,ai){return `<button type="button" class="phrase t-${p.tier}${ai?' ai':''}" data-copy="${esc(p.text)}" title="${esc(TIERNAME[p.tier]+(p.source?' · '+({ai:'lyric bank',wikt:'idiom',cn:'ConceptNet',combo:'word combo'}[p.source]||p.source):'')+(ai?' · AI brainstorm, verified':''))}">${esc(p.text)}${ai?' ✨':''}</button>`}
const REL_CAP={perfect:30,multi:24,slant:30,phrase:16},relOpen=new Set();
function renderRel(slot,d,bs){const g={perfect:[],multi:[],slant:[],phrase:[]},seen=new Set();
  d.related.forEach(x=>{g[x.group].push(chip(x,false));seen.add(x.word)});d.phrases.forEach(p=>{g.phrase.push(phraseBtn(p,false));seen.add(p.text)});
  let added=0;if(bs&&bs.items)bs.items.forEach(x=>{if(seen.has(x.text))return;seen.add(x.text);added++;
    if(x.group==='phrase')g.phrase.unshift(phraseBtn({text:x.text,tier:x.tier},true));else g[x.group].unshift(chip({word:x.text,tier:x.tier,matched:x.matched},true))});
  const total=Object.values(g).reduce((a,x)=>a+x.length,0);
  const bsState=!bsOn()?'off':bs===undefined?'loading':bs&&bs.error?'error':bs?'done':'off';
  slot.innerHTML=`<section class="card relcard" id="relCard" data-bs="${bsState}"><div class="relhead"><h2 class="ptitle">Related to “${esc(d.word)}” <span class="badge b-perfect" id="relTotal">${total}</span></h2>
    <label class="chk bschk"><input type="checkbox" id="bsToggle"${bsOn()?' checked':''}> ✨ AI brainstorm</label></div>
    <p class="hint">Rhymes connected to your word's meaning, strongest first · ● perfect ◐ near ○ slant/vowel · ×2 = multi-syllable match${bsState==='done'?` · <span class="bsnote">✨ ${added} more from AI${bs.model?' ('+esc(bs.model.split('/').pop())+')':''}, verified by the rhyme engine</span>`:bsState==='loading'?' · <span class="bsnote"><span class="spinner"></span>AI brainstorming…</span>':bsState==='error'?` · <span class="bsnote">AI brainstorm unavailable (${esc(bs.error)})</span>`:''}</p>
    ${GROUPS.map(([k,t,desc])=>{const n=g[k].length,cap=REL_CAP[k];if(!n)return'';const open=relOpen.has(k);
      return `<div class="relgroup${open?' open':''}" data-group="${k}"><h3 class="subh">${t} <span class="cnt">${n}</span> <small>${desc}</small></h3><div class="words${k==='phrase'?' phrases':''}">${g[k].map((h,i)=>i<cap?h:h.replace(/^<(span|button) class="/,'<$1 class="xtra ')).join('')}</div>${n>cap?`<button type="button" class="ghost relmore" data-g="${k}" aria-expanded="${open}">${open?'Show fewer':`Show all ${n}`}</button>`:''}</div>`}).join('')}</section>`;
  slot.querySelectorAll('.relmore').forEach(b=>b.addEventListener('click',()=>{const k=b.dataset.g,grp=b.parentElement,o=!grp.classList.contains('open');
    grp.classList.toggle('open',o);o?relOpen.add(k):relOpen.delete(k);b.setAttribute('aria-expanded',o);b.textContent=o?'Show fewer':`Show all ${g[k].length}`}));
  slot.querySelector('#bsToggle').addEventListener('change',e=>{localStorage.setItem('rhymer-bs',e.target.checked?'1':'0');loadRelated(d.word)})}
async function brainstorm(word){
  const d=await aiGet('brainstorm',{word},40000);
  const items=[...new Set(['perfect','multi','slant','phrases'].flatMap(k=>Array.isArray(d[k])?d[k]:[]).filter(s=>typeof s==='string'&&s&&s.length<=60))].slice(0,200);
  const r=await fetch('api/verify',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({word,items})});const v=await r.json();if(!r.ok)throw new Error(v.error||r.status);
  return{items:v.items,model:d.model,proposed:items.length}}
async function loadRelated(word){const slot=$('#relSlot');if(!slot)return;
  slot.innerHTML='<div class="card relcard"><div class="skel" style="width:60%"></div></div>';
  try{const r=await fetch('api/related?'+new URLSearchParams({word,limit:'300',phrases:'120'}));const d=await r.json();if(!r.ok)throw new Error(d.error||r.status);
    if($('#q').value.trim().toLowerCase()!==d.word||!$('#relSlot'))return;
    if(!d.in_vocab||!(d.related.length||d.phrases.length)){slot.innerHTML=`<div class="card relcard" id="relCard"><h2 class="ptitle">Related to “${esc(d.word)}”</h2><p class="hint">No associations for this word yet — showing plain rhymes below.</p></div>`;return}
    const on=bsOn()&&navigator.onLine!==false;renderRel(slot,d,on?undefined:null);
    if(on){let bs;try{bs=await brainstorm(d.word)}catch(e){bs={error:e.message}}
      if($('#q').value.trim().toLowerCase()===d.word&&$('#relSlot')===slot)renderRel(slot,d,bs)}}
  catch(e){slot.innerHTML=`<div class="card relcard"><div class="err" role="alert">Related words unavailable: ${esc(e.message)}</div></div>`}}
async function copyText(t,btn){try{await navigator.clipboard.writeText(t)}catch(e){const ta=document.createElement('textarea');ta.value=t;document.body.appendChild(ta);ta.select();document.execCommand('copy');ta.remove()}
  if(btn){const o=btn.textContent;btn.classList.add('copied');btn.dataset.label=o;btn.textContent='Copied ✓';setTimeout(()=>{btn.textContent=btn.dataset.label;btn.classList.remove('copied')},1200)}}
document.addEventListener('click',e=>{const b=e.target.closest('.phrase');if(b){e.stopPropagation();copyText(b.dataset.copy,b)}},true);

// ---------------- AI line writer (Cloudflare Worker): many candidates, scored by the rhyme engine, best 8 shown ----------------
const MOODS=[['any','Any mood'],['related','Related to the line'],['hopeful','Hopeful'],['dark','Dark'],['nostalgic','Nostalgic'],['angry','Angry'],['dreamy','Dreamy']];
const RHYME_HINT=w=>/^[a-z]{3,}$/.test(w);
function fillMoods(){document.querySelectorAll('.aimood').forEach(s=>{const v=s.value;s.innerHTML=MOODS.map(([v,l])=>`<option value="${v}">${l}</option>`).join('')+
  (THEMES.length?'<optgroup label="Themes">'+THEMES.map(t=>`<option value="${esc(t.id)}">${esc(t.label)}</option>`).join('')+'</optgroup>':'');if(v)s.value=v})}
const scoreCls=s=>s>=80?'hi':s>=60?'mid':'lo';
function makeAI(box,{getInput,onInsert}){
  box.innerHTML=`<div class="card"><div class="aihead"><h2 class="ptitle">✨ AI lines</h2><label class="chk">Mood <select class="aimood" aria-label="Mood"></select></label></div>
    <p class="hint aisrc"></p><div class="aistatus" aria-live="polite"></div><ol class="ailist"></ol>
    <div class="row"><button type="button" class="ghost aimore" hidden>More lines</button></div></div>`;
  fillMoods();const st=box.querySelector('.aistatus'),list=box.querySelector('.ailist'),more=box.querySelector('.aimore'),mood=box.querySelector('.aimood');
  let pool=[],shownTexts=new Set(),cur=null,busy=false,seed=0,hintsCache=null,stats={cands:0,model:''};
  async function hints(line,m){const p=new URLSearchParams({prev:line,line:'',limit:'40'});if(m==='related'||THEMES.some(t=>t.id===m))p.set('theme',m);
    const r=await fetch('api/line?'+p);const d=await r.json();if(!r.ok)throw new Error(d.error||r.status);
    // hints: perfect rhymes first (related to the line's meaning, then the most common), near rhymes only to fill up
    let rel=[];try{const rr=await fetch('api/related?'+new URLSearchParams({word:d.end_word,limit:'120',phrases:'0'}));if(rr.ok){const j=await rr.json();
      rel=j.related.filter(x=>x.group!=='slant'&&x.freq>=3.8&&x.pos.length&&RHYME_HINT(x.word))}}catch(e){}
    const H=[],addH=w=>{if(H.length<10&&!H.includes(w)&&w!==d.end_word)H.push(w)};
    rel.filter(x=>x.tier==='perfect').slice(0,7).forEach(x=>addH(x.word));
    d.suggestions.perfect.filter(x=>x.freq>=4.2&&x.pos.length&&RHYME_HINT(x.word)).sort((a,b)=>b.freq-a.freq).slice(0,12).forEach(x=>{if(H.length<8)addH(x.word)});
    rel.forEach(x=>addH(x.word));d.hintWords=H;
    d.rhythm=(d.prev.words||[]).map(w=>[...w.stress].map(c=>c==='/'?'DUM':'da').join('-')).join(' ');return d}
  function fallback(msg,h){box.dataset.state='fallback';more.hidden=true;
    const ends=h?['perfect','near'].flatMap(t=>h.suggestions[t]).slice(0,24):[];
    st.innerHTML=`<div class="note">AI unavailable (${esc(msg)}) — showing offline rhyme suggestions instead.</div>`+
      (ends.length?`<div class="words fb">${ends.map(x=>`<button type="button" class="w fbw" data-copy="${esc(x.word)}">${esc(x.word)}<sup>${x.syllables}</sup></button>`).join('')}</div>`:'')}
  function row(x){const det=[x.multi?`×${x.multi+1} multi`:'',x.internal?`${x.internal} internal`:''].filter(Boolean);
    return `<li class="ail t-${x.tier}"><span class="sc s-${scoreCls(x.score)}" title="Line score: end-rhyme strength, multi-syllable match, internal rhymes, syllable fit, freshness${x.sense!=null?', editor sense '+x.sense+'/10':''}">${x.score}</span><span class="tb t-${x.tier}">${x.tier==='assonant'?'vowel':x.tier}</span>${det.map(t=>`<span class="tb tx">${t}</span>`).join('')}<span class="txt">${esc(x.text)}</span><span class="syl" title="syllables">${x.syllables} syl</span>
      <button type="button" class="ghost cp" data-copy="${esc(x.text)}" aria-label="Copy line">Copy</button>${onInsert?`<button type="button" class="ghost ins" data-t="${esc(x.text)}">Insert</button>`:''}</li>`}
  const senseOf=new Map();
  async function rank(line,lines){lines=lines.slice(0,40).map(s=>String(s).slice(0,200));const body={line,lines,keep:40};
    if(lines.some(t=>senseOf.has(t)))body.sense=lines.map(t=>senseOf.has(t)?senseOf.get(t):6);
    const rr=await fetch('api/rank_lines',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    if(!rr.ok)return lines.map(t=>({text:t,tier:'none',syllables:0,score:0,multi:0,internal:0}));return(await rr.json()).lines}
  function showNext(){const fresh=pool.filter(x=>!shownTexts.has(x.text)&&x.tier!=='none'&&x.score>=35).slice(0,8);fresh.forEach(x=>shownTexts.add(x.text));
    list.insertAdjacentHTML('beforeend',fresh.map(row).join(''));return fresh.length}
  async function run(isMore){if(busy)return;const inp=getInput();if(!inp||!inp.line.trim()){box.hidden=false;box.dataset.state='error';st.innerHTML='<div class="err" role="alert">Write a lyric line first.</div>';return}
    busy=true;box.hidden=false;const line=inp.line.trim().slice(0,200);
    if(!isMore||!cur||cur.line!==inp.line||cur.mood!==mood.value){pool=[];shownTexts=new Set();list.innerHTML='';seed=0;hintsCache=null;stats={cands:0,model:''}}cur={...inp,mood:mood.value};
    box.querySelector('.aisrc').innerHTML=`Next lines for “${esc(line)}”`;box.dataset.state='loading';more.hidden=true;
    if(isMore&&showNext()>=8){box.dataset.state='done';status();busy=false;return}
    st.innerHTML=`<span class="spinner"></span>Writing ${isMore?'more ':''}lines and checking every rhyme…`;let h=hintsCache;
    try{if(!h)h=hintsCache=await hints(line,mood.value)}catch(e){}
    try{const body={line,mood:mood.value,count:24};if(seed)body.seed=seed;if(pool.length)body.exclude=pool.map(x=>x.text).slice(-60);
      if(h){body.syllables=Math.max(1,Math.min(40,h.target_syllables||1));if(/^[a-z][a-z'\-]{0,23}$/.test(h.end_word))body.end_word=h.end_word;
        if(h.hintWords.length)body.rhymes=h.hintWords;if(h.rhythm&&/^[A-Za-z \-]{1,160}$/.test(h.rhythm))body.rhythm=h.rhythm;
        if(h.echo&&h.echo.words&&h.echo.words.length)body.echo={word:h.echo.word,words:h.echo.words.slice(0,12)}}
      if(inp.context)body.context=inp.context.slice(-600);
      const d=await aiGet('lines',body,45000);seed++;
      if(!Array.isArray(d.lines)||!d.lines.length)throw new Error('no lines returned');
      if(Array.isArray(d.sense)&&d.sense.length===d.lines.length)d.lines.forEach((t,k)=>{const v=+d.sense[k];if(v>=0&&v<=10)senseOf.set(String(t).slice(0,200),v)});
      stats.cands+=d.lines.length;stats.model=d.model||stats.model;
      const known=new Set(pool.map(x=>x.text.toLowerCase()));const add=d.lines.filter(t=>!known.has(String(t).toLowerCase()));
      const ranked=await rank(line,[...pool.filter(x=>!shownTexts.has(x.text)).map(x=>x.text),...add].slice(0,40));
      pool=[...pool.filter(x=>shownTexts.has(x.text)),...ranked];
      const n=showNext();if(!n&&!list.children.length)throw new Error('no strong rhymes this time — try again');
      box.dataset.state='done';status()}
    catch(e){if(list.children.length){box.dataset.state='done';status(' · couldn’t get more: '+e.message)}else fallback(e.message,h)}finally{busy=false}}
  function status(extra=''){const s=[...list.querySelectorAll('.sc')].map(x=>+x.textContent),avg=s.length?Math.round(s.reduce((a,b)=>a+b,0)/s.length):0;
    st.innerHTML=`<span class="meta">Best ${list.children.length} of ${stats.cands} AI candidates · scored by the rhyme engine (avg ${avg}/100)${stats.model?' · '+esc(stats.model.split('/').pop()):''}${esc(extra)}</span>`;more.hidden=false}
  more.addEventListener('click',()=>run(true));mood.addEventListener('change',()=>{if(cur)run(false)});
  box.addEventListener('click',e=>{const c=e.target.closest('.cp,.fbw');if(c)copyText(c.dataset.copy,c.classList.contains('cp')?c:null);const i=e.target.closest('.ins');if(i&&onInsert)onInsert(i.dataset.t)});
  return{run}}
const aiLine=makeAI($('#aiLine'),{getInput:()=>({line:$('#prevLine').value})});
$('#aiGo').addEventListener('click',()=>aiLine.run(false));
function padCurrent(){const lines=pad.value.split('\n');let idx=pad.value.slice(0,pad.selectionStart).split('\n').length-1;
  if(document.activeElement!==pad&&pad.selectionStart===0)idx=lines.length-1;
  while(idx>0&&!lines[idx].trim())idx--;return{lines,idx}}
let padIdx=0;
const aiPad=makeAI($('#aiPad'),{getInput:()=>{const{lines,idx}=padCurrent();padIdx=idx;
    return{line:lines[idx]||'',context:lines.slice(Math.max(0,idx-4),idx).filter(l=>l.trim()).join('\n')}},
  onInsert:t=>{const lines=pad.value.split('\n');lines.splice(padIdx+1,0,t);padIdx++;pad.value=lines.join('\n');pad.dispatchEvent(new Event('input'))}});
$('#padAI').addEventListener('click',()=>aiPad.run(false));
