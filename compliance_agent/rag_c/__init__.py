"""Workstream C (RAG foundation): read-only source governance tools.

No database is ever written. Nothing in this package writes to the authoritative database, data/raw/, the collection lock, the frozen evaluation
sets or the experiment ledger. Databases are opened with SQLite's read-only mode; the ingestion dry run builds into a
temporary folder (or a new file that must not exist yet). Retrieval code (llm_lab/retrieve.py, concepts.py) belongs to
Workstream B and is not imported or changed here.

    python3 -m compliance_agent.rag_c inventory   [--db data/<copy>.sqlite3]        read-only corpus report
    python3 -m compliance_agent.rag_c validate    [--register knowledge_base/CL_source_register.json]
    python3 -m compliance_agent.rag_c hashes                                         raw files vs collection lock
    python3 -m compliance_agent.rag_c duplicates  [--db ...]                          same bytes / same text / same URL
    python3 -m compliance_agent.rag_c compare OLD_VERSION NEW_VERSION [--db ...]     article-level differences
    python3 -m compliance_agent.rag_c dryrun      [--out data/CL_rag_c_build.sqlite3] offline rebuild + reproducibility
    python3 -m compliance_agent.rag_c diff BUILD_DB [--db REFERENCE]                 content diff by (doc, locator)
    python3 -m compliance_agent.rag_c amendments | claims | facts | validity [--write] | trace | extraction | headings
    python3 -m compliance_agent.rag_c discover --listing FILE [--listing-url URL] [--write]
    python3 -m compliance_agent.rag_c monitor  --fixtures DIR | --firecrawl-dir DIR | --allow-network
"""
