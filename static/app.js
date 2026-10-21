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
  results.innerHTML=tiers.map(([k,title,desc])=>{const items=d[k];if(!items.length)return'';
    const groups={};items.forEach(it=>(groups[it.syllables]=groups[it.syllables]||[]).push(it));
    return `<section class="tier" data-tier="${k}"><h2>${title}<span class="badge b-${k}">${d[k+'_total']}</span> <small>${desc}</small></h2>`+
      Object.keys(groups).sort((a,b)=>a-b).map(s=>`<div class="group"><h3>${s} syllable${s==1?'':'s'}</h3><div class="words">`+
        groups[s].map(it=>`<span class="w ${it.freq>=4?'common':it.freq<1?'rare':''}${it.conf&&it.conf!=='dict'?' gen':''}${it.themed?' on':''}" data-w="${esc(it.word)}" title="${esc((it.pos.join(', ')||'—')+' · zipf '+it.freq+(it.conf&&it.conf!=='dict'?' · generated pronunciation ('+it.conf+')':'')+(it.themed?' · on theme':''))}">${esc(it.word)}${it.matched_syllables>1?`<sup>×${it.matched_syllables}</sup>`:''}</span>`).join('')+'</div></div>').join('')+'</section>'}).join('')}
const init=new URLSearchParams(location.search).get('w');if(init){q.value=init;setTimeout(search)}

// ---------------- tabs ----------------
const TABS=['rhymes','line','pad'];
function showTab(t){if(!TABS.includes(t))t='rhymes';TABS.forEach(x=>{$('#tab-'+x).hidden=x!==t;$('#t-'+x).setAttribute('aria-selected',x===t)});
  document.body.dataset.tab=t;if(t==='pad')padAnalyze()}
addEventListener('hashchange',()=>showTab(location.hash.slice(1)));
// ---------------- themed rhymes toggle ----------------
const tToggle=$('#themeToggle'),tSel=$('#theme'),tOnly=$('#themeOnly');let themesLoaded=false;
async function loadThemes(){if(themesLoaded)return;try{const r=await fetch('api/themes');const d=await r.json();
  tSel.innerHTML='<option value="">Choose a theme…</option>'+d.themes.map(t=>`<option value="${esc(t.id)}">${esc(t.label)}</option>`).join('');themesLoaded=true;
  const saved=localStorage.getItem('rhymer-theme');if(saved&&d.themes.some(t=>t.id===saved))tSel.value=saved}catch(e){}}
function themeParams(p){if(tToggle.checked&&tSel.value){p.set('theme',tSel.value);if(tOnly.checked)p.set('theme_only','1')}return p}
function themeChanged(){tToggle.setAttribute('aria-checked',tToggle.checked);tSel.disabled=tOnly.disabled=!tToggle.checked;
  document.body.classList.toggle('themed',tToggle.checked&&!!tSel.value);localStorage.setItem('rhymer-theme-on',tToggle.checked?'1':'');
  if(tSel.value)localStorage.setItem('rhymer-theme',tSel.value);rerun()}
function rerun(){const t=document.body.dataset.tab;if(t==='line'){if($('#prevLine').value.trim())lineHelp()}else if(q.value.trim())search()}
tToggle.addEventListener('change',async()=>{if(tToggle.checked){await loadThemes();if(!tSel.value)tSel.value=tSel.options[1]?tSel.options[1].value:''}themeChanged()});
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
    $('#padStats').innerHTML=d.total_lines?`<span id="scheme">Scheme <b>${esc(d.scheme)}</b></span> · ${d.total_lines} line${d.total_lines==1?'':'s'} · ${words} words · ${d.total_syllables} syllables`:'Your verse analysis will appear here.';
  }catch(e){if(seq===padSeq)$('#padStats').innerHTML=`<div class="err" role="alert">Couldn't analyse lyrics: ${esc(e.message)}</div>`}}
padLines.addEventListener('click',e=>{const b=e.target.closest('.endw');if(!b)return;q.value=b.dataset.w;location.hash='#rhymes';search()});
$('#padClear').addEventListener('click',()=>{if(!pad.value||confirm('Clear the lyrics pad?')){pad.value='';localStorage.removeItem('rhymer-pad');padAnalyze()}});
$('#padCopy').addEventListener('click',async()=>{try{await navigator.clipboard.writeText(pad.value);$('#padSaved').textContent='Copied'}catch(e){pad.select();document.execCommand('copy');$('#padSaved').textContent='Copied'}});
$('#padDownload').addEventListener('click',()=>{const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([pad.value],{type:'text/plain'}));a.download='lyrics.txt';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)});
// restore theme toggle + initial tab
(async()=>{if(localStorage.getItem('rhymer-theme-on')){tToggle.checked=true;await loadThemes();tToggle.setAttribute('aria-checked','true');tSel.disabled=tOnly.disabled=false;document.body.classList.toggle('themed',!!tSel.value)}
  showTab(location.hash.slice(1))})();
