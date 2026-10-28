"""抓取指定验证者出的块，分析交易排序规则。"""
import urllib.request, json, sys, time, pickle
M = 'https://solana-rpc.publicnode.com'

def rpc(method, params=None, timeout=60):
    body = json.dumps({"jsonrpc":"2.0","id":1,"method":method,"params":params or []}).encode()
    req = urllib.request.Request(M, data=body,
        headers={'Content-Type':'application/json','User-Agent':'Mozilla/5.0'})
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    return json.loads(op.open(req, timeout=timeout).read().decode())

VOTE = 'Vote111111111111111111111111111111111111111'
BASE_FEE = 5000

def fetch_block(slot):
    for attempt in range(3):
        try:
            r = rpc('getBlock', [slot, {"encoding":"json","transactionDetails":"full",
                                        "rewards":False,"maxSupportedTransactionVersion":1}])
            if 'error' in r:
                if 'skipped' in str(r['error']).lower() or 'not available' in str(r['error']).lower():
                    return None
                time.sleep(1); continue
            return r['result']
        except Exception:
            time.sleep(1)
    return None

def analyze(block):
    """返回按块内位置排序的交易度量表。"""
    out = []
    for pos, t in enumerate(block['transactions']):
        msg = t['transaction']['message']
        ak = [a if isinstance(a, str) else a.get('pubkey') for a in msg['accountKeys']]
        if VOTE in ak:
            continue
        meta = t['meta']
        fee = meta.get('fee', 0)
        cu = meta.get('computeUnitsConsumed') or 0
        nsign = len(t['transaction']['signatures'])
        prio_fee = max(0, fee - BASE_FEE * nsign)
        out.append({
            'pos': pos,
            'slot': None,
            'fee': fee,
            'prio_fee': prio_fee,
            'cu': cu,
            'cost_units': meta.get('costUnits'),
            'nsign': nsign,
            'price': (prio_fee / cu) if cu else None,   # lamports per CU
            'err': meta.get('err') is not None,
        })
    return out

def spearman(xs, ys):
    """无 scipy 的 Spearman 秩相关。"""
    n = len(xs)
    if n < 3: return None
    def ranks(v):
        idx = sorted(range(n), key=lambda i: v[i])
        r = [0.0]*n
        i = 0
        while i < n:
            j = i
            while j+1 < n and v[idx[j+1]] == v[idx[i]]: j += 1
            avg = (i+j)/2 + 1
            for k in range(i, j+1): r[idx[k]] = avg
            i = j+1
        return r
    rx, ry = ranks(xs), ranks(ys)
    mx = sum(rx)/n; my = sum(ry)/n
    num = sum((rx[i]-mx)*(ry[i]-my) for i in range(n))
    dx = sum((rx[i]-mx)**2 for i in range(n))**0.5
    dy = sum((ry[i]-my)**2 for i in range(n))**0.5
    if dx == 0 or dy == 0: return None
    return num/(dx*dy)

if __name__ == '__main__':
    targets = pickle.load(open('/tmp/topval.pkl','rb'))
    # 取 6 个跨客户端的代表
    wanted = []
    seen_clients = set()
    for npk, cli, ver, pct in targets:
        if cli not in seen_clients:
            seen_clients.add(cli)
            wanted.append((npk, cli, ver, pct))
    print('目标验证者:')
    for w in wanted: print('  %-18s %-12s %.2f%%' % (w[1], w[2], w[3]))

    epoch_info = rpc('getEpochInfo')['result']
    epoch_start = epoch_info['absoluteSlot'] - epoch_info['slotIndex']
    # 用上一 epoch 的 leader schedule（覆盖完整 432000 slot）
    prev_probe_slot = epoch_start - 1000
    sched = {}
    for _w in wanted:
        _r = rpc('getLeaderSchedule', [prev_probe_slot, {"identity": _w[0]}])
        sched.update(_r.get('result') or {})
    epoch_start = epoch_start - epoch_info['slotsInEpoch']
    print('\n当前 epoch', epoch_info['epoch'], 'abs', epoch_info['absoluteSlot'],
          '| 分析 epoch', epoch_info['epoch']-1, '起始 slot', epoch_start)

    result = {}
    cur_slot = epoch_info['absoluteSlot']
    for npk, cli, ver, pct in wanted:
        rel = sched.get(npk) or []
        slots = [epoch_start + r for r in rel]   # 相对索引转绝对 slot
        done = [s for s in slots if s < cur_slot - 200]
        if not done:
            print(f'\n{cli}: 本 epoch 无已确认 slot')
            continue
        picked = done[-4:]
        print(f'\n=== {cli} {ver} ({pct:.2f}%) 采样 slot {picked}')
        all_tx = []
        for s in picked:
            b = fetch_block(s)
            if not b: 
                print(f'   slot {s}: 无数据'); continue
            rows = analyze(b)
            for r in rows: r['slot'] = s
            all_tx.extend(rows)
            print(f'   slot {s}: {len(rows)} 笔非投票交易')
        if not all_tx: continue
        # 每个 slot 内部算相关
        per_slot = {}
        for r in all_tx: per_slot.setdefault(r['slot'], []).append(r)
        corr = []
        for s, rows in per_slot.items():
            rows.sort(key=lambda x: x['pos'])
            pos = list(range(len(rows)))
            c_price = spearman(pos, [r['price'] or 0 for r in rows])
            c_fee   = spearman(pos, [r['prio_fee'] for r in rows])
            c_cu    = spearman(pos, [r['cu'] for r in rows])
            corr.append((s, c_price, c_fee, c_cu, len(rows)))
        result[cli] = {'ver': ver, 'pct': pct, 'corr': corr, 'n': len(all_tx)}
        for s, cp, cf, cc, n in corr:
            print(f'   slot {s} n={n:3}  ρ(位置,价格)={cp if cp is None else round(cp,3)}'
                  f'  ρ(位置,优先费)={cf if cf is None else round(cf,3)}'
                  f'  ρ(位置,CU)={cc if cc is None else round(cc,3)}')
    pickle.dump(result, open('/tmp/order_result.pkl','wb'))
    print('\n已保存 /tmp/order_result.pkl')
