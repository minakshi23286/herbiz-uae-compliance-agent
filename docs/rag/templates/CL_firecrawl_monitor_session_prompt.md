# HerBiz — scheduled Claude session prompt for Firecrawl-assisted monitoring (TEMPLATE, NOT SCHEDULED)

Business line: HomepreunerHub / HerBiz. Use only after the founder approves Firecrawl credits for monitoring (estimate in CL_HERBIZ_SOURCE_MONITORING_DESIGN.md §6).

1. In the C worktree, list the watch URLs:
   `python3 -c "from compliance_agent.rag_c import monitor as M; [print(i['url']) for i in M.watchlist() if i['kind']=='listing']"`
   (weekly run: listing pages only; full run only if the founder asked).
2. For each URL call firecrawl_scrape with exactly: formats ["markdown", "changeTracking", "links"], onlyMainContent false,
   zeroDataRetention true if the account allows it. Use the same options every time (changing them makes Firecrawl's comparison unreliable).
   Do not scrape any URL not on the list. Do not run crawls. Stop after the listed URLs.
3. Save each full JSON result to data/monitor/firecrawl/<YYYY-MM-DD>/<n>.json (never under data/raw/).
4. Run `python3 -m compliance_agent.rag_c monitor --firecrawl-dir data/monitor/firecrawl/<YYYY-MM-DD> --db data/CL_c_readonly_copy.sqlite3`.
5. Report the high and medium alerts to the founder. Do not collect, activate or edit the register; `discover --write` only if the founder asks.
