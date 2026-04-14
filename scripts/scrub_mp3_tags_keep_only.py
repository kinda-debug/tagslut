#!/usr/bin/env python3

from __future__ import annotations
import argparse, shutil, sys
from pathlib import Path
from mutagen.id3 import (
    ID3,
    ID3NoHeaderError,
    TIT2,   # Title
    TPE1,   # Artist
    TALB,   # Album
    TBPM,   # BPM
    TKEY,   # Key
    COMM,   # Comment
    TSRC,   # ISRC
    TPUB,   # Label
    TYER,   # Year
    TDRC,   # Date
    APIC,   # Artwork
)

KEEP = {"TPE1","TIT2","TALB","TBPM","TKEY","COMM","TSRC","TPUB","TYER","APIC"}

def iter_mp3(root):
    for p in Path(root).rglob("*.mp3"):
        if p.is_file():
            yield p

def text(frame):
    try:
        return str(frame.text[0]).strip() if frame.text else None
    except:
        return None

def year(v):
    if not v: return None
    for i in range(len(v)-3):
        s=v[i:i+4]
        if s.isdigit(): return s
    return None

def collect(tags):
    d={"artist":None,"title":None,"album":None,"bpm":None,"key":None,"comment":None,"isrc":None,"label":None,"year":None,"apic":list(tags.getall("APIC"))}
    if tags.getall("TPE1"): d["artist"]=text(tags["TPE1"])
    if tags.getall("TIT2"): d["title"]=text(tags["TIT2"])
    if tags.getall("TALB"): d["album"]=text(tags["TALB"])
    if tags.getall("TBPM"): d["bpm"]=text(tags["TBPM"])
    if tags.getall("TKEY"): d["key"]=text(tags["TKEY"])
    if tags.getall("COMM"):
        for c in tags.getall("COMM"):
            t=text(c)
            if t: d["comment"]=t; break
    if tags.getall("TSRC"): d["isrc"]=text(tags["TSRC"])
    if tags.getall("TPUB"): d["label"]=text(tags["TPUB"])
    if tags.getall("TYER"): d["year"]=year(text(tags["TYER"]))
    if not d["year"] and tags.getall("TDRC"): d["year"]=year(text(tags["TDRC"]))
    for f in tags.getall("TXXX"):
        k=(f.desc or "").upper()
        v=text(f)
        if not v: continue
        if k=="ISRC" and not d["isrc"]: d["isrc"]=v
        elif k=="LABEL" and not d["label"]: d["label"]=v
        elif k=="INITIALKEY" and not d["key"]: d["key"]=v
        elif k=="BPM" and not d["bpm"]: d["bpm"]=v
        elif k in {"COMMENT","COMMENTS"} and not d["comment"]: d["comment"]=v
        elif k in {"YEAR","DATE"} and not d["year"]: d["year"]=year(v)
    return d

def build(v):
    t=ID3()
    if v["title"]: t.add(TIT2(encoding=3,text=[v["title"]]))
    if v["artist"]: t.add(TPE1(encoding=3,text=[v["artist"]]))
    if v["album"]: t.add(TALB(encoding=3,text=[v["album"]]))
    if v["bpm"]: t.add(TBPM(encoding=3,text=[v["bpm"]]))
    if v["key"]: t.add(TKEY(encoding=3,text=[v["key"]]))
    if v["comment"]: t.add(COMM(encoding=3,lang="eng",desc="",text=[v["comment"]]))
    if v["isrc"]: t.add(TSRC(encoding=3,text=[v["isrc"]]))
    if v["label"]: t.add(TPUB(encoding=3,text=[v["label"]]))
    if v["year"]: t.add(TYER(encoding=3,text=[v["year"]]))
    for a in v["apic"]: t.add(a)
    t.update_to_v23()
    return t

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--execute",action="store_true")
    ap.add_argument("--backup",action="store_true")
    args=ap.parse_args()

    root=Path(args.root)
    if not root.exists(): sys.exit("bad path")

    for f in iter_mp3(root):
        try:
            tags=ID3(f)
        except:
            continue

        v=collect(tags)
        new=build(v)

        if not args.execute:
            print("[DRY]",f)
            continue

        if args.backup:
            b=f.with_suffix(".mp3.bak")
            if not b.exists(): shutil.copy2(f,b)

        tags.delete(f,delete_v1=True,delete_v2=True)
        new.save(f,v2_version=3,v1=0)
        print("[OK]",f)

if __name__=="__main__":
    main()
