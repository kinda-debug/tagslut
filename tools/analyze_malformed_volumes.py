#!/usr/bin/env python3
import os, re, collections
infile='artifacts/reports/missing_by_volume/malformed_paths.txt'
out_dir='artifacts/reports/missing_by_volume'
if not os.path.exists(infile):
    print('Malformed paths file not found:', infile)
    raise SystemExit(1)
pattern=re.compile(r'/Volumes/([^/]+)')
counts=collections.Counter()
by_inner={}
with open(infile) as f:
    for line in f:
        line=line.strip()
        if not line: continue
        vols=pattern.findall(line)
        # vols is list of all /Volumes/... occurrences in the path
        if len(vols)>=2:
            inner=vols[1]
            counts[inner]+=1
            by_inner.setdefault(inner, []).append(line)
        elif len(vols)==1:
            counts[vols[0]]+=1

with open(os.path.join(out_dir,'inner_volume_counts.txt'),'w') as s:
    for k,v in counts.most_common():
        s.write(f"{k}\t{v}\n")

for k,rows in by_inner.items():
    safe=k.replace('/','_')
    with open(os.path.join(out_dir,f'inner_{safe}.txt'),'w') as g:
        g.write('\n'.join(rows))

print('Wrote inner_volume_counts and per-inner-volume lists to', out_dir)
print('Top inner volumes:')
for k,v in counts.most_common(20):
    print(k,v)
