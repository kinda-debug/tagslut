#!/usr/bin/env python3
import os, csv, collections, re
mapfile='artifacts/reports/finalize_map_recovery.csv'
out_dir='artifacts/reports/missing_by_volume'
os.makedirs(out_dir, exist_ok=True)
def top_vol(path):
    m=re.match(r'^(/Volumes/[^/]+)', path)
    if m: return m.group(1)
    return 'OTHER'
counts=collections.Counter()
groups={}
malformed=[]
if not os.path.exists(mapfile):
    print('Map file not found:', mapfile)
    raise SystemExit(1)
with open(mapfile, newline='') as f:
    r=csv.reader(f)
    for row in r:
        if not row: continue
        src=row[0]
        if not os.path.exists(src):
            tv=top_vol(src)
            counts[tv]+=1
            groups.setdefault(tv, []).append(row)
            rest = src[len(tv):]
            if '/Volumes/' in rest:
                malformed.append(src)
with open(os.path.join(out_dir,'summary.txt'),'w') as s:
    for k,v in counts.most_common():
        s.write(f"{k}\t{v}\n")
for k, rows in groups.items():
    name = k.strip('/').replace('/','_') if k!='OTHER' else 'OTHER'
    path = os.path.join(out_dir, f'missing_{name}.csv')
    with open(path, 'w', newline='') as g:
        w=csv.writer(g)
        w.writerows(rows)
with open(os.path.join(out_dir,'malformed_paths.txt'),'w') as m:
    m.write('\n'.join(malformed))
print('Wrote', len(groups), 'per-volume files to', out_dir)
print('Top volumes:')
for k,v in counts.most_common(20):
    print(k, v)
print('Malformed path samples:', len(malformed))
if malformed:
    print('\nFirst 20 malformed samples:')
    for p in malformed[:20]:
        print(p)
