"""按区块饱和度分层，检验排序规则。"""
import urllib.request, json, pickle, time
from probe import rpc, fetch_block, analyze, spearman, VOTE

MAX_CU = 48_000_000     # Solana 区块 CU 上限（当前）

def block_cu(block):
    tot = 0
    for t in block['transactions']:
        if t['meta']:
            tot += t['meta'].get('computeUnitsConsumed') or 0
    return tot

def main():
    targets = pickle.load(open('/tmp/topval.pkl','rb'))
    wanted, seen = [], set()
    for npk, cli, ver, pct in targets:
        if cli not in seen:
            seen.add(cli); wanted.append((npk, cli, ver, pct))

    ei = rpc('getEpochInfo')['result']
    epoch_start_now = ei['absoluteSlot'] - ei['slotIndex']
    prev = epoch_start_now - 1000
    sched = {}
    for npk, cli, ver, pct in wanted:
        r = rpc('getLeaderSchedule', [prev, {"identity": npk}])
        sched[npk] = r.get('result') or {}

    estart = epoch_start_now - ei['slotsInEpoch']
    results = {}
    for npk, cli, ver, pct in wanted:
        rel = (sched.get(npk) or {}).get(npk) or []
        slots = [estart + x for x in rel]
        # 均匀取 10 个（避开前 50 个 slot，减少 epoch 边界效应）
        cand = [s for s in slots if s > estart + 1000]
        if len(cand) < 10:
            continue
        step = max(1, len(cand)//10)
        picked = cand[::step][:10]
        rows_all = []
        for s in picked:
            b = fetch_block(s)
            if not b: continue
            cu_tot = block_cu(b)
            rows = analyze(b)
            for x in rows:
                x['slot'] = s
                x['sat'] = cu_tot / MAX_CU
            rows_all.extend(rows)
        if not rows_all: continue
        # 按 slot 分组
        per = {}
        for x in rows_all: per.setdefault(x['slot'], []).append(x)
        sat_corr, unsat_corr = [], []
        for s, rows in per.items():
            rows.sort(key=lambda y: y['pos'])
            n = len(rows)
            if n < 50: continue
            sat = rows[0]['sat']
            pos = list(range(n))
            cp = spearman(pos, [r['price'] or 0 for r in rows])
            if cp is None: continue
            (sat_corr if sat > 0.7 else unsat_corr).append((cp, sat, n, s))
        results[cli] = dict(ver=ver, pct=pct, sat=sat_corr, unsat=unsat_corr,
                            nslot=len(per))
        def avg(v): return sum(x[0] for x in v)/len(v) if v else None
        print(f"\n=== {cli} {ver} ({pct:.2f}%)  采样 {len(per)} slot")
        print(f"    饱满块(>70% CU) : {len(sat_corr):2} 个  ρ均值={avg(sat_corr) if avg(sat_corr) is not None else 'n/a'}")
        print(f"    稀疏块(<70% CU) : {len(unsat_corr):2} 个  ρ均值={avg(unsat_corr) if avg(unsat_corr) is not None else 'n/a'}")
        if sat_corr:
            for cp,sat,n,s in sat_corr[:3]:
                print(f"      饱满 slot {s} 饱和={sat*100:.0f}% n={n} ρ={cp:.3f}")
    pickle.dump(results, open('/tmp/layered.pkl','wb'))
    print('\n保存 /tmp/layered.pkl')

if __name__ == '__main__':
    main()
