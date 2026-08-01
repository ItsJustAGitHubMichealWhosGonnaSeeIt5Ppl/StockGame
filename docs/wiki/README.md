# Wiki drafts

These Markdown files are meant to be published as [GitHub Wiki](https://github.com/ItsJustAGitHubMichealWhosGonnaSeeIt5Ppl/StockGame/wiki) pages.

## How to publish

1. In the GitHub repo: **Settings → Features → Wikis** (enable if needed).
2. Open the wiki and create pages with the same titles as the filenames (without `.md`), or clone the wiki repo:

   ```bash
   git clone https://github.com/ItsJustAGitHubMichealWhosGonnaSeeIt5Ppl/StockGame.wiki.git
   cp docs/wiki/*.md /path/to/StockGame.wiki/
   # rename files to match wiki page titles if needed, then commit & push
   ```

Suggested wiki page titles:

| File | Wiki page title |
|------|-----------------|
| `Discord-Bot-Setup.md` | Discord Bot Setup |
| `Discord-Integrations.md` | Discord Integrations |
| `Alpaca-Setup.md` | Alpaca Setup |
| `Environment-Variables.md` | Environment Variables |
| `Home.md` | Home (optional wiki landing page) |

Screenshots for **Discord Integrations** live in [`images/`](images/) with descriptive filenames (for example `server-settings-integrations.png`). When publishing that page to the GitHub Wiki, include the matching files from `docs/wiki/images/` next to the page so the `images/...` links resolve — do not bulk-copy unrelated folders.
