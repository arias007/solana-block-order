"""验证假设：区块顺序 = 并行执行完成顺序，不是优先费顺序。"""
import pickle, statistics
from probe import rpc, fetch_block, analyze, spearman

def main():
    targets = pickle.load(open('/tmp/topval.pkl','rb'))
    npk, cli, ver, pct = targets[0]     # HarmonicAgave 最大质押
    ei = rpc('getEpochInfo')['result']
    estart_now = ei['absoluteSlot'] - ei['slotIndex']
    r = rpc('getLeaderSchedule', [estart_now-1000, {"identity": npk}])
    rel = (r.get('result') or {}).get(npk) or []
    estart = estart_now - ei['slotsInEpoch']
    slots = [estart+x for x in rel if estart+x > estart+2000]
    step = max(1, len(slots)//12)
    picked = slots[::step][:12]

    print(f'{cli} {ver} — {len(picked)} 个 slot\n')
    print(f"{'slot':>12} {'n':>5} {'ρ_cu':>7} {'ρ_pfee':>8} {'前25%均CU':>10} {'后25%均CU':>10} {'倍数':>6}")
    rows_cu=[]
    for s in picked:
        b = fetch_block(s)
        if not b: continue
        rows = analyze(b); rows.sort(key=lambda x:x['pos'])
        n=len(rows)
        if n<100: continue
        pos=list(range(n))
        rcu=spearman(pos,[x['cu'] for x in rows])
        rpf=spearman(pos,[x['prio_fee'] for x in rows])
        q=n//4
        head=statistics.mean([x['cu'] for x in rows[:q]])
        tail=statistics.mean([x['cu'] for x in rows[-q:]])
        rows_cu.append((rcu, head, tail))
        print(f"{s:>12} {n:>5} {rcu:>+7.3f} {rpf:>+8.3f} {head:>10.0f} {tail:>10.0f} {tail/head:>6.2f}x")
    if rows_cu:
        print(f"\nρ_cu 平均 {statistics.mean(x[0] for x in rows_cu):+.3f}")
        print(f"块尾/块头 CU 倍数 平均 {statistics.mean(x[2]/x[1] for x in rows_cu):.2f}x")

    # 再测：同一 slot 内，冲突交易（共享可写账户）是否严格保序
    print('\n--- 冲突交易是否保序 ---')
    b = fetch_block(picked[0])
    rows = analyze(b)
    # 用 preBalances 变化的账户做代理
    import collections
    seq = collections.defaultdict(list)
    for i,t in enumerate(b['transactions']):
        ak=[a if isinstance(a,str) else a.get('pubkey') for a in t['transaction']['message']['accountKeys']]
        meta=t['meta']
        pre,post=meta.get('preBalances') or [],meta.get('postBalances') or []
        for j,a in enumerate(ak[:len(pre)]):
            if pre[j]!=post[j]: seq[a].append(i)
    multi={k:v for k,v in seq.items() if 1 < len(v) <= 40}
    print(f'被 2-40 笔交易连续改动的账户数: {len(multi)}')
    for k,v in list(multi.items())[:5]:
        gaps=[v[i+1]-v[i] for i in range(len(v)-1)]
        print(f'  {k[:12]}… 出现 {len(v):2} 次, 间隔 {gaps[:8]}')

if __name__=='__main__': main()
