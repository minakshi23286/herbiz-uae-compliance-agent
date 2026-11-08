# Copied into the repository for rc3 item 2 (founder/CTO 19 Oct 2026) from the assessment session's
# CL_HERBIZ_Competition_Assessment/CL_build_architecture_v3.py (corrections a-c applied there; d applied here: recorded
# answers that rely on a changed article are withheld). Usage: python3 CL_build_architecture.py out.svg "<candidate label>" <private tests> <public tests>
import html, sys
RC=sys.argv[2] if len(sys.argv)>2 else "t2-a-rc2 (585166f)"
NPRIV=sys.argv[3] if len(sys.argv)>3 else "498"; NPUB=sys.argv[4] if len(sys.argv)>4 else "329"   # rc3: counts from the evidence run
W,H=1640,1284
o=[]; E=lambda s: html.escape(s, quote=False)
C=dict(ink="#0F1B3D",muted="#556070",line="#D5DCE6",bg="#F6F8FC",white="#FFFFFF",
 blue="#1D4ED8",bluebg="#EAF1FE",bluest="#B7CBF5",
 green="#15803D",greenbg="#E8F6EE",greenst="#9FD5B3",
 teal="#0F766E",tealbg="#E6F5F2",tealst="#94CFC4",
 purple="#6D28D9",purplebg="#F2EDFC",purplest="#C9B5F2",
 orange="#C2410C",orangebg="#FFF3E8",orangest="#F3C29B",
 red="#B91C1C",redbg="#FDECEC",redst="#F1AAAA",
 grey="#6B7280",greybg="#F2F4F7",greyst="#CBD2DC")
def t(x,y,s,size=13,w=400,fill=C["ink"],anchor="start"):
    o.append(f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{w}" fill="{fill}" text-anchor="{anchor}">{E(s)}</text>')
def rect(x,y,w,h,fill,stroke,r=12,dash=False,sw=1.3):
    d=' stroke-dasharray="6 5"' if dash else ''
    o.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{d}/>')
ICONS={
 "user":'<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 3.6-6.5 8-6.5s8 2.5 8 6.5"/>',
 "users":'<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c0-3.6 2.9-5.6 6.5-5.6s6.5 2 6.5 5.6"/><circle cx="17" cy="9" r="2.8"/><path d="M16.5 14.6c3 .2 5 2 5 5"/>',
 "laptop":'<rect x="4" y="5" width="16" height="11" rx="1.5"/><path d="M2 19h20"/>',
 "phone":'<rect x="7" y="2.5" width="10" height="19" rx="2"/><path d="M11 18h2"/>',
 "eye":'<path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
 "shield":'<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/><path d="M8.8 12l2.2 2.2 4.2-4.4"/>',
 "route":'<circle cx="6" cy="5" r="2"/><circle cx="18" cy="19" r="2"/><path d="M6 7v4a4 4 0 0 0 4 4h4a4 4 0 0 1 4 2"/>',
 "search":'<circle cx="11" cy="11" r="6.5"/><path d="M16 16l5 5"/>',
 "db":'<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5"/><path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>',
 "clock":'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.5 2"/>',
 "doc":'<path d="M6 2.5h8l4 4V21.5H6z"/><path d="M14 2.5v4h4"/><path d="M9 14l2 2 4-4"/>',
 "warn":'<path d="M12 3.5L22 20.5H2z"/><path d="M12 10v5"/><path d="M12 17.6v.4"/>',
 "server":'<rect x="4" y="3.5" width="16" height="7" rx="1.5"/><rect x="4" y="13.5" width="16" height="7" rx="1.5"/><path d="M8 7h.01M8 17h.01"/>',
 "gear":'<circle cx="12" cy="12" r="3.2"/><path d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3M5.3 5.3l2.1 2.1M16.6 16.6l2.1 2.1M5.3 18.7l2.1-2.1M16.6 7.4l2.1-2.1"/>',
 "play":'<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M10 9l5 3-5 3z"/>',
 "folder":'<path d="M3 6.5h6l2 2h10v11H3z"/>',
 "book":'<path d="M4 4.5h6a2 2 0 0 1 2 2v14a2 2 0 0 0-2-2H4z"/><path d="M20 4.5h-6a2 2 0 0 0-2 2v14a2 2 0 0 1 2-2h6z"/>',
 "lock":'<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
 "check":'<rect x="3.5" y="3.5" width="17" height="17" rx="3"/><path d="M8 12l3 3 5-6"/>',
 "chain":'<path d="M10 14a4 4 0 0 1 0-5.7l2.3-2.3a4 4 0 0 1 5.7 5.7l-1.2 1.2"/><path d="M14 10a4 4 0 0 1 0 5.7l-2.3 2.3a4 4 0 0 1-5.7-5.7l1.2-1.2"/>',
 "bell":'<path d="M6 16v-5a6 6 0 0 1 12 0v5l2 2H4z"/><path d="M10 20.5a2 2 0 0 0 4 0"/>',
 "spark":'<path d="M12 3l2 6 6 2-6 2-2 6-2-6-6-2 6-2z"/>',
 "person":'<circle cx="12" cy="7.5" r="3.5"/><path d="M5 21v-2a5 5 0 0 1 5-5h4a5 5 0 0 1 5 5v2"/>',
 "chart":'<path d="M4 20V4M4 20h16"/><path d="M8.5 16v-4M12.5 16V8M16.5 16v-6"/>',
 "tool":'<path d="M14.5 6.5a4 4 0 0 0-5.3 5.3L3.5 17.5l3 3 5.7-5.7a4 4 0 0 0 5.3-5.3l-2.5 2.5-2.5-.5-.5-2.5z"/>',
 "globe":'<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>',
}
def icon(name,x,y,col,size=34,bg=True):
    if bg: rect(x,y,size,size,C[col+"bg"],C[col+"st"],r=9,sw=1)
    s=(size-10)/24
    o.append(f'<g transform="translate({x+5},{y+5}) scale({s})" fill="none" stroke="{C[col]}" stroke-width="{1.9/s*0.85:.2f}" stroke-linecap="round" stroke-linejoin="round">{ICONS[name]}</g>')
STAT={"built":("Built & tested","green"),"sim":("Simulated","purple"),"plan":("Planned","grey"),"gap":("Open gap","red"),"proto":("Prototype","orange"),"offline":("Evaluated offline","purple")}
def pill(x,y,key,right=False):
    lab,col=STAT[key]; w=6.6*len(lab)+18
    if right: x=x-w
    rect(x,y,w,20,C[col+"bg"],C[col],r=10,sw=0.9); t(x+w/2,y+14,lab,10.8,700,C[col],"middle"); return w
def card(x,y,w,h,ic,col,title,lines,status=None,bullets=True,dash=False,tsize=14,bottom=False):
    rect(x,y,w,h,C["white"] if not dash else C["greybg"],C[col+"st"],r=12,dash=dash)
    icon(ic,x+14,y+14,col)
    t(x+58,y+30,title,tsize,700,C[col] if col!="grey" else C["ink"])
    if status:
        if bottom: pill(x+16,y+h-30,status)
        else: pill(x+w-12,y+12,status,right=True)
    yy=y+58
    for ln in lines:
        if bullets: o.append(f'<circle cx="{x+62}" cy="{yy-4}" r="2" fill="{C["muted"]}"/>'); t(x+70,yy,ln,12,400,C["muted"])
        else: t(x+58,yy,ln,12,400,C["muted"])
        yy+=17
def lane(n,y,h,title,sub,col="blue"):
    rect(20,y,250,h,C["white"],C["line"],r=14)
    o.append(f'<circle cx="48" cy="{y+30}" r="14" fill="{C[col]}"/>'); t(48,y+35,str(n),14,800,"#fff","middle")
    yy=y+35
    for i,ln in enumerate(title.split("|")): t(72,yy+i*20,ln,15,800,C["ink"])
    yy+=20*len(title.split("|"))+4
    for i,ln in enumerate(sub.split("|")): t(72,yy+i*17,ln,12,400,C["muted"])
def arrow(x1,y1,x2,y2,col="blue",dash=False):
    d=' stroke-dasharray="5 4"' if dash else ''
    o.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{C[col]}" stroke-width="1.8" marker-end="url(#ah{col})"{d}/>')
o.append(f'<rect width="{W}" height="{H}" fill="{C["bg"]}"/>')
# ---------- header
t(32,58,"HerBiz",40,800,C["ink"]); t(186,58,"— UAE post-setup compliance agent",28,700,C["ink"])
t(32,90,"Deterministic answers today. AI-assisted agent tomorrow.",19,500,C["blue"])
t(32,116,f"Local prototype · release candidate {RC} · as built on 19 Oct 2026 · synthetic businesses only · not legal advice",12.5,400,C["muted"])
rect(1110,22,510,104,C["white"],C["line"],r=14)
t(1126,44,"WHO IT IS FOR",11,800,C["muted"])
aud=[("user","Home-business","owners (now)","blue",False),("person","Tax agents &","advisors (later)","grey",True),("users","Accountants","(later)","grey",True)]
for i,(ic,a,b,col,dsh) in enumerate(aud):
    x=1130+i*165; icon(ic,x,56,col,38); t(x+48,74,a,12.5,700,C["ink"] if not dsh else C["muted"]); t(x+48,91,b,12,400,C["muted"])
t(1126,116,"Demo uses fictional businesses; no real users yet.",11,400,C["muted"])
CX=290; CW=1040; RX=1350; RW=270
# ---------- lane 1 users
Y=146; lane(1,Y,128,"USERS","How people|use the prototype")
card(CX,Y,335,128,"laptop","blue","Owner web app",["desktop or phone browser, this computer","onboarding → obligations → VAT →","money & records → help → rule changes"],"built")
card(CX+352,Y,335,128,"play","blue","Demo flows",["fictional businesses (bakery, henna…)","VAT questions with recorded answers","corporate-tax demo: fictional only"],"built")
card(CX+704,Y,336,128,"eye","purple","Reviewer mode",["separate start flag","audit view only here","/api/audit/* hidden in owner mode"],"built")
arrow(CX+520,Y+130,CX+520,Y+166)
t(CX+530,Y+154,"HTTP · 127.0.0.1:8765 (this computer only) · no outbound network",12,600,C["blue"])
# ---------- lane 2 pipeline
Y=312; lane(2,Y,262,"ANSWER|PIPELINE","Deterministic,|safe and auditable","blue")
rect(CX,Y,CW,262,C["bluebg"],C["bluest"],r=14)
t(CX+18,Y+28,"HerBiz agent · local application",16,800,C["ink"]); pill(CX+290,Y+12,"built")
t(CX+CW-18,Y+28,"runs in this order for every question · fails closed",12,600,C["blue"],"end")
steps=[("shield","teal","Privacy gate",["checks typed text for","personal data first","blocks and explains","what to remove"],"before any search or log"),
 ("route","blue","Route",["matches topic and intent","exact match → replay","the recorded answer","otherwise → search"],"no AI at this step"),
 ("search","purple","Retrieve (v8)",["full-text search","provision map","cross-references","frozen code, hash-checked"],"v10 66.7 · v11 70.4 · 68.5%"),
 ("clock","orange","Source status",["current · outdated ·","conflicting (110 records)","link shown, never fetched","changed article → withheld"],"never silent about age"),
 ("doc","green","Explain",["rules as data, 5 states","sources and missing facts","next step to take","corporate tax: blocked"],"no unreviewed verdicts")]
sw=196; gap=11
for i,(ic,col,ti,ls,foot) in enumerate(steps):
    x=CX+16+i*(sw+gap); y=Y+44
    rect(x,y,sw,160,C["white"],C[col+"st"],r=12)
    o.append(f'<circle cx="{x+20}" cy="{y+22}" r="12" fill="{C[col]}"/>'); t(x+20,y+26.5,str(i+1),12.5,800,"#fff","middle")
    t(x+40,y+27,ti,14,800,C[col]); icon(ic,x+sw-44,y+10,col,30)
    for j,ln in enumerate(ls): t(x+14,y+60+j*17,ln,12,400,C["muted"])
    rect(x+10,y+128,sw-20,24,C[col+"bg"],C[col+"bg"],r=7); t(x+sw/2,y+144,foot,11.2,600,C[col],"middle")
    if i: arrow(x-gap,y+80,x-1,y+80)
chips=["Never claims \"complete\"","Shows source and date","Flags outdated law","Points to a tax agent","Writes an audit record"]
rect(CX+16,Y+214,CW-32,34,C["white"],C["greenst"],r=10)
slot=(CW-32)/5
for i,c in enumerate(chips):
    xx=CX+16+i*slot+14
    o.append(f'<circle cx="{xx+8}" cy="{Y+231}" r="8" fill="{C["green"]}"/><path d="M{xx+4} {Y+231}l3 3 5-6" stroke="#fff" stroke-width="2" fill="none" stroke-linecap="round"/>')
    t(xx+22,Y+235.5,c,11.8,600,C["ink"])
# ---------- right column AI panel
rect(RX,146,RW,428,C["white"],C["purplest"],r=14)
icon("spark",RX+14,160,"purple",34)
t(RX+58,176,"Where AI is used",15,800,C["purple"]); t(RX+58,194,"in this release",12,600,C["purple"])
rows=[("Live model at run time","red","None (declared off)",None),
 ("Recorded answers","ink","Sonnet 5.5, offline 16 Oct;","replayed on exact match only"),
 ("Search, rules, checks","ink","deterministic, no model",None)]
yy=224
for a,cl,b,c in rows:
    t(RX+16,yy,a,12,700,C["ink"]); t(RX+16,yy+17,b,12,700 if cl=="red" else 400,C[cl] if cl!="ink" else C["muted"])
    if c: t(RX+16,yy+33,c,12,400,C["muted"]); yy+=16
    yy+=44
o.append(f'<line x1="{RX+16}" y1="{yy-14}" x2="{RX+RW-16}" y2="{yy-14}" stroke="{C["line"]}"/>')
t(RX+16,yy+4,"live_model, evaluated offline 18 Oct 2026",11.5,800,C["purple"]); t(RX+16,yy+19,"— not in the app",11.5,800,C["purple"]); yy+=14
off=[("Haiku","finds 85.2% of required articles, but","2 answers wrongly marked complete"),("Sonnet","0 invented facts; quotes 226/226 exact","still says \"you must\" in 10%"),("Opus","similar quality at ~2× the cost",None),("Haiku · law changes","found 9/9 changes in FTA summary",None)]
yy+=26
for a,b,c in off:
    t(RX+16,yy,a,12,700,C["ink"]); t(RX+16,yy+16,b,11.5,400,C["muted"])
    if c: t(RX+16,yy+30,c,11.5,400,C["muted"]); yy+=14
    yy+=36
# ---------- lane 3 services
Y=596; lane(3,Y,140,"APPLICATION|SERVICES","Logic behind|the screens","blue")
card(CX,Y,335,140,"gear","blue","Obligations engine",["rule catalogues stored as data","five states, fails closed (D-062)","real-law rules blocked until reviewed"],"built")
card(CX+352,Y,335,140,"server","blue","Local server",["ask · dashboard · corporate tax","finance · rule changes · scenarios","answer withheld if audit write fails"],"built")
card(CX+704,Y,336,140,"play","purple","Error-scenario runner",["SC-1 missing facts → asks for them","SC-2 20 vs 30 days → shows both","SC-3 outdated article → flags it"],"sim")
rect(RX,Y,RW,140,C["white"],C["purplest"],r=14); icon("person",RX+14,Y+14,"purple"); t(RX+58,Y+30,"Human review",14,800,C["purple"]); pill(RX+RW-12,Y+12,"sim",True)
for j,ln in enumerate(["uncertain answers point to an","FTA-registered tax agent","source updates wait for a person","qualified reviewer: not engaged yet"]): t(RX+16,Y+62+j*17,ln,12,400,C["muted"])
arrow(RX-2,Y+70,CX+1042,Y+70,"purple",True)
# ---------- lane 4 data
Y=758; lane(4,Y,148,"DATA &|KNOWLEDGE","Sources and|workspace data","orange")
card(CX,Y,250,148,"db","orange","Knowledge base",["3 FTA VAT sources","371 passages","SHA-256 lock per file","read-only, md5-protected"],"built",tsize=13.5,bottom=True)
card(CX+263,Y,250,148,"folder","orange","Workspace data",["synthetic owner profiles","audit logs","never the knowledge base"],"built",tsize=13.5,bottom=True)
card(CX+526,Y,250,148,"book","orange","Source snapshot",["official FTA / MoF texts","allow-listed, hash lock","snapshot 17 Oct 2026","changes → report, never live"],"built",tsize=13.5,bottom=True)
card(CX+789,Y,251,148,"folder","orange","Fixtures",["fictional businesses","TEST RULES (not law)","scenarios SC-1 to SC-3"],"sim",tsize=13.5,bottom=True)
rect(RX,Y,RW,148,C["redbg"],C["redst"],r=14); icon("warn",RX+14,Y+14,"red"); t(RX+58,Y+28,"Outdated VAT copy",14,800,C["red"]); pill(RX+58,Y+36,"gap")
for j,ln in enumerate(["DL 16/2025 changed Arts 48, 74,","54 bis, 79 bis from 1 Jan 2026","stored copy predates it (G3)","recorded answers: withheld","new copy needs your approval"]): t(RX+16,Y+76+j*15.5,ln,11.8,400,C["ink"] if j<2 else C["muted"])
# ---------- lane 5 assurance
Y=928; lane(5,Y,134,"ASSURANCE","Tests, audit|and privacy","green")
card(CX,Y,335,134,"check","green","Automated tests",[f"{NPRIV} private tests pass",f"{NPUB}/{NPUB} public tests (clean export)","privacy scan: 0 blocking"],"built")
card(CX+352,Y,335,134,"chain","green","Audit records",["one record per response","hash chain, write locks","offline verify command"],"built")
card(CX+704,Y,336,134,"lock","green","Protected data",["databases never written by app","md5 checked before and after","no personal data: synthetic only"],"built")
rect(RX,Y,RW,134,C["white"],C["purplest"],r=14); icon("doc",RX+14,Y+14,"purple"); t(RX+58,Y+30,"Capabilities",14,800,C["purple"]); pill(RX+RW-12,Y+12,"built",True)
for j,ln in enumerate(["capabilities.json says what is","built, recorded, simulated, planned","a test fails if any response mode","is not declared there"]): t(RX+16,Y+62+j*17,ln,12,400,C["muted"])
# ---------- lane 6 next
Y=1084; lane(6,Y,108,"NEXT","Planned, not|in this release","grey")
nxt=[("spark","Live answers","behind an on/off switch","offline"),("shield","Answer guards","withhold · no \"you must\" · cite all","plan"),("tool","Tool use","agent calls search & status tools","plan"),("bell","Source monitoring","change alerts, human approval","plan"),("globe","More domains","e-invoicing · PDPL · Arabic","plan")]
bw=(CW+RW+20-4*12)/5
for i,(ic,a,b,st) in enumerate(nxt):
    x=CX+i*(bw+12); rect(x,Y,bw,108,C["greybg"],C["greyst"],r=12,dash=True); icon(ic,x+12,Y+12,"grey",30)
    t(x+50,Y+32,a,13.5,800,C["ink"]); t(x+14,Y+66,b,11.8,400,C["muted"]); pill(x+14,Y+78,st)
# ---------- status bar
Y=1206; rect(20,Y,W-40,0.01,C["bg"],C["bg"])
rect(20,Y,W-40,60,C["white"],C["line"],r=14)
t(36,Y+26,"Current status ("+RC.split(" ")[0]+")",14,800,C["ink"]); t(36,Y+44,"as built for the ITU submission",11.5,400,C["muted"])
stats=[("search","blue","Retrieval v8: v10 66.7% · v11 70.4%","pooled 68.5% (37/54), target 70% not met"),("warn","orange","Warnings","on 100% of answers"),("check","green","Tests",f"{NPRIV} private · {NPUB} public"),("lock","green","Protected data","unchanged")]
xx=232
for ic,col,a,b in stats:
    icon(ic,xx,Y+14,col,32); t(xx+40,Y+27,a,12,800,C["ink"]); t(xx+40,Y+44,b,11.5,400,C["muted"]); xx+=40+max(len(a)*7.2,len(b)*6.4)+18
t(xx,Y+36,"Legend",12.5,800,C["ink"]); lx=xx+54
for k in ("built","sim","offline","plan","gap"): lx+=pill(lx,Y+21,k)+5
defs="".join(f'<marker id="ah{k}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{C[k]}"/></marker>' for k in ("blue","purple","grey","green"))
svg=f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" font-family="Inter, -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif"><defs>{defs}</defs>{"".join(o)}</svg>'''
open(sys.argv[1],"w").write(svg); print("ok")
