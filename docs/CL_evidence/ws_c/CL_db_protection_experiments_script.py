import sys, os, sqlite3, subprocess, json
from pathlib import Path
sys.path.insert(0, ".")
from compliance_agent.dbsafety import copy_readonly
from compliance_agent.rag_c import protection as P
from compliance_agent.store import Store
from compliance_agent.engine import Engine
from compliance_agent.clock import FixedClock
from compliance_agent import kb as K
SP=Path(sys.argv[1]); REF=Path("data/CL_c_readonly_copy.sqlite3"); res={}
def tryw(db, sql="INSERT INTO meta(key,value) VALUES('probe','x')"):
    c=None
    try:
        c=sqlite3.connect(db); c.execute(sql); c.commit(); return "WRITE OK"
    except Exception as e: return f"{type(e).__name__}: {e}"
    finally:
        if c: c.close()
a=copy_readonly(REF, SP/"mode444.sqlite3"); os.chmod(a,0o444)
res["L2_chmod444_write"]=tryw(a)
try: s=Store(a); s.close(); res["L2_store_open"]="Store opened"
except Exception as e: res["L2_store_open"]=f"{type(e).__name__}: {e}"
res["L2_ro_read"]=sqlite3.connect(f"file:{a}?mode=ro",uri=True).execute("select count(*) from passages").fetchone()[0]
res["L2_side_files_after"]=[s for s in ("-journal","-wal","-shm") if Path(str(a)+s).exists()]
os.chmod(a,0o644); res["L2_revert"]=tryw(a, "SELECT 1")
b=copy_readonly(REF, SP/"uchg.sqlite3"); subprocess.run(["chflags","uchg",str(b)],check=True)
res["L3_write"]=tryw(b)
for op,f in (("rm",lambda: os.remove(b)),("rename",lambda: os.rename(b, SP/"moved.sqlite3")),("chmod",lambda: os.chmod(b,0o600))):
    try: f(); res[f"L3_{op}"]="ALLOWED"
    except Exception as e: res[f"L3_{op}"]=f"refused ({type(e).__name__})"
res["L3_ro_read"]=sqlite3.connect(f"file:{b}?mode=ro",uri=True).execute("select count(*) from passages").fetchone()[0]
res["L3_status"]={k:v for k,v in P.status(b).items() if k in ("mode","user_immutable","journal_mode")}
subprocess.run(["chflags","nouchg",str(b)],check=True); res["L3_revert_write"]=tryw(b)
c=copy_readonly(REF, SP/"wal.sqlite3"); x=sqlite3.connect(c); x.execute("PRAGMA journal_mode=WAL"); x.close()
os.chmod(c,0o444)
try: n=sqlite3.connect(f"file:{c}?mode=ro",uri=True).execute("select count(*) from passages").fetchone()[0]; res["WAL_ro_read_444_no_shm"]=f"ok {n}"
except Exception as e: res["WAL_ro_read_444_no_shm"]=f"{type(e).__name__}: {e}"
try: n=sqlite3.connect(f"file:{c}?immutable=1",uri=True).execute("select count(*) from passages").fetchone()[0]; res["WAL_immutable1_read"]=f"ok {n}"
except Exception as e: res["WAL_immutable1_read"]=f"{type(e).__name__}: {e}"
os.chmod(c,0o644)
w=sqlite3.connect(f"file:{c}?mode=ro",uri=True); w.execute("select count(*) from passages").fetchone()
res["WAL_ro_read_writable_side_files"]=[s for s in ("-wal","-shm") if Path(str(c)+s).exists()]; w.close()
d=copy_readonly(REF, SP/"delete.sqlite3"); q=sqlite3.connect(f"file:{d}?mode=ro",uri=True); q.execute("select count(*) from passages").fetchone(); q.close()
res["DELETE_mode_ro_side_files"]=[s for s in ("-journal","-wal","-shm") if Path(str(d)+s).exists()]
h=copy_readonly(REF, SP/"hardened.sqlite3"); res["L4_applied"]=len(P.apply_triggers(h))
eid=sqlite3.connect(h).execute("select min(event_id) from audit_events").fetchone()[0]
res["L4_replace_audit"]=tryw(h, f"INSERT OR REPLACE INTO audit_events SELECT event_id,at,'forged',event,entity,entity_id,payload_json FROM audit_events WHERE event_id={eid}")
res["L4_update_passage"]=tryw(h,"UPDATE passages SET text='x' WHERE rowid=1")
res["L4_delete_version"]=tryw(h,"DELETE FROM source_versions WHERE version_id='FTA-VAT-ER@v1'")
res["L4_update_doc_hash"]=tryw(h,"UPDATE documents SET sha256='0' WHERE rowid=1")
res["L4_drop_trigger"]=tryw(h,"DROP TRIGGER C_PROTECT_passages_no_delete")
P.apply_triggers(h)
e=Engine(Store(h), FixedClock("2026-10-17T10:00:00"))
kbx=K.KnowledgeBase(e, Path("data"), fetch=lambda u: (_ for _ in ()).throw(K.CollectError("offline")), lock_path=Path("knowledge_base/CL_collected_lock.json"))
try: out=kbx.rebuild(json.loads(Path("knowledge_base/CL_source_manifest.json").read_text())); res["L4_legit_rebuild"]=sorted({o['outcome'] for o in out})
except Exception as ex: res["L4_legit_rebuild"]=f"{type(ex).__name__}: {ex}"
try: res["L4_legit_review_approve"]=e.review_source("FTA-VAT-REG-PAGE@v1","approve","Test Reviewer","qualified tax reviewer (TEST, copy only)","protection experiment")
except Exception as ex: res["L4_legit_review_approve"]=f"{type(ex).__name__}: {ex}"
e.s.close()
res["L4_rollback_removed"]=len(P.remove_triggers(h)); res["L4_after_rollback_update"]=tryw(h,"UPDATE documents SET bytes=bytes WHERE rowid=1")
try: P.apply_triggers("../CL_compliance_agent_app/data/CL_compliance.sqlite3"); res["L4_refuses_original"]="NOT REFUSED"
except Exception as ex: res["L4_refuses_original"]=type(ex).__name__
res["original_status_readonly"]={k:v for k,v in P.status("../CL_compliance_agent_app/data/CL_compliance.sqlite3").items() if k!="path"}
print(json.dumps(res,indent=1,default=str)); json.dump(res, open(SP/"results.json","w"), indent=1, default=str)
