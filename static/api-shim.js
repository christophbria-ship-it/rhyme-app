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
  let themes={};try{const tr=await fetch(new URL('themes.json',base));if(tr.ok)themes=await tr.json()}catch(e){}
  const tsets={};for(const k in themes)tsets[k]=new Set(themes[k].words);
  const lx=await(await fetch(new URL('lex.json',base))).json();
  const lex={stop:new Set(lx.stop),relStop:new Set(lx.rel_stop),func:new Set(lx.func),particles:new Set(lx.particles),filler:new Set(lx.filler),cliches:lx.cliches,params:lx.params};
  W={words,info,idx,suffix,sorted,assonsig,themes,tsets,lex};})();
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
  const theme=q.get("theme")||null,themeOnly=["1","true"].includes(q.get("theme_only"));if(theme&&theme!=="related"&&!W.tsets[theme])return[400,{error:"unknown theme"}];
  const tset=theme?(theme==="related"?relatedSet(w):W.tsets[theme]):null;
  const t0=performance.now(),cd=candidates(w),limit=Math.min(parseInt(q.get("limit")||"300",10),5000);
  const res={word:w,known:!cd.guessed,confidence:W.info.has(w)?W.info.get(w).conf:"guess",guessed_from:cd.guessed?cd.src:null,pronunciations:cd.prons.map(p=>p.join(" ")),perfect:[],near:[],slant:[]};
  for(const tier of["perfect","near","slant"]){const items=[];for(const[c,m,sc]of cd[tier]){const inf=W.info.get(c);
      if(syl&&syl.length&&!syl.includes(inf.syl))continue;if(pos&&!inf.pos.some(p=>pos.includes(p)))continue;
      if(minl&&inf.len<minl)continue;if(maxl&&inf.len>maxl)continue;if(minf!=null&&inf.freq<minf)continue;
      items.push({word:c,syllables:inf.syl,freq:inf.freq,pos:inf.pos,len:inf.len,matched_syllables:m,score:sc,conf:inf.conf,themed:!!tset&&tset.has(c)})}
    let its=tset&&themeOnly?items.filter(x=>x.themed):items;its.sort(SORTS[sort]);if(tset)its.sort((a,b)=>(!a.themed)-(!b.themed));
    res[tier+"_total"]=its.length;res[tier]=its.slice(0,limit)}
  res.theme=theme;res.themed_total=tset?["perfect","near","slant"].reduce((a,t)=>a+res[t].filter(x=>x.themed).length,0):0;
  res.elapsed_ms=Math.round((performance.now()-t0)*100)/100;return[200,res]}
function suggest(q){const v=(q.get("q")||"").trim().toLowerCase(),lim=parseInt(q.get("limit")||"8",10);if(!v)return[200,{suggestions:[]}];
  let lo=0,hi=W.sorted.length;while(lo<hi){const m=(lo+hi)>>1;if(W.sorted[m]<v)lo=m+1;else hi=m}
  const out=[];for(let i=lo;i<W.sorted.length&&W.sorted[i].startsWith(v)&&out.length<400;i++)out.push(W.sorted[i]);
  out.sort((a,b)=>W.info.get(b).freq-W.info.get(a).freq||a.length-b.length);return[200,{suggestions:out.slice(0,lim)}]}
// ---- songwriting: lyrics analysis & line helper (port of Engine.analyze / Engine.line_help) ----
const TOKEN=/[A-Za-z][A-Za-z']*(?:-[A-Za-z']+)*/g;
function wordInfo(raw){const w=raw.toLowerCase().replace(/^'+|'+$/g,"");const[pl,guessed]=w?prons(w):[[],true];const ph=pl[0]||[];
  let stress=ph.filter(p=>VOWELS.has(strip(p))).map(p=>/[12]$/.test(p)?"/":"u").join("");
  if(!ph.length)stress="u".repeat(Math.max(1,(w.match(/[aeiouy]+/g)||[]).length));
  return{word:raw,norm:w,syllables:stress.length,stress,known:!guessed,keys:[...new Set(pl.map(p=>keys(p).perfect))].sort(),fkeys:[...new Set(pl.map(p=>keys(p).family))].sort()}}
function analyzeText(text){if(text==null)throw new RangeError("missing text");if(text.length>10000)throw new RangeError("text too long");
  const lines=[],parts=[];let stanza=[],groups=[];const letter=i=>i<26?String.fromCharCode(65+i):"Z";
  for(const raw of text.split("\n").slice(0,400)){const toks=raw.match(TOKEN)||[];
    if(!toks.length){lines.push({text:raw,words:[],syllables:0,end:null,letter:null,match:null});if(stanza.length){parts.push(stanza.join(""));stanza=[];groups=[]}continue}
    const ws=toks.map(wordInfo),end=ws[ws.length-1],pk=new Set(end.keys),fk=new Set(end.fkeys);let let_=null,match=null;
    const inter=(a,b)=>[...a].some(x=>b.has(x));
    for(const g of groups){if(end.norm===g.end){let_=g.l;match="repeat";break}if(inter(pk,g.pk)){let_=g.l;match="perfect";break}}
    if(let_===null)for(const g of groups){if(inter(fk,g.fk)){let_=g.l;match="near";break}}
    if(let_===null){let_=letter(groups.length);groups.push({l:let_,pk,fk,end:end.norm})}
    else{const g=groups.find(g=>g.l===let_);g.pk=new Set([...g.pk,...pk]);g.fk=new Set([...g.fk,...fk])}
    stanza.push(let_);
    lines.push({text:raw,words:ws.map(({keys,fkeys,...x})=>x),syllables:ws.reduce((a,x)=>a+x.syllables,0),stress:ws.map(x=>x.stress).join(" "),end:end.norm,letter:let_,match})}
  if(stanza.length)parts.push(stanza.join(""));
  return{lines,scheme:parts.join(" "),rhyme_density:rhymeDensity(text),total_lines:lines.filter(l=>l.words.length).length,total_syllables:lines.reduce((a,l)=>a+l.syllables,0)}}
function analyze(q){if(!q.has("text"))return[400,{error:"missing 'text' parameter"}];try{return[200,analyzeText(q.get("text"))]}catch(e){if(e instanceof RangeError)return[400,{error:e.message}];throw e}}
function lineHelp(q){const prev=q.get("prev")||"";if(!prev.trim())return[400,{error:"missing 'prev' parameter"}];
  const theme=q.get("theme")||null,limit=Math.min(parseInt(q.get("limit")||"40",10),500);
  const a=analyzeText(prev.trim()+"\n"+(q.get("line")||"").trim()),p=a.lines[0],l=a.lines[1];
  if(!p.words.length)return[400,{error:"previous line has no words"}];
  const needed=p.syllables-l.syllables;
  const call=syl=>{const u=new URLSearchParams({word:p.end,min_freq:"2",limit:String(limit),sort:"score"});if(theme)u.set("theme",theme);if(syl)u.set("syllables",String(syl));return rhymes(u)};
  let[st,r]=call(needed>=1?needed:null);if(st!==200)return[st,r];let fit=needed>=1;
  if(fit&&!(r.perfect.length||r.near.length)){[st,r]=call(null);fit=false;if(st!==200)return[st,r]}
  const sug={};for(const t of["perfect","near","slant"])sug[t]=r[t].filter(x=>/[aeiouy]/.test(x.word));
  return[200,{prev:p,line:l,target_syllables:p.syllables,needed:needed>=1?needed:null,fits_count:fit,end_word:p.end,theme,echo:echo(p),suggestions:sug}]}
function echo(pl,limit=12){const ws=pl?pl.words:[];if(ws.length<2)return null;const w=ws[ws.length-2].norm;if(LX().stop.has(w)||!W.info.has(w))return null;
  const best=new Map();for(const ph of W.info.get(w).prons.slice(0,1)){const k=keys(ph).asson,sg=segments(ph);if(k.startsWith("u:"))continue;
    const ks=[...new Set([k,k.split(" ").map(x=>x==="AA"?"AO":x).join(" "),k.split(" ").map(x=>x==="AO"?"AA":x).join(" ")])].sort();
    for(const kk of ks)for(const{sig,ids}of(W.assonsig.get(kk)||new Map()).values()){const sc=consSim(sg,sig);if(sc<0.5)continue;
      for(const i of ids){const c=W.words[i],inf=W.info.get(c);if(c===w||LX().stop.has(c)||inf.freq<3.5||!inf.pos.length||c.includes("'")||stemClash(w,c))continue;
        if(sc>(best.get(c)||0))best.set(c,sc)}}}
  const out=[...best].map(([c,sc])=>[-Math.round(sc*1000)/1000,-W.info.get(c).freq,c]).sort((a,b)=>a[0]-b[0]||a[1]-b[1]||cmp(a[2],b[2]));
  return out.length?{word:w,words:out.slice(0,limit).map(x=>x[2])}:null}
function themesList(){return[200,{themes:Object.entries(W.themes).map(([id,t])=>({id,label:t.label,size:W.tsets[id].size}))}]}
// ---- shared phonetic helpers (port of engine.py: phrase_phones, vowel_match, tail_tier, coda_sim) ----
const REDUCED=new Set(["AH","IH","UH"]),eqA=(a,b)=>a.length===b.length&&a.every((x,i)=>x===b[i]);
const nv=p=>{const s=strip(p);return REDUCED.has(s)&&p.endsWith("0")?"@":s==="AO"?"AA":s};
const LX=()=>W.lex;
function phrasePhones(toks,guess){const out=[];for(let k=0;k<toks.length;k++){const t=toks[k].toLowerCase().replace(/^'+|'+$/g,"");if(!t)continue;
  let ph=W.info.has(t)?W.info.get(t).prons[0]:guess?guess(t):null;if(!ph||!ph.length)return null;
  if(LX().func.has(t)&&!(k===toks.length-1&&LX().particles.has(t)))ph=ph.map(p=>/[12]$/.test(p)?p.slice(0,-1)+"0":p);out.push(...ph)}return out}
const guessPron=t=>{const pl=prons(t)[0];return pl.length?pl[0]:null};
function vowelMatch(a,b){const va=a.filter(isV).map(nv),vb=b.filter(isV).map(nv);let n=0;while(n<va.length&&n<vb.length&&va[va.length-1-n]===vb[vb.length-1-n])n++;return n}
function tailTier(qph,cph){const qt=tail(qph),ct=tail(cph);if(!qt.length||!ct.length||!isV(qt[0])||strip(qt[0])!==strip(ct[0]))return null;
  const qv=qt.filter(isV),cv=ct.filter(isV);if(qv.length!==cv.length)return"assonant";
  const qn=qt.map(nv),cn=ct.map(nv);if(eqA(qn,cn))return"perfect";
  const fam=xs=>xs.map(x=>VOWELS.has(x)||x==="@"?x:(FAM[x]||x));if(eqA(fam(qn),fam(cn)))return"near";
  if(!eqA(qv.map(nv),cv.map(nv)))return"assonant";return consSim(segments(qt),segments(ct))>=SLANT_MIN?"slant":"assonant"}
function codaSim(a,b){if(!a.length&&!b.length)return 1;if(!a.length||!b.length)return 0.3;const[sh,lg]=a.length<=b.length?[a,b]:[b,a];const pool=[...lg];let tot=0;
  for(const x of sh){let best=0,bi=-1;pool.forEach((y,k)=>{const s=x===y?1:FAM[x]===FAM[y]?0.6:MANNER[x]===MANNER[y]?0.4:0;if(s>best){best=s;bi=k}});if(bi>=0)pool.splice(bi,1);tot+=best}
  return tot/lg.length}
function coda(ph){const t=tail(ph).map(strip);return t.length>0&&VOWELS.has(t[0])&&!t.slice(1).some(x=>VOWELS.has(x))?t.slice(1):null}
const tailVowels=ph=>tail(ph).filter(isV).length;
function svowelsPh(pl){const out=[];for(const p of pl){const v=tail(p).map(strip).filter(x=>VOWELS.has(x));if(v.length&&!out.includes(v[0]))out.push(v[0])}return out}
// ---- related rhymes (port of Engine.related; association data lazy-loaded per vowel group) ----
const pyRound=x=>{const f=Math.floor(x),d=x-f;return d>0.5?f+1:d<0.5?f:(f%2===0?f:f+1)};const DETS=new Set(["the","a","an","my","your","his","her","our","their","this","every","each"]);const TIER_Q={perfect:1,near:0.85,slant:0.7},ASSONANT_Q=0.5,SRC_W={ai:1,wikt:0.9,cn:0.5,combo:0.8};
let AV=null,AVp=null;const AQ={},AG={},AP={};
const stemClash=(w,c)=>(w.length>=4&&c.startsWith(w.slice(0,4)))||w.startsWith(c)||(c.length>=4&&w.startsWith(c.slice(0,4)));
const abase=()=>new URL('data/assoc/',document.baseURI);
const getBin=f=>realFetch(new URL(f,abase())).then(r=>{if(!r.ok)throw new Error('association data unavailable');return r.arrayBuffer()});
const getJson=f=>realFetch(new URL(f,abase())).then(r=>{if(!r.ok)throw new Error('association data unavailable');return r.json()});
const norm8=v=>{let s=0;for(let i=0;i<v.length;i++)s+=v[i]*v[i];return Math.sqrt(s)};
function load(cache,key,fn){if(!cache[key])cache[key]=fn().then(x=>cache[key]=x,e=>{delete cache[key];throw e});return cache[key]}
async function assocEnsure(w){
  if(!AV){AVp=AVp||getJson('vocab.json').then(v=>{v.index=new Map(v.words.map((x,i)=>[x,i]));v.lyricSet=new Set((v.lyric||[]).map(i=>v.words[i]));AV=v},e=>{AVp=null;throw e});await AVp}
  const i=AV.index.get(w);if(i===undefined)return false;const sh=Math.floor(i/AV.q_per_shard),jobs=[];
  jobs.push(load(AQ,sh,()=>getBin(`q-${String(sh).padStart(2,'0')}.bin`).then(b=>new DataView(b))));
  for(const v of svowelsPh(prons(w)[0])){
    if(AV.groups[v])jobs.push(load(AG,v,()=>getBin(`g-${v}.bin`).then(b=>{const n=AV.groups[v],dv=new DataView(b),out=[];
      for(let k=0;k<n;k++){const vec=new Int8Array(b,2*n+k*AV.dim,AV.dim);out.push([AV.words[dv.getUint16(2*k,true)],vec,norm8(vec)])}return out})));
    if(AV.phrase_groups[v])jobs.push(load(AP,v,()=>Promise.all([getJson(`p-${v}.json`),getBin(`p-${v}.bin`)]).then(([meta,b])=>
      meta.map(([t,ph,src],k)=>{const vec=new Int8Array(b,k*AV.dim,AV.dim);return[t,ph.split(" "),src,vec,norm8(vec)]}))))}
  await Promise.all(jobs);return true}
function aquery(w){if(!AV)return null;const i=AV.index.get(w);if(i===undefined)return null;const sh=Math.floor(i/AV.q_per_shard),dv=AQ[sh];
  if(!(dv instanceof DataView))return null;const o=(i%AV.q_per_shard)*(AV.dim+2*AV.k_gen),vec=new Int8Array(dv.buffer,o,AV.dim),gen=[];
  for(let k=0;k<AV.k_gen;k++){const g=dv.getUint16(o+AV.dim+2*k,true);if(g!==65535)gen.push(AV.words[g])}return[vec,norm8(vec),gen]}
const agroup=v=>Array.isArray(AG[v])?AG[v]:[],aphr=v=>Array.isArray(AP[v])?AP[v]:[],AGM={};
function alookup(v,w){if(!Array.isArray(AG[v]))return null;if(!AGM[v])AGM[v]=new Map(AG[v].map(([c,vec,n])=>[c,[vec,n]]));return AGM[v].get(w)||null}
function cos(a,na,b,nb){if(!na||!nb)return 0;let s=0;for(let i=0;i<a.length;i++)s+=a[i]*b[i];return s/(na*nb)}
const r4=x=>Math.round(x*1e4)/1e4,r3=x=>Math.round(x*1e3)/1e3;
function relatedCore(w,limit,minFreq,nPhr){const q=aquery(w),res={word:w,in_vocab:!!q,related:[],phrases:[],related_total:0,phrase_total:0,groups:{perfect:0,multi:0,slant:0}};
  if(!q)return res;const[qv,qn,gen]=q,P=LX().params,cd=candidates(w),tierOf=new Map();
  for(const t of["slant","near","perfect"])for(const[c,m]of cd[t])tierOf.set(c,[t,m]);
  const qph=cd.prons.length?cd.prons[0]:[],qtail=qph.length?tailVowels(qph):1,qcoda=qph.length?coda(qph):null,items=[],seen=new Set([w]);
  for(const v of svowelsPh(cd.prons))for(const[c,vec,n]of agroup(v)){
    if(seen.has(c)||stemClash(w,c)||LX().relStop.has(c)||!W.info.has(c))continue;seen.add(c);const inf=W.info.get(c);
    if(!inf.pos.length&&!AV.lyricSet.has(c))continue;if(minFreq!=null&&inf.freq<minFreq)continue;
    const a=cos(qv,qn,vec,n),[t,m]=tierOf.get(c)||["assonant",0];if(a<((t==="perfect"||t==="near")?P.A_MIN_RHYME:P.A_MIN))continue;
    const vm=qph.length?Math.max(...inf.prons.slice(0,2).map(p=>vowelMatch(qph,p))):0,ml=Math.max(m,vm);
    let qual=TIER_Q[t]||ASSONANT_Q;
    if(t==="assonant"){if(qtail>=2&&vm>=qtail)qual=0.65;const ct=Math.min(...inf.prons.slice(0,2).map(tailVowels));for(let k=0;k<Math.max(0,ct-qtail);k++)qual*=0.7;
      if(qcoda!==null){const cc=inf.prons.slice(0,2).map(coda).filter(x=>x!==null);if(cc.length)qual*=0.2+0.8*Math.max(...cc.map(x=>codaSim(qcoda,x)))}}
    if(ml>=2)qual*=1+0.15*(ml-1);
    if(AV.lyricSet.has(c))qual*=P.LYRIC_BOOST;else if(inf.freq<3.5)qual*=0.8;
    const sc=a*qual;if(sc<0.07)continue;
    const g=(qtail>=2&&ml>=2)||(qtail===1&&(t==="perfect"||t==="near")&&inf.syl>=2)?"multi":(t==="perfect"||t==="near")?"perfect":"slant";
    items.push({word:c,assoc:r3(a),tier:t,group:g,matched:ml,score:r4(sc),_s:sc,syllables:inf.syl,freq:inf.freq,pos:inf.pos,conf:inf.conf})}
  items.sort((a,b)=>b._s-a._s||cmp(a.word,b.word));
  let out=[];const pseen=new Set();
  for(const v of svowelsPh(cd.prons))for(const[text,ph,src,vec,n]of aphr(v)){if(pseen.has(text)||src==="cn")continue;const toks=text.split(" ");const last=toks[toks.length-1];
    const parts=text.replace(/-/g," ").split(/\s+/).filter(Boolean);if(parts.some(x=>x===w||stemClash(w,x)))continue;
    if(parts.some(x=>x.length===1&&x!=="a"&&x!=="i"))continue;const t=qph.length?tailTier(qph,ph):null;if(t===null)continue;
    const vm=vowelMatch(qph,ph);if(t==="assonant"&&vm<2)continue;const a=cos(qv,qn,vec,n);if(a<P.P_MIN)continue;
    let sc=a*(TIER_Q[t]||ASSONANT_Q)*(SRC_W[src]||0.7)*(1+0.15*Math.max(0,vm-qtail));if(src==="wikt"&&parts.length===2)sc*=0.6;pseen.add(text);
    out.push({text,end:last,tier:t,source:src,score:r4(sc),_s:sc})}
  out.sort((a,b)=>b._s-a._s||cmp(a.text,b.text));const perEnd=new Map();
  out=out.filter(x=>{const k=perEnd.get(x.end)||0;if(k<4){perEnd.set(x.end,k+1);return true}return false});
  for(const x of[...items,...out])delete x._s;
  res.related_total=items.length;res.related=items.slice(0,limit);res.phrase_total=out.length;res.phrases=out.slice(0,nPhr);
  for(const x of items)res.groups[x.group]++;return res}
function relatedSet(w){const r=relatedCore(w,1e9,null,0),s=new Set(r.related.map(x=>x.word));const q=r.in_vocab?aquery(w):null;
  if(q)for(const c of q[2])if(!stemClash(w,c))s.add(c);return s}
function related(q){const raw=(q.get("word")||"").trim();if(!raw)return[400,{error:"missing 'word' parameter"}];const w=raw.toLowerCase();
  if(!WORD_RE.test(w))return[400,{error:"invalid word"}];const mf=q.get("min_freq");
  return[200,relatedCore(w,Math.min(parseInt(q.get("limit")||"300",10),1000),mf?Number(mf):null,Math.min(parseInt(q.get("phrases")||"80",10),300))]}
// ---- verify AI brainstorm items (port of Engine.verify) ----
function verify(word,items){const w=String(word||"").trim().toLowerCase();if(!WORD_RE.test(w))throw new RangeError("invalid word");
  if(!Array.isArray(items)||items.length>200||!items.every(x=>typeof x==="string"&&x.length>0&&x.length<=60))throw new RangeError("invalid items");
  const cd=candidates(w),qph=cd.prons.length?cd.prons[0]:[],tierOf=new Map();for(const t of["slant","near","perfect"])for(const[c]of cd[t])tierOf.set(c,t);
  const qtail=qph.length?tailVowels(qph):1,out=[],seen=new Set();
  for(const raw of items){const text=raw.toLowerCase().replace(/[^a-z' \-]/g," ").replace(/\s+/g," ").trim();const toks=text.replace(/-/g," ").split(" ").filter(Boolean);
    if(!toks.length||seen.has(text)||toks[toks.length-1]===w)continue;seen.add(text);let t;
    if(toks.length===1&&tierOf.has(toks[0]))t=tierOf.get(toks[0]);else{const ph=phrasePhones(toks,guessPron);t=ph&&qph.length?tailTier(qph,ph):null}
    if(t===null)continue;const ph=phrasePhones(toks,guessPron)||[],vm=qph.length?vowelMatch(qph,ph):0;
    if(t==="assonant"&&vm<2&&toks.length>1)continue;const syl=ph.filter(isV).length;
    const g=toks.length>1?"phrase":(qtail>=2&&vm>=2)||(qtail===1&&(t==="perfect"||t==="near")&&syl>=2)?"multi":(t==="perfect"||t==="near")?"perfect":"slant";
    out.push({text,tier:t,group:g,matched:vm,syllables:syl})}
  return{word:w,items:out}}
// ---- AI line post-check (port of Engine.rank_lines v2) ----
const RANK_ORDER={perfect:0,near:1,slant:2,assonant:3,none:4,repeat:5},TIER_BASE={perfect:55,near:47,slant:38,assonant:26,none:0,repeat:4};
function stressedVowels(w){const[pl]=prons(w),out=new Set();for(const p of pl){const v=tail(p).map(strip).filter(x=>VOWELS.has(x));if(v.length)out.add(v[0])}return out}
const linePhones=toks=>phrasePhones(toks.slice(-4),guessPron)||[];
function internal(toks){const ks=new Map();for(let t of toks){t=t.toLowerCase().replace(/^'+|'+$/g,"");if(LX().stop.has(t)||t.length<2)continue;
  for(const k of wordInfo(t).keys.slice(0,1)){const kk=k.split("AO").join("AA");if(!ks.has(kk))ks.set(kk,new Set());ks.get(kk).add(t)}}
  let n=0;for(const v of ks.values())if(v.size>1)n+=v.size-1;return n}
function rankLines(line,lines,keep=8,sense=null){if(typeof line!=="string"||!line.trim())throw new RangeError("missing line");
  if(sense!=null&&!(Array.isArray(sense)&&Array.isArray(lines)&&sense.length===lines.length&&sense.every(x=>typeof x==="number"&&x>=0&&x<=10)))throw new RangeError("invalid sense");
  if(!Array.isArray(lines)||lines.length>40||!lines.every(x=>typeof x==="string"&&x.length<=200))throw new RangeError("invalid lines");
  if(line.length>200)throw new RangeError("line too long");
  const src=analyzeText(line.trim()).lines[0];if(!src.words.length)throw new RangeError("line has no words");
  const end=src.end,ew=wordInfo(end),tiers=new Map();
  if(WORD_RE.test(end)){const cd=candidates(end);for(const t of["slant","near","perfect"])for(const[c]of cd[t])tiers.set(c,t)}
  const sv=stressedVowels(end),stoks=line.match(TOKEN)||[],sph=linePhones(stoks),ep=prons(end)[0],tailV=ep.length?tailVowels(ep[0]):1;
  const qa=WORD_RE.test(end)?aquery(end):null,evs=qa?svowelsPh(ep):[];
  const out=lines.map((text,i)=>{const a=text.trim()?analyzeText(text.trim()).lines[0]:{words:[]};
    if(!a.words.length)return{text,end:null,tier:"none",syllables:0,syllable_diff:src.syllables,multi:0,internal:0,filler:false,cliche:false,assoc:null,sense:null,score:0,_i:i};
    const e=a.end;let t;if(e===end)t="repeat";else if(tiers.has(e))t=tiers.get(e);else if(wordInfo(e).keys.some(k=>ew.keys.includes(k)))t="perfect";
    else if([...stressedVowels(e)].some(v=>sv.has(v)))t="assonant";else t="none";
    const toks=text.match(TOKEN)||[],filler=LX().filler.has(e)&&!LX().filler.has(end);
    const vm=["perfect","near","slant","assonant"].includes(t)?vowelMatch(sph,linePhones(toks)):0;
    const parrot=toks.length>=2&&stoks.length>=2&&toks[toks.length-2].toLowerCase()===stoks[stoks.length-2].toLowerCase()&&t!=="repeat",multi=parrot?0:Math.max(0,vm-tailV);
    const inl=internal([...toks.slice(0,-1),e]),sd=Math.abs(a.syllables-src.syllables),low=" "+toks.map(x=>x.toLowerCase()).join(" ")+" ";
    const cliche=LX().cliches.some(c=>low.includes(" "+c+" "));
    let sc=TIER_BASE[t]*(filler?0.35:1);if(t!=="none"&&t!=="repeat"&&!filler)sc+=Math.min(20,10*multi);
    sc+=Math.min(12,4*inl);sc+=sd===0?13:sd===1?10:sd===2?4:-8*(sd-2);if(cliche)sc-=15;if(parrot)sc-=10;if(toks.length>=2&&DETS.has(toks[toks.length-2].toLowerCase())&&W.info.has(e)&&W.info.get(e).pos.length&&!W.info.get(e).pos.includes("n"))sc-=20;if(!filler&&LX().stop.has(e)&&!LX().particles.has(e)&&!LX().stop.has(end))sc-=15;if(toks.length<3)sc-=10;
    const ef=W.info.has(e)?W.info.get(e).freq:0;if(t!=="none"&&t!=="repeat")sc-=ef<3?12:ef<3.5?6:0;
    let coh=null;if(qa&&["perfect","near","slant","assonant"].includes(t)){for(const v of evs){const hit=alookup(v,e);if(hit){coh=cos(qa[0],qa[1],hit[0],hit[1]);break}}
      if(coh!==null)sc+=coh>=0.3?6:coh>=0.18?3:coh<0.06?-6:0}
    sc+=Math.max(0,6-Math.floor(i/4));let sn=null;if(sense!=null&&t!=="none"&&t!=="repeat"){sn=pyRound(sense[i]);sc+=Math.max(-30,Math.min(20,(sn-6)*5))}
    return{text:text.trim(),end:e,tier:t,syllables:a.syllables,syllable_diff:sd,multi,internal:inl,filler,cliche,assoc:coh===null?null:r3(coh),sense:sn,score:Math.max(0,Math.min(100,pyRound(sc))),_i:i}});
  out.sort((a,b)=>b.score-a.score||a._i-b._i);const ends=new Map(),bags=[];
  for(const x of out){if(x.end===null)continue;const bag=new Set((x.text.match(TOKEN)||[]).map(t=>t.toLowerCase()).filter(t=>!LX().stop.has(t)));let pen=0;
    if(ends.get(x.end))pen+=15*ends.get(x.end);
    if(bags.some(b=>{if(!bag.size)return false;let i=0;for(const t of bag)if(b.has(t))i++;const u=new Set([...bag,...b]).size;return i/u>=0.6}))pen+=25;
    x.score=Math.max(0,x.score-pen);ends.set(x.end,(ends.get(x.end)||0)+1);bags.push(bag)}
  out.sort((a,b)=>b.score-a.score||RANK_ORDER[a.tier]-RANK_ORDER[b.tier]||a.syllable_diff-b.syllable_diff||a._i-b._i);
  out.forEach((x,k)=>{x.keep=k<keep&&x.score>=40&&x.tier!=="none";delete x._i});
  return{line:line.trim(),end,syllables:src.syllables,lines:out}}
// ---- rhyme density (port of Engine.rhyme_density) ----
function rhymeDensity(text){const seq=[],ends=[];for(const raw of(text||"").match(TOKEN)||[]){const w=raw.toLowerCase().replace(/^'+|'+$/g,"");const pl=prons(w)[0];
    const vs=pl.length?pl[0].filter(isV).map(p=>strip(p).replace("AO","AA")):[];if(!vs.length)continue;seq.push(...vs);ends.push([seq.length-1,w])}
  if(ends.length<2)return 0;let tot=0;
  for(let k=1;k<ends.length;k++){const[pi,wi]=ends[k];let best=0;for(let j=Math.max(0,k-15);j<k;j++){const[pj,wj]=ends[j];if(wj===wi)continue;let n=0;
      while(pj-n>=0&&pi-n>pj&&seq[pi-n]===seq[pj-n])n++;if(n>best)best=n}tot+=best}
  return Math.round(tot/(ends.length-1)*1000)/1000}
const realFetch=window.fetch.bind(window);
window.fetch=async(input,init)=>{const url=new URL(typeof input==="string"?input:input.url,location.href);
  const p=url.pathname.replace(/.*\/api\//,"/api/");if(!url.pathname.includes("/api/"))return realFetch(input,init);
  await ready;
  if(p==="/api/related"||((p==="/api/rhymes"||p==="/api/line")&&url.searchParams.get("theme")==="related")){
    const tk=p==="/api/line"?((url.searchParams.get("prev")||"").trim().match(TOKEN)||[]):[];
    const ww=p==="/api/line"?(tk.length?tk[tk.length-1].toLowerCase().replace(/^'+|'+$/g,""):""):(url.searchParams.get("word")||"").trim().toLowerCase();
    try{if(WORD_RE.test(ww))await assocEnsure(ww)}catch(e){if(p==="/api/related")return new Response(JSON.stringify({error:navigator.onLine===false?"offline — association data not cached yet":e.message}),{status:503,headers:{"Content-Type":"application/json"}});
      url.searchParams.delete("theme");url.searchParams.delete("theme_only")}}  // rhymes still work without association data
  if(init&&init.signal&&init.signal.aborted)throw new DOMException("aborted","AbortError");
  let r;try{
    if(init&&init.method==="POST"){let b;try{b=JSON.parse(init.body||"{}")}catch(e){b=null}
      if(p==="/api/rank_lines"&&b&&typeof b.line==="string"){const tk=b.line.match(TOKEN)||[];const ew=tk.length?tk[tk.length-1].toLowerCase().replace(/^'+|'+$/g,""):"";
        if(WORD_RE.test(ew))try{await assocEnsure(ew)}catch(e){}}
      if(p.startsWith("/api/ai/"))return realFetch(input,init);
      const guard=f=>{try{return[200,f()]}catch(e){if(e instanceof RangeError)return[400,{error:e.message}];throw e}};
      if(p==="/api/verify")r=b&&typeof b==="object"?guard(()=>verify(b.word,b.items)):[400,{error:"body must be an object"}];else
      if(p==="/api/rank_lines")r=b&&typeof b==="object"?(()=>{try{return[200,rankLines(b.line,b.lines,8,b.sense==null?null:b.sense)]}catch(e){if(e instanceof RangeError)return[400,{error:e.message}];throw e}})():[400,{error:"body must be an object"}];
      else if(p!=="/api/analyze")r=[404,{error:"not found"}];
      else r=b&&typeof b.text==="string"?(()=>{try{return[200,analyzeText(b.text)]}catch(e){return[400,{error:e.message}]}})():[400,{error:"missing 'text'"}]}
    else r=p==="/api/related"?related(url.searchParams):p==="/api/themes"?themesList():p==="/api/analyze"?analyze(url.searchParams):p==="/api/line"?lineHelp(url.searchParams):p==="/api/rhymes"?rhymes(url.searchParams):p==="/api/suggest"?suggest(url.searchParams):p==="/api/health"?[200,{ok:true,words:W.words.length}]:[404,{error:"not found"}]}
  catch(e){r=[500,{error:"internal error"}]}
  return new Response(JSON.stringify(r[1]),{status:r[0],headers:{"Content-Type":"application/json"}})};
window.RHYME_READY=ready;
})();
