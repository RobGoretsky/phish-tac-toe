# Enabling the live setlist feed

`refresh.workflow.yml` belongs at `.github/workflows/refresh.yml`. It isn't there because
the token this repo was pushed with lacks the **Workflows** permission, and GitHub rejects
any push that creates a workflow file without it.

Two ways to install it (either is fine, takes a minute):

**A — via the web UI (no permission change needed)**
1. On GitHub: *Add file → Create new file*
2. Name it `.github/workflows/refresh.yml`
3. Paste the contents of `deploy/refresh.workflow.yml`, commit to `main`
4. Delete this `deploy/` folder if you like

**B — grant the token the permission**
Settings → Developer settings → Fine-grained tokens → your token → Repository permissions →
**Workflows: Read and write**. Then `git mv deploy/refresh.workflow.yml .github/workflows/refresh.yml`
and push.

## Then check
- **Actions** tab → *Refresh setlist* → *Run workflow* to confirm it can commit.
- **Settings → Pages** → Source: *Deploy from a branch*, branch `main`, folder `/ (root)`.

Without the workflow the boards still work, but `data/setlist.json` never updates —
you'd be playing entirely on Manual entry.
