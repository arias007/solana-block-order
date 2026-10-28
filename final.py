"""跨验证者、跨 slot 的排序规则测量（只用公开区块数据）。"""
import pickle, statistics, json
from probe import rpc, fetch_block, analyze, spearman

MAX_CU = 48_000_000

def block_sat(b):
    return sum((t['meta'] or {}).get('computeUnitsConsumed') or 0 for t in b['transactions']) / MAX_CU

def quartile_positions(rows, key):
    """把交易按 key 分四档，看每档的平均相对位置。0=块头 1=块尾"""
    n = len(rows)
    vals = [(i, r) for i, r in enumerate(rows)]
    vals.sort(key=lambda x: (x[1][key] or 0))
    q = n // 4
    out = []
    for k in range(4):
        seg = vals[k*q:(k+1)*q] if k < 3 else vals[3*q:]
        if not seg: out.append(None); continue
        out.append(sum(i/(n-1) for i, _ in seg) / len(seg))
    return out

def main():
    targets = pickle.load(open('/tmp/topval.pkl','rb'))
    wanted, seen = [], set()
    for npk, cli, ver, pct in targets:
        if cli not in seen:
            seen.add(cli); wanted.append((npk, cli, ver, pct))

    ei = rpc('getEpochInfo')['result']
    estart_now = ei['absoluteSlot'] - ei['slotIndex']
    prev = estart_now - 1000
    estart = estart_now - ei['slotsInEpoch']

    ALL = {}
    for npk, cli, ver, pct in wanted:
        r = rpc('getLeaderSchedule', [prev, {"identity": npk}])
        rel = (r.get('result') or {}).get(npk) or []
        slots = [estart + x for x in rel if estart + x > estart + 2000]
        if len(slots) < 20: print(f'{cli}: slot 不足'); continue
        step = max(1, len(slots)//20)
        picked = slots[::step][:20]

        per_slot = []
        for s in picked:
            b = fetch_block(s)
            if not b: continue
            rows = analyze(b)
            if len(rows) < 80: continue
            rows.sort(key=lambda x: x['pos'])
            n = len(rows)
            pos = list(range(n))
            rec = dict(
                slot=s, n=n, sat=block_sat(b),
                rho_price=spearman(pos, [x['price'] or 0 for x in rows]),
                rho_pfee =spearman(pos, [x['prio_fee'] for x in rows]),
                rho_cu   =spearman(pos, [x['cu'] for x in rows]),
                q_pfee   =quartile_positions(rows, 'prio_fee'),
                q_price  =quartile_positions(rows, 'price'),
                zero_pct =sum(1 for x in rows if x['prio_fee']==0)/n,
            )
            per_slot.append(rec)
        ALL[cli] = dict(ver=ver, pct=pct, slots=per_slot)
        print(f"\n=== {cli} {ver}  ({pct:.2f}% stake)  有效 slot {len(per_slot)}")
        for k in ('rho_price','rho_pfee','rho_cu'):
            v=[r[k] for r in per_slot if r[k] is not None]
            if not v: continue
            m=statistics.mean(v); sd=statistics.pstdev(v) if len(v)>1 else 0
            se=sd/(len(v)**0.5) if len(v)>1 else 0
            sig='*' if abs(m)>2*se and se>0 else ' '
            print(f"    {k:10} 均值={m:+.3f}  SD={sd:.3f}  SE={se:.3f} {sig}")
        z=statistics.mean([r['zero_pct'] for r in per_slot])
        print(f"    优先费=0 占比 {z*100:.0f}%")
        qs=[r['q_price'] for r in per_slot if r['q_price'] and None not in r['q_price']]
        if qs:
            avg=[statistics.mean(x[i] for x in qs) for i in range(4)]
            print(f"    按价格分档的平均位置（0=块头,1=块尾）: " +
                  ' '.join(f'{v:.2f}' for v in avg))
    pickle.dump(ALL, open('/tmp/final_result.pkl','wb'))
    print('\n-> /tmp/final_result.pkl')

if __name__=='__main__':
    main()
