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
  const p=new URLSearchParams({word:w,sort:$('#sort').value,limit:'1000'});
  [['syllables','#syl'],['pos','#pos'],['min_freq','#freq'],['min_len','#minl'],['max_len','#maxl']].forEach(([k,s])=>{if($(s).value)p.set(k,$(s).value)});
  history.replaceState(null,'','?'+new URLSearchParams({w}));
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
  let meta=`<span class="meta">${esc(d.word)}${d.pronunciations.length?' · /'+esc(d.pronunciations[0])+'/':''}${d.guessed_from?` · not in dictionary, pronunciation guessed from “${esc(d.guessed_from)}”`:''} · ${total} results in ${d.elapsed_ms} ms</span>`;
  if(!total){status.dataset.state='empty';status.innerHTML=meta;results.innerHTML=`<div class="empty" id="empty">No rhymes found for “${esc(d.word)}”. Try loosening the filters or another word.</div>`;return}
  status.dataset.state='done';status.innerHTML=meta;
  results.innerHTML=tiers.map(([k,title,desc])=>{const items=d[k];if(!items.length)return'';
    const groups={};items.forEach(it=>(groups[it.syllables]=groups[it.syllables]||[]).push(it));
    return `<section class="tier" data-tier="${k}"><h2>${title}<span class="badge b-${k}">${d[k+'_total']}</span> <small>${desc}</small></h2>`+
      Object.keys(groups).sort((a,b)=>a-b).map(s=>`<div class="group"><h3>${s} syllable${s==1?'':'s'}</h3><div class="words">`+
        groups[s].map(it=>`<span class="w ${it.freq>=4?'common':it.freq<1?'rare':''}${it.conf&&it.conf!=='dict'?' gen':''}" data-w="${esc(it.word)}" title="${esc((it.pos.join(', ')||'—')+' · zipf '+it.freq+(it.conf&&it.conf!=='dict'?' · generated pronunciation ('+it.conf+')':''))}">${esc(it.word)}${it.matched_syllables>1?`<sup>×${it.matched_syllables}</sup>`:''}</span>`).join('')+'</div></div>').join('')+'</section>'}).join('')}
const init=new URLSearchParams(location.search).get('w');if(init){q.value=init;search()}
