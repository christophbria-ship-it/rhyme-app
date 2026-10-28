"""Stress: 10k engine lookups (cold + warm) and 2k HTTP lookups at 16 concurrency against a separate
multi-worker server process; latency percentiles + memory."""
import urllib.error, sys, os, time, random, resource, statistics, subprocess, urllib.request, json
from concurrent.futures import ThreadPoolExecutor
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, ROOT)
def pct(xs, p): xs = sorted(xs); return xs[min(len(xs) - 1, int(len(xs) * p / 100))]
def rep(name, lat):
    print(f"{name}: n={len(lat)} mean={statistics.mean(lat):.2f}ms p50={pct(lat,50):.2f} p90={pct(lat,90):.2f} p95={pct(lat,95):.2f} p99={pct(lat,99):.2f} max={max(lat):.2f}")
    return pct(lat, 95), pct(lat, 99)
def rss_mb(pid):
    try: return int([l for l in open(f"/proc/{pid}/status") if l.startswith("VmRSS")][0].split()[1]) / 1024
    except Exception: return 0
def pss_mb(pid):
    try: return sum(int(l.split()[1]) for l in open(f"/proc/{pid}/smaps_rollup") if l.startswith("Pss:")) / 1024
    except Exception: return 0
rss0 = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
t = time.perf_counter(); from engine import Engine; e = Engine(); load = time.perf_counter() - t
print(f"index load: {load*1000:.0f}ms, RSS after load: {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024:.1f} MB (baseline {rss0/1024:.1f} MB)")
random.seed(42)
common = [w for w in e.words if e.info[w]["freq"] >= 3 and w.isalpha()]
qs = random.sample(common, 5000) + random.sample(e.words, 4000) + ["".join(random.choices("abcdefghijklmnopqrstuvwxyz", k=random.randint(4, 10))) for _ in range(1000)]
random.shuffle(qs)
def run(label):
    lat = []; t = time.perf_counter()
    for w in qs:
        s = time.perf_counter()
        try: e.rhymes(w, limit=300)
        except ValueError: pass
        lat.append((time.perf_counter() - s) * 1000)
    r = rep(label, lat); print(f"  throughput={len(qs)/(time.perf_counter()-t):.0f} q/s"); return r
c95, c99 = run("engine 10k lookups (cold cache)")
run("engine 10k lookups (warm cache)")
print(f"  engine RSS max={resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024:.1f} MB")
port = 18000 + random.randint(0, 999)
srv = subprocess.Popen([sys.executable, os.path.join(ROOT, "server.py"), str(port)], stdout=subprocess.PIPE, text=True)
srv.stdout.readline(); base = f"http://127.0.0.1:{port}"
for _ in range(50):
    try: urllib.request.urlopen(base + "/api/health"); break
    except Exception: time.sleep(0.1)
def hit(w):
    s = time.perf_counter(); urllib.request.urlopen(f"{base}/api/rhymes?word={w}&limit=300").read(); return (time.perf_counter() - s) * 1000
words = [w for w in qs if w.isalpha()][:2000]
t = time.perf_counter()
with ThreadPoolExecutor(16) as ex: hl = list(ex.map(hit, words))
h95, h99 = rep("HTTP 2k lookups, 16 concurrent, cold", hl); print(f"  throughput={len(words)/(time.perf_counter()-t):.0f} req/s")
with ThreadPoolExecutor(16) as ex: hl2 = list(ex.map(hit, words))
rep("HTTP 2k lookups, 16 concurrent, warm", hl2)
def hit_rel(w):
    s = time.perf_counter()
    try: urllib.request.urlopen(f"{base}/api/related?word={w}&limit=300&phrases=120").read()
    except urllib.error.HTTPError: pass
    return (time.perf_counter() - s) * 1000
rel_words = [w for w in words if e.info.get(w, {}).get("freq", 0) >= 4][:500]
t = time.perf_counter()
with ThreadPoolExecutor(16) as ex: rl = list(ex.map(hit_rel, rel_words))
r95, r99 = rep(f"HTTP {len(rel_words)} related (300 words + phrases), 16 concurrent", rl); print(f"  throughput={len(rel_words)/(time.perf_counter()-t):.0f} req/s")
kids = subprocess.run(["pgrep", "-P", str(srv.pid)], capture_output=True, text=True).stdout.split()
print(f"  server memory: master RSS={rss_mb(srv.pid):.0f} MB; workers={len(kids)}, RSS each≈{max([rss_mb(k) for k in kids] or [0]):.0f} MB, total PSS={pss_mb(srv.pid)+sum(pss_mb(k) for k in kids):.0f} MB")
srv.terminate(); srv.wait()
ok = c95 < 50 and h99 < 200 and r95 < 1000
print("STRESS", "PASS" if ok else "FAIL", f"(criteria: engine p95<50ms, HTTP cold p99<200ms, related p95<1000ms at 16 concurrent)"); sys.exit(0 if ok else 1)
