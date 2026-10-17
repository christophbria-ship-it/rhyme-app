// In-browser port of engine.py: answers /api/* fetches locally so the app runs as a static site.
(()=>{
const VOWELS=new Set("AA AE AH AO AW AY EH ER EY IH IY OW OY UH UW".split(" ")),FAM={},MANNER={};
Object.entries({STOP_V:"B D G",STOP_U:"P T K",FRIC_V:"V DH Z ZH",FRIC_U:"F TH S SH HH",NAS:"M N NG",LIQ:"L R",AFF:"CH JH",GLD:"W Y"}).forEach(([g,ps])=>ps.split(" ").forEach(p=>FAM[p]=g));
Object.entries({stop:"B D G P T K",fric:"V DH Z ZH F TH S SH HH",aff:"CH JH",nas:"M N NG",liq:"L R",gld:"W Y"}).forEach(([g,ps])=>ps.split(" ").forEach(p=>MANNER[p]=g));
const strip=p=>p.replace(/\d/g,""),isV=p=>VOWELS.has(strip(p)),SLANT_MIN=0.6,WORD_RE=/^[a-z][a-z'.\-]{0,44}$/;
function tail(ph){for(const m of["1","2"]){let i=-1;ph.forEach((p,j)=>{if(p.endsWith(m))i=j});if(i>=0)return ph.slice(i)}
  let i=-1;ph.forEach((p,j)=>{if(isV(p))i=j});return i>=0?ph.slice(i):ph}
function keys(ph){const raw=tail(ph),t=raw.map(strip),stressed=raw.some(p=>/[12]$/.test(p));
  return{perfect:t.join(" "),family:t.map(p=>VOWELS.has(p)?p:(FAM[p]||p)).join(" "),
    asson:(stressed?"":"u:")+t.filter(p=>VOWELS.has(p)).join(" "),conson:t.map(p=>VOWELS.has(p)?"*":p).join(" ")}}
function segments(ph){const s=[];for(const p of tail(ph).map(strip)){if(VOWELS.has(p))s.push([]);else if(s.length)s[s.length-1].push(p)}return s}
function consSim(a,b){if(a.length!==b.length||!a.length)return 0;let tot=0;
  for(let i=0;i<a.length;i++){const x=a[i],y=b[i];let sc;
    if(!x.length&&!y.length)sc=1;else if(!x.length||!y.length)sc=0;
    else{const p=x[x.length-1],q=y[y.length-1];sc=p===q?1:FAM[p]===FAM[q]?0.8:MANNER[p]===MANNER[q]?0.6:0.2;if(x.length!==y.length)sc*=0.8}
    tot+=sc}return tot/a.length}
function matched(a,b){a=a.map(strip);b=b.map(strip);let n=0;for(let i=1;i<=Math.min(a.length,b.length);i++){if(a[a.length-i]!==b[b.length-i])break;if(VOWELS.has(a[a.length-i]))n++}return n}
let W=null;const ready=(async()=>{
  const base=new URL('data/',document.baseURI),man=await(await fetch(new URL('manifest.json',base))).json();
  const parts=await Promise.all([...Array(man.shards).keys()].map(async i=>{const r=await fetch(new URL(`words-${i}.json`,base));if(!r.ok)throw new Error('data load failed');return r.json()}));
  const rows=parts.flat(),info=new Map(),idx={perfect:new Map(),family:new Map(),asson:new Map(),conson:new Map()},words=[],assonsig=new Map();
  rows.forEach(([w,syl,freq,pos,prons,cf],i)=>{words.push(w);const pl=prons.split("|").map(p=>p.split(" "));
    info.set(w,{syl,freq,pos:pos?pos.split(","):[],len:w.length,prons:pl,segs:null,conf:["dict","derived","g2p"][cf||0]});const seen=new Set();
    for(const ph of pl){const k=keys(ph);for(const n in idx){const sk=n+"\u0000"+k[n];if(seen.has(sk))continue;seen.add(sk);
      let l=idx[n].get(k[n]);if(!l)idx[n].set(k[n],l=[]);l.push(i)}
      const sig=segments(ph),ss=k.asson+"\u0001"+JSON.stringify(sig);if(!seen.has(ss)){seen.add(ss);
        let m=assonsig.get(k.asson);if(!m)assonsig.set(k.asson,m=new Map());const sk=JSON.stringify(sig);
        let e=m.get(sk);if(!e)m.set(sk,e={sig,ids:[]});e.ids.push(i)}}});
  const suffix=new Map();[...words].sort((a,b)=>info.get(b).freq-info.get(a).freq).forEach(w=>{if(!/^[a-z]+$/.test(w)||info.get(w).conf!=="dict")return;
    for(let n=2;n<=Math.min(w.length,6);n++){const s=w.slice(-n);if(!suffix.has(s))suffix.set(s,w)}});
  const sorted=[...words].sort((a,b)=>a<b?-1:a>b?1:0);
  W={words,info,idx,suffix,sorted,assonsig};})();
const segsOf=c=>{const i=W.info.get(c);return i.segs||(i.segs=i.prons.map(segments))};
function prons(w){if(W.info.has(w))return[W.info.get(w).prons,false,w];
  for(let n=Math.min(w.length,6);n>1;n--){const s=W.suffix.get(w.slice(-n));if(s)return[W.info.get(s).prons,true,s]}return[[],true,null]}
const cache=new Map();
function candidates(w){if(cache.has(w))return cache.get(w);const[pl,guessed,src]=prons(w);
  const out={prons:pl,guessed,src,perfect:[],near:[],slant:[]},seen=new Set([w]),ks=pl.map(keys),sg=pl.map(segments);
  for(const[tier,name]of[["perfect","perfect"],["near","family"]])pl.forEach((ph,j)=>{for(const i of W.idx[name].get(ks[j][name])||[]){const c=W.words[i];
    if(seen.has(c))continue;seen.add(c);const m=tier==="perfect"?Math.max(...W.info.get(c).prons.map(q=>matched(ph,q))):0;out[tier].push([c,m,1])}});
  const slant=new Map();pl.forEach((ph,j)=>{const k=ks[j];if(k.asson.startsWith("u:"))return;
    for(const{sig,ids}of(W.assonsig.get(k.asson)||new Map()).values()){const sc=consSim(sg[j],sig);if(sc<SLANT_MIN)continue;
      for(const i of ids){const c=W.words[i];if(!seen.has(c)&&sc>(slant.get(c)||0))slant.set(c,sc)}}
    if(sg[j].reduce((a,x)=>a+x.length,0)>=2)for(const i of W.idx.conson.get(k.conson)||[]){const c=W.words[i];if(!seen.has(c)&&!slant.has(c))slant.set(c,SLANT_MIN)}});
  out.slant=[...slant].map(([c,sc])=>[c,0,Math.round(sc*1000)/1000]);if(cache.size>2000)cache.clear();cache.set(w,out);return out}
const cmp=(a,b)=>a<b?-1:a>b?1:0;
const SORTS={score:(a,b)=>(a.conf!=="dict")-(b.conf!=="dict")||b.matched_syllables-a.matched_syllables||b.score-a.score||b.freq-a.freq||cmp(a.word,b.word),
  freq:(a,b)=>b.freq-a.freq||cmp(a.word,b.word),alpha:(a,b)=>cmp(a.word,b.word),length:(a,b)=>a.len-b.len||cmp(a.word,b.word),
  syllables:(a,b)=>a.syllables-b.syllables||b.freq-a.freq};
function rhymes(q){const raw=(q.get("word")||"").trim();if(!raw)return[400,{error:"missing 'word' parameter"}];
  const sort=q.get("sort")||"score";if(!SORTS[sort])return[400,{error:"invalid sort"}];
  const pos=q.get("pos")?q.get("pos").split(","):null;if(pos&&!pos.every(p=>["n","v","adj","adv"].includes(p)))return[400,{error:"invalid pos"}];
  const num=k=>{const v=q.get(k);if(!v)return null;const n=Number(v);if(isNaN(n))throw 0;return n};
  let syl,minl,maxl,minf;try{syl=q.get("syllables")?q.get("syllables").split(",").filter(x=>x.trim()).map(x=>{const n=parseInt(x,10);if(isNaN(n)||!/^\s*-?\d+\s*$/.test(x))throw 0;return n}):null;
    minl=num("min_len");maxl=num("max_len");minf=num("min_freq")}catch(e){return[400,{error:"invalid number"}]}
  const w=raw.toLowerCase();if(!WORD_RE.test(w))return[400,{error:"invalid word"}];
  const t0=performance.now(),cd=candidates(w),limit=Math.min(parseInt(q.get("limit")||"300",10),5000);
  const res={word:w,known:!cd.guessed,confidence:W.info.has(w)?W.info.get(w).conf:"guess",guessed_from:cd.guessed?cd.src:null,pronunciations:cd.prons.map(p=>p.join(" ")),perfect:[],near:[],slant:[]};
  for(const tier of["perfect","near","slant"]){const items=[];for(const[c,m,sc]of cd[tier]){const inf=W.info.get(c);
      if(syl&&syl.length&&!syl.includes(inf.syl))continue;if(pos&&!inf.pos.some(p=>pos.includes(p)))continue;
      if(minl&&inf.len<minl)continue;if(maxl&&inf.len>maxl)continue;if(minf!=null&&inf.freq<minf)continue;
      items.push({word:c,syllables:inf.syl,freq:inf.freq,pos:inf.pos,len:inf.len,matched_syllables:m,score:sc,conf:inf.conf})}
    items.sort(SORTS[sort]);res[tier+"_total"]=items.length;res[tier]=items.slice(0,limit)}
  res.elapsed_ms=Math.round((performance.now()-t0)*100)/100;return[200,res]}
function suggest(q){const v=(q.get("q")||"").trim().toLowerCase(),lim=parseInt(q.get("limit")||"8",10);if(!v)return[200,{suggestions:[]}];
  let lo=0,hi=W.sorted.length;while(lo<hi){const m=(lo+hi)>>1;if(W.sorted[m]<v)lo=m+1;else hi=m}
  const out=[];for(let i=lo;i<W.sorted.length&&W.sorted[i].startsWith(v)&&out.length<400;i++)out.push(W.sorted[i]);
  out.sort((a,b)=>W.info.get(b).freq-W.info.get(a).freq||a.length-b.length);return[200,{suggestions:out.slice(0,lim)}]}
const realFetch=window.fetch.bind(window);
window.fetch=async(input,init)=>{const url=new URL(typeof input==="string"?input:input.url,location.href);
  const p=url.pathname.replace(/.*\/api\//,"/api/");if(!url.pathname.includes("/api/"))return realFetch(input,init);
  await ready;if(init&&init.signal&&init.signal.aborted)throw new DOMException("aborted","AbortError");
  let r;try{r=p==="/api/rhymes"?rhymes(url.searchParams):p==="/api/suggest"?suggest(url.searchParams):p==="/api/health"?[200,{ok:true,words:W.words.length}]:[404,{error:"not found"}]}
  catch(e){r=[500,{error:"internal error"}]}
  return new Response(JSON.stringify(r[1]),{status:r[0],headers:{"Content-Type":"application/json"}})};
window.RHYME_READY=ready;
})();
