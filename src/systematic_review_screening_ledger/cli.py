import argparse, csv, hashlib, json, re, sys
from pathlib import Path

def norm_title(value): return " ".join(re.findall(r"[a-z0-9]+", (value or "").casefold()))
def norm_doi(value): return re.sub(r"[\s.]$", "", re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", (value or "").strip(), flags=re.I)).casefold()
def bib_entries(text):
    entries=[]; offset=0
    while True:
        match=re.search(r"@([A-Za-z]+)\s*([\{\(])",text[offset:])
        if not match: break
        start=offset+match.start(); opening=offset+match.end()-1; opener=text[opening]; closer="}" if opener=="{" else ")"
        depth=1; quoted=False; index=opening+1
        while index<len(text) and depth:
            char=text[index]
            if char=='"' and (index==0 or text[index-1]!="\\"): quoted=not quoted
            if not quoted:
                if char==opener: depth+=1
                elif char==closer: depth-=1
            index+=1
        if depth: raise ValueError("unclosed BibTeX entry")
        inner=text[opening+1:index-1]; comma=inner.find(",")
        if comma>=0:
            key=inner[:comma].strip(); body=inner[comma+1:]; fields={}; pos=0
            while pos<len(body):
                field=re.search(r"([A-Za-z][A-Za-z0-9_-]*)\s*=\s*",body[pos:])
                if not field: break
                name=field.group(1).casefold(); value_start=pos+field.end()
                if value_start>=len(body): break
                if body[value_start]=="{":
                    nest=1; end=value_start+1
                    while end<len(body) and nest:
                        if body[end]=="{": nest+=1
                        elif body[end]=="}": nest-=1
                        end+=1
                    value=body[value_start+1:end-1].strip()
                elif body[value_start]=='"':
                    end=value_start+1
                    while end<len(body) and (body[end]!='"' or body[end-1]=="\\"): end+=1
                    value=body[value_start+1:end].strip(); end=min(end+1,len(body))
                else:
                    end=body.find(",",value_start)
                    if end<0: end=len(body)
                    value=body[value_start:end].strip()
                fields[name]=value; pos=end
            entries.append((key,fields,text[start:index]))
        offset=index
    return entries
def parse_records(path):
    text=Path(path).read_text(encoding="utf-8-sig")
    ext=Path(path).suffix.casefold()
    if ext==".csv":
        rows=list(csv.DictReader(text.splitlines()))
        return [{"fields":{k:v for k,v in row.items()},"source_text":json.dumps(row,ensure_ascii=False),"source_file":Path(path).name,"source_format":"csv"} for row in rows]
    if ext==".ris":
        out=[]; cur={}; raw=[]
        for line in text.splitlines():
            if line.strip().upper()=="ER  -":
                out.append({"fields":cur,"source_text":"\n".join(raw+[line]),"source_file":Path(path).name,"source_format":"ris"}); cur={}; raw=[]; continue
            raw.append(line)
            m=re.match(r"^([A-Z0-9]{2})\s+-\s+(.*)$",line)
            if m:
                k,v=m.groups(); cur[k]=cur.get(k,[])+[v]
        if cur or raw: out.append({"fields":cur,"source_text":"\n".join(raw),"source_file":Path(path).name,"source_format":"ris"})
        for rec in out:
            f=rec["fields"]; rec["title"]=(f.get("TI") or f.get("T1") or [""])[0]; rec["doi"]=(f.get("DO") or [""])[0]
        return out
    if ext==".bib":
        out=[]
        for key,fields,raw in bib_entries(text):
            out.append({"fields":fields,"citekey":key,"title":fields.get("title",""),"doi":fields.get("doi",""),"source_text":raw,"source_file":Path(path).name,"source_format":"bibtex"})
        if not out and text.strip(): raise ValueError("no BibTeX entries parsed")
        return out
    raise ValueError("supported input formats are .ris, .bib, and .csv")

def get_identity(rec):
    f=rec.get("fields",{})
    ris_title=f.get("TI",[""])
    ris_doi=f.get("DO",[""])
    if isinstance(ris_title,list): ris_title=ris_title[0] if ris_title else ""
    if isinstance(ris_doi,list): ris_doi=ris_doi[0] if ris_doi else ""
    title=rec.get("title") or f.get("title") or ris_title
    doi=rec.get("doi") or f.get("doi") or ris_doi
    return norm_title(title),norm_doi(doi)
def record_id(rec):
    title,doi=get_identity(rec); key="doi:"+doi if doi else "title:"+title
    if not doi and not title:
        key="unidentified:"+hashlib.sha256((rec.get("source_file","")+"\0"+rec.get("source_text","")).encode("utf-8")).hexdigest()
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
def import_into(ledger, records):
    groups={r["record_id"]:r for r in ledger.get("records",[])}
    for incoming in records:
        incoming=dict(incoming); rid=record_id(incoming); incoming["record_id"]=rid
        old=groups.get(rid)
        if old is None:
            incoming["source_records"]=[{"source_file":incoming.get("source_file"),"source_format":incoming.get("source_format"),"source_text":incoming.get("source_text"),"fields":incoming.get("fields",{})}]
            groups[rid]=incoming
        else:
            old.setdefault("source_records",[]).append({"source_file":incoming.get("source_file"),"source_format":incoming.get("source_format"),"source_text":incoming.get("source_text"),"fields":incoming.get("fields",{})})
    ledger["records"]=list(groups.values()); ledger.setdefault("votes",[]); return ledger

def conflicts(ledger):
    by={}
    for vote in ledger.get("votes",[]): by.setdefault(vote.get("record_id"),{})[vote.get("reviewer")]=vote
    return [rid for rid, reviewers in by.items() if len(reviewers)>=2 and len({v.get("decision") for v in reviewers.values()})>1]
def summary(ledger):
    votes={}
    for v in ledger.get("votes",[]): votes.setdefault(v.get("record_id"),{})[v.get("reviewer")]=v
    return {"records":len(ledger.get("records",[])),"imported_source_records":sum(len(r.get("source_records",[])) for r in ledger.get("records",[])),"votes":len(ledger.get("votes",[])),"conflicts":len(conflicts(ledger)),"agreement_include":sum(1 for vv in votes.values() if len(vv)>=2 and {v.get("decision") for v in vv.values()}=={"include"}),"agreement_exclude":sum(1 for vv in votes.values() if len(vv)>=2 and {v.get("decision") for v in vv.values()}=={"exclude"}),"unresolved":sum(1 for r in ledger.get("records",[]) if len(votes.get(r["record_id"],{}))<2)}
def read_ledger(path):
    ledger=json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(ledger,dict) or not isinstance(ledger.get("records"),list) or not isinstance(ledger.get("votes",[]),list):
        raise ValueError("ledger must be an object with records and votes arrays")
    if not all(isinstance(r,dict) and isinstance(r.get("record_id"),str) for r in ledger["records"]):
        raise ValueError("ledger contains an invalid record")
    if not all(isinstance(v,dict) for v in ledger.get("votes",[])):
        raise ValueError("ledger contains an invalid vote")
    record_ids={r["record_id"] for r in ledger["records"]}
    for vote in ledger.get("votes",[]):
        if vote.get("record_id") not in record_ids or not isinstance(vote.get("reviewer"),str) or not vote["reviewer"].strip() or vote.get("decision") not in ("include","exclude","uncertain") or not isinstance(vote.get("reason",""),str):
            raise ValueError("ledger contains an invalid vote")
    ledger.setdefault("votes",[])
    return ledger
def main(argv=None):
    p=argparse.ArgumentParser(description="Maintain imported records and independent review votes")
    sp=p.add_subparsers(dest="cmd",required=True)
    a=sp.add_parser("import"); a.add_argument("input"); a.add_argument("--ledger",required=True)
    v=sp.add_parser("vote"); v.add_argument("vote_json"); v.add_argument("--ledger",required=True)
    e=sp.add_parser("export"); e.add_argument("--ledger",required=True); e.add_argument("--output"); e.add_argument("--format",choices=("json","csv"),default="json")
    args=p.parse_args(argv)
    try:
        if args.cmd=="import":
            records=parse_records(args.input); path=Path(args.ledger); ledger=read_ledger(path) if path.exists() else {"records":[],"votes":[]}; import_into(ledger,records); path.write_text(json.dumps(ledger,ensure_ascii=False,indent=2)+"\n",encoding="utf-8",newline="\n"); print(f"imported {len(records)}; grouped {len(ledger['records'])} record(s)")
        elif args.cmd=="vote":
            path=Path(args.ledger); ledger=read_ledger(path); vote=json.loads(Path(args.vote_json).read_text(encoding="utf-8"))
            if not isinstance(vote,dict): raise ValueError("vote must be a JSON object")
            if vote.get("record_id") not in {r["record_id"] for r in ledger.get("records",[])}: raise ValueError("unknown record_id")
            if not isinstance(vote.get("reviewer"),str) or not vote["reviewer"].strip() or vote.get("decision") not in ("include","exclude","uncertain"): raise ValueError("reviewer required; decision must be include, exclude, or uncertain")
            if not isinstance(vote.get("reason",""),str): raise ValueError("reason must be text")
            ledger.setdefault("votes",[]).append(vote); path.write_text(json.dumps(ledger,ensure_ascii=False,indent=2)+"\n",encoding="utf-8",newline="\n"); print(json.dumps({"conflicts":conflicts(ledger),"counts":summary(ledger)}))
        else:
            ledger=read_ledger(args.ledger); data={"summary":summary(ledger),"conflict_record_ids":conflicts(ledger),"records":ledger.get("records",[]),"votes":ledger.get("votes",[])}
            if args.format=="json": text=json.dumps(data,ensure_ascii=False,indent=2)+"\n"
            else:
                from io import StringIO
                s=StringIO(newline=""); w=csv.writer(s); w.writerow(["record_id","title","doi","source_count","reviewer","decision","reason","conflict","total_records","total_source_records","total_votes","conflict_count","unresolved_count","agreement_include","agreement_exclude"])
                conflictset=set(conflicts(ledger)); vote_map={}
                for vote in ledger.get("votes",[]): vote_map.setdefault(vote["record_id"],[]).append(vote)
                counts=summary(ledger)
                for r in ledger.get("records",[]):
                    title,doi=get_identity(r); votes=vote_map.get(r["record_id"],[]) or [{}]
                    for vote in votes:
                        w.writerow([r["record_id"],title,doi,len(r.get("source_records",[])),vote.get("reviewer",""),vote.get("decision",""),vote.get("reason",""),r["record_id"] in conflictset,counts["records"],counts["imported_source_records"],counts["votes"],counts["conflicts"],counts["unresolved"],counts["agreement_include"],counts["agreement_exclude"]])
                text=s.getvalue()
            Path(args.output).write_text(text,encoding="utf-8",newline="\n") if args.output else sys.stdout.write(text)
        return 0
    except (OSError,json.JSONDecodeError,ValueError,csv.Error) as exc: print(f"error: {exc}",file=sys.stderr); return 2
if __name__=="__main__": raise SystemExit(main())
