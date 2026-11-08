"""Build the HerBiz 360 technical report in the official AI for Good Sandbox Hackathon template (Workstream A).

Keeps the template's own heading paragraphs (numbered) and its mapping table; replaces the example text with HerBiz
content. Only measured facts; status words: Implemented / Tested / Demonstrated / Planned / Unverified.
Usage: python3 experiments/ws_a/CL_build_tech_report.py --tests "N run, 0 failures, 1 skip" --commit <sha>
Writes docs/360/submission/CL_HERBIZ360_TECHNICAL_REPORT.docx and .md (no network, nothing published).
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

import docx
from docx.shared import Pt

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT.parent.parent / "AI For Good Documents" / "AI-for-Good-Sandbox-Hackathon-submission-template.docx"
OUT = ROOT / "docs" / "360" / "submission"
EVID = ROOT / "docs" / "360" / "evidence" / "CL_error_scenarios.json"

HEADER = [
    "AI for Good Sandbox Hackathon – [Team name: to confirm] – HerBiz 360: a post-setup compliance and financial-readiness agent for UAE small businesses",
    "Team leader: Minakshi Shrimalve",
    "Team members: [to confirm]   Contact details: [to confirm]",
    "Github link: [pending founder approval to publish the repository]",
]

def sections(tests: str, commit: str, ev: dict) -> list[tuple[str, list]]:
    m = ev["meta"]
    n_ok, n = m["passed"], m["total"]
    return [
    ("Introduction", [
                "UAE home-based and micro-businesses often discover tax, accounting and regulatory obligations only after set-up, spread across authorities. I built HerBiz 360, a planned product shown here as a prototype: an agentic assistant for the period after set-up. It asks a few plain questions, shows which obligations may apply, what is missing and which documents help, cites the official UAE source behind each item, organises records for an accountant and watches official texts for amendments. Every legally unreviewed conclusion is withheld and routed to a human. Its knowledge base uses openly available UAE government texts (FTA, Ministry of Finance, UAE Legislation portal).",
        "Section 4 maps the design to ITU-T Y.3172 and the ITU AI Ready Report 2.0 as explanation, not a claim of conformance. HerBiz is independent: it is not affiliated with, endorsed by or reviewed by the FTA, the Ministry of Finance, ITU or any UAE authority.",
        f"Status words: Implemented, Tested (automated tests pass), Demonstrated (shown end to end), Planned (not built), Unverified (not checked by a qualified professional). Evidence: private integration branch t2-integration at commit {commit}: {tests}. All demo businesses and data are fictional. Demo source snapshot: 17 October 2026. Every claim maps to a file, test or count in docs/360/submission/CL_HERBIZ360_REPORT_EVIDENCE_APPENDIX.md (outside these pages).",
    ]),
    ("Description of the use case ", [
        "**Problem (founder analysis; Unverified with users).** Official information is spread across portals and legal texts; professional help is often sought late; general chatbots can answer confidently without showing the governing text.",
        "**Customer scenarios** (Demonstrated with the fictional \"Amal\", a Dubai design business, as a sole establishment and as a small LLC):",
        "TABLE:UC",
        "**Capability declaration** (capabilities.json, contract capability_declaration/1.0): deterministic (engine, retrieval, validity checks, privacy gate, audit); recorded model output (VAT answers from claude-sonnet-5-5, recorded 16 Oct 2026 and replayed); proxy outputs (offline evaluation only, not model performance); **live inference: none**; tool use (reads local files, writes its own log; never browses, fetches, files, pays or sends); simulated (fictional businesses, test rules, reviewer, scenarios); planned (live answers, more domains, monitoring schedule, Arabic, real users, qualified review). Audit records carry these classes; a test checks they match.",
    ]),
    ("Use case requirement", [
        "**Implemented and Tested controls per Y.3172 node:**",
        "• SRC/C: official texts only, from allow-listed government hosts with a SHA-256 hash per file; a locked snapshot; amendments monitored report-only.",
        "• PP/M: article locators; unknown answers stay unknown; rules as reviewable data in a deterministic engine; recorded answers must quote passages word for word.",
        "• P: fail closed for every unreviewed legal rule (no definitive decision, deadline or filing instruction); corporate tax blocked; no approval wording; a \"may be incomplete\" warning; protected databases cannot be written. Source validity per passage (current, outdated, superseded, conflict) from 110 working records, which are not independently verified legal content; a current official link is shown, never fetched, and marked \"not checked by a person yet\" until it has been. A recorded answer that relies on a repealed, amended or conflicting article is withheld.",
        "• P (privacy): questions and reviewer notes with common UAE personal-data formats are not passed to search, storage or logs; pattern checks miss names, addresses and unusual formats.",
        "• **Auditability:** every owner-facing response writes one audit record (contract audit_record/1.0) to a daily SHA-256 hash-chained log with a database pointer row; an independent sanitizer rejects any record with passage text, personal-data patterns, local paths or long strings; an offline scanner re-checks stored logs; if a record cannot be written the answer is withheld; the audit view exists only in a separate reviewer mode; a blocked question leaves no text and no hash. Tested for every channel, tampering and 60 parallel requests.",
        "• D/SINK: owner-visible fields only; each item shows its source, copy date, uncertainty and the reviewer it needs.",
            ]),
    ("Mapping with ITU-T Y.3172 Readiness 2.0 Report, and domain-specific policies", ["TABLE:Y3172",
        "Readiness factors and dimensions (D1–D13) are as named in ITU \"AI Ready – Analysis Towards a Standardized Readiness Framework, Report 2.0\" (January 2026). Four governance references (UAE PDPL, Federal Decree-Law No. 45 of 2021; UAE Charter for the Development and Use of AI; UAE National Strategy for AI 2031; Dubai AI Ethics Principles) are collected, not activated or legally assessed. 0 legal sources have qualified approval. The ITU reference code was evaluated for compatibility, not adopted: on a comparative, non-independent set it found all required passages for 0 of 18 questions, against 8 of 18 for HerBiz's own search.",
    ]),
    ("Error scenarios.", [
        "Three synthetic scenarios release one event at a time; each step is checked against frozen expected flags and audited. All pass (Tested, Demonstrated):",
        "**SC-1 Missing information.** \"Not sure\" answers become questions (8, then 5, then 0); the complete profile stays \"blocked: legal validation\" with \"What you can do now\"; no deadline at any step.",
        "**SC-2 Conflicting rules.** Both values are shown with sources; no precedence rule is known (Arabic prevails over translations); no deadline; referral to an FTA-registered tax agent. It explains, not resolves.",
        "**SC-3 Outdated source.** The cited VAT copy predates its 2026 amendments: the answer is withheld; the current official link is shown, not fetched, as \"not checked by a person yet\"; review required.",
        f"**Other controversy scenarios** ({n_ok} of {n} Tested, with input, expected and actual result): a requested deadline is withheld; splitting sales to avoid VAT is declined; a later source change suppresses a claim, never silently; an Emirates ID number is not processed.",
        "**Retrieval exception (open; stated without qualification).** For free-typed questions the interim retrieval (deterministic, frozen code, 18 Oct 2026) found all required provisions for 66.7% of independent set v10 (18/27), 70.4% of independent set v11 (19/27) and 68.5% pooled (37/54), against a 70% target that is not met. It wrongly classified 4 of 27 (v10) and 1 of 27 (v11) valid VAT questions as out of scope and answered no out-of-scope question. It never claims completeness, so every answer is warned; zero silent-incomplete answers holds by that construction and is not evidence of completeness detection. The main limits are source coverage (the pinned VAT Decree-Law copy is outdated for Articles 48 and 74) and provision mapping (Article 79).",
        "**Other limitations:** 0 legal sources approved; answers recorded, not live; reviewer simulated; append-only notes and audit logs with retention unresolved; no real-user evidence; two deferred cautious inconsistencies (free-typed passages use whole-source age labels; the \"not checked by a person yet\" note cannot yet clear). Synthetic demonstration only. Not approved for real personal or financial data.",
    ]),
    ("Policy gaps and standards gaps derived from the mapping exercise", [
        "The event page says \"the relevance of the gaps and accuracy of the global policy examples would be a critical part of the evaluation\". Each gap is a hypothesis from official pages read on 18 Oct 2026; where a page is silent, that shows only what that page says. Foreign examples show how others handle the issue; they are not recommendations or claims that the issue is solved there.",
        "TABLE:GAPS",
        "**Standards gaps from building HerBiz:** no machine-readable authoritative-versus-translated flag; no amendment feed (MD 131/2026 was found by reading decisions); inconsistent version metadata; Y.3172 (06/2019) has no step for per-output human review or source validity (NIST AI 600-1 and EU AI Act Art. 14 address related points); unclear reuse terms, so I publish metadata, hashes and links only.",
        "**Next steps (Planned):** qualified review; source and provision-map review; retrieval measured on a new independent set; retention decisions; a privacy review; sessions with owners.",
    ]),
    ]

GAP_HEADER = ["Gap (hypothesis)", "UAE source: title and article", "Official URL (read 18 Oct 2026)", "Global examples (official)"]
GAP_ROWS = [
    ("G-T2-1 Licensing: no single machine-readable view of home-based licence expiry and renewal across emirates",
     "National Economic Register service page (updated 17 Apr 2026): licence details; no expiry or renewal reminders on the page. Dubai e-Trader page: no validity or renewal information",
     "u.ae/en/information-and-services/business/important-digital-services/national-economic-register; dubai.ae/investing/starting-a-business/ecommerce",
     "Singapore GoBusiness (one cross-agency touchpoint); UK Companies House opt-in email reminders; Estonia e-Business Register annual report confirms permits"),
    ("G-T2-2 Data protection: no published SME-proportionate PDPL guidance on the official pages reviewed",
     "Federal Decree-Law No. 45 of 2021 (PDPL), in force since 2 January 2022; its compliance period for businesses runs from the issuance of an Executive Regulation. The official pages I reviewed do not state whether that Regulation has been issued, and published commentary conflicts",
     "u.ae/en/about-the-uae/digital-uae/data/data-protection-laws (updated 4 Dec 2025)",
     "Singapore PDPC self-assessment tools and small-business FAQ; UK ICO small-organisations hub; Estonia data-protection checklists (EDPB SME guide)"),
    ("G-T2-3 Monitoring: no pre-deadline, cross-authority notification or machine-readable obligations feed found",
     "MoHRE Ministerial Resolution No. (0340) of 2026 (Wage Protection System), in force 1 June 2026: Art. 1(1) due date; Annex 1 item 2, alerts start the second day after it. FTA e-invoicing: invoices become structured data, obligations do not",
     "mohre.gov.ae (Resolution 0340 of 2026, PDF); tax.gov.ae/en/taxes/Vat/uae.einvoicing.aspx",
     "UK legislation.gov.uk developer API; UK HMRC Making Tax Digital; Estonia pre-filled TSD declarations from the employment register"),
    ("G-T2-4 Coordination: no single obligation view or coordination mechanism across authorities found",
     "Zero Government Bureaucracy Programme (updated 30 Dec 2024) targets procedures, not an SME obligation view; Basher covers set-up only. Obligations sit with FTA/MoF, MoHRE, emirate economic departments and the UAE Data Office",
     "u.ae/en/about-the-uae/strategies-initiatives-and-awards (Zero Government Bureaucracy Programme)",
     "UK Primary Authority (assured advice other regulators respect); Singapore GoBusiness; Estonia 2023 study proposes a gateway with proactive messages (proposal, not delivery)"),
]

UC_HEADER = ["Customer scenario (owner need)", "What HerBiz demonstrates (components; status)", "Y.3172 stages", "Readiness 2.0"]
UC_ROWS = [
    ("UC-01 New-business onboarding (demo steps 1–2): \"I've registered. What do I organise next?\"",
     "Plain-question onboarding (\"Not sure\" allowed, errors explained); obligations engine (rules as data); owner overview with missing facts and documents. Demonstrated",
     "SRC (owner answers), PP, M, D, SINK", "D6 Human Interface; D11 AI for Inclusion; D4 Contextualization"),
    ("UC-02 VAT information (step 3): \"Do I need to register?\"",
     "VAT items with official sources and uncertainty; no unreviewed dates; recorded answers quoting passages; free questions get passages with source validity, never an answer; \"may be incomplete\" warning. Demonstrated (answers recorded)",
     "SRC, C, PP (retrieval), M, P", "Data factor; D5 AI in Workflows; D10 AI & Policies"),
    ("UC-03 Corporate-tax information, fictional scenarios (step 4): \"What information do I need?\"",
     "Questions, document checklist and possible steps only, labelled \"Demo scenario — fictional business.\"; every determination blocked; reviewer needed named. Demonstrated",
     "M, P, D", "D10 AI & Policies; D9 Humans in AI Integration"),
    ("UC-04 Financial-records readiness (step 5): \"Are my records ready?\"",
     "Checklist of missing invoices, receipts and bank records; draft estimate labelled not financial statements; CSV for an accountant. Demonstrated",
     "SRC (synthetic records), PP, D, SINK", "D5 AI in Workflows; D6 Human Interface"),
    ("UC-05 Regulatory-change awareness (step 7): \"A rule changed. Does it affect me?\"",
     "Source monitoring; real amendment (MD 131 of 2026) with an unreviewed summary; affected item flagged \"changed — pending review\"; nothing activated; snapshot lock. Demonstrated (reviewer simulated)",
     "C, P, D", "D10 AI & Policies; D13 Digital Infrastructure; Standards factor"),
    ("UC-06 Professional assistance (step 6): \"Can I do this myself?\"",
     "Who-does-what guide (estimates, no fees); referral to an FTA-registered tax agent or accountant on every uncertain item. Demonstrated",
     "P, SINK", "D8 Collaboration with AI; D9 Humans in AI Integration"),
]

Y_HEADER = ["", "Use case (HerBiz 360, UAE small businesses)", "Readiness 2.0 Report (factors / dimensions)", "Documents (openly available UAE texts; ITU)"]
TABLE_ROWS = [
    ("SRC", "Official FTA, MoF and UAE Legislation texts (VAT: 3 sources, 5 captures, 371 passages; 27 further official sources inventoried as metadata); fictional owner answers. Implemented",
     "Data factor; D4 Contextualization and Regional Impact; D1 Data/model Marketplace",
     "Federal Decree-Law No. 8 of 2017 (VAT) and Executive Regulation; Federal Decree-Law No. 47 of 2022 (Corporate Tax); MD 73/2023 and MD 131/2026 (SBR)"),
    ("C", "Allow-listed HTTPS collection with hash lock; fixed source snapshot; amendment monitoring report-only. Implemented",
     "Deployment Support; D13 Digital Infrastructure",
     "FTA legislation pages and service cards (tax.gov.ae); MoF decisions (mof.gov.ae); uaelegislation.gov.ae"),
    ("PP", "Text extraction with article locators; lexical full-text index; profile validation; interim retrieval v8 (all required provisions: v10 66.7%, v11 70.4%, pooled 68.5%; target 70% not met; every answer warned; section 5). Implemented, Tested",
     "Data factor; Standards factor",
     "FTA Decision No. 4 of 2026 (accounting records); register metadata: evidence level, retrieval date"),
    ("M", "Analogy: a deterministic obligations engine (rules as data, not ML) plus language-model answers grounded in quoted passages, recorded (no live calls). Implemented, Tested",
     "D5 Level of Integration of AI in Workflows; Research factor",
     "Rules cite DL 8/2017 Art. 13, 17, 19, 21; ER Art. 7, 8, 14; corporate tax: FTA Decision No. 3 of 2024 (synthetic scenario only)"),
    ("P", "Fail closed for unreviewed rules; corporate tax blocked; citation, quote and wording checks; incompleteness warning; source validity; personal-data intake check; hash-chained audit records. Implemented, Tested; qualified review and retention Planned",
     "D10 AI & Policies; D8 Collaboration with AI; D9 Impacts of Humans in AI Integration",
     "HerBiz design policy; four governance references (PDPL DL 45/2021, UAE AI Charter, UAE AI Strategy 2031, Dubai AI Ethics): collected, not activated or legally assessed"),
    ("D", "Presentation adapter: owner-only fields; source labels (uncertainty, date copied, review status); amendment impact flags. Implemented, Tested",
     "D6 Human Interface; D7 Strategy Alignment",
     "ITU-T Y.3172 (06/2019) clause 8.1; HerBiz source register (0 legal sources approved)"),
    ("SINK", "Owner dashboard (phone and desktop) and human escalation; reviewer simulated in the demo. Demonstrated",
     "D11 AI for Inclusion; D6 Human Interface; Sandbox Environments factor",
     "FTA EmaraTax service pages (where the owner acts); HerBiz never files or pays"),
]
TABLES = {"UC": (UC_HEADER, UC_ROWS), "Y3172": (Y_HEADER, TABLE_ROWS), "GAPS": (GAP_HEADER, GAP_ROWS)}


def _set_text(p, text: str):
    for r in list(p.runs):
        r._element.getparent().remove(r._element)
    parts = text.split("**")
    for i, part in enumerate(parts):
        if part:
            run = p.add_run(part)
            run.bold = i % 2 == 1


def build(tests: str, commit: str) -> tuple[Path, Path]:
    ev = json.loads(EVID.read_text(encoding="utf-8"))
    d = docx.Document(str(TEMPLATE))
    body = d.element.body
    paras = d.paragraphs
    heading_proto = next(p for p in paras if p.style.name == "List Paragraph" and p.text.strip().startswith("Introduction"))._element
    normal_proto = next(p for p in paras if p.style.name == "Normal" and p.text.strip().startswith("AI is increasingly"))._element
    table_el = d.tables[0]._element
    sect = body[-1]                                      # sectPr
    for el in list(body):
        if el is not sect:
            body.remove(el)

    def add_para(text: str, proto, size=None):
        el = copy.deepcopy(proto)
        body.insert(len(body) - 1, el)
        p = docx.text.paragraph.Paragraph(el, d._body)
        _set_text(p, text)
        if size:
            for r in p.runs:
                r.font.size = Pt(size)
        return p

    md = []
    for i, line in enumerate(HEADER):
        add_para(line, normal_proto, 11 if i else 12).runs[0].bold = i == 0
        md.append(("# " if i == 0 else "") + line)
    for title, items in sections(tests, commit, ev):
        add_para(title.strip(), heading_proto)
        md.append(f"\n## {title.strip()}\n")
        for item in items:
            if item.startswith("TABLE:"):
                hdr, rows = TABLES[item.split(":", 1)[1]]
                tbl = copy.deepcopy(table_el)
                body.insert(len(body) - 1, tbl)
                t = docx.table.Table(tbl, d._body)
                while len(t.rows) - 1 > len(rows):                 # drop the template's surplus rows
                    t._tbl.remove(t.rows[-1]._tr)
                while len(t.rows) - 1 < len(rows):
                    t._tbl.append(copy.deepcopy(t.rows[-1]._tr))
                for i, (row, vals) in enumerate(zip(t.rows, [hdr] + list(rows))):
                    for c, txt in zip(row.cells, vals):
                        _set_text(c.paragraphs[0], txt)
                        for extra in c.paragraphs[1:]:
                            extra._element.getparent().remove(extra._element)
                        for r in c.paragraphs[0].runs:
                            r.font.size = Pt(9 if i == 0 else 8.5); r.bold = r.bold or i == 0
                md.append("| " + " | ".join(h or "Node" for h in hdr) + " |\n|" + "---|" * len(hdr))
                md += ["| " + " | ".join(v) + " |" for v in rows]
                continue
            add_para(item, normal_proto, 10.5)
            md.append(item)
    OUT.mkdir(parents=True, exist_ok=True)
    out_docx, out_md = OUT / "CL_HERBIZ360_TECHNICAL_REPORT.docx", OUT / "CL_HERBIZ360_TECHNICAL_REPORT.md"
    d.save(str(out_docx))
    out_md.write_text("\n".join(md) + "\n", encoding="utf-8")
    return out_docx, out_md


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tests", required=True)
    ap.add_argument("--commit", required=True)
    a = ap.parse_args()
    print(*build(a.tests, a.commit))
