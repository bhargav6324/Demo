# Git Workflow: AI Service

This guide covers how the AI service was restored to GitHub, how the `ai` branch was set up, and how to work with it day to day.

- **Repo:** https://github.com/bhargav6324/Demo
- **Commands:** written for **PowerShell** on Windows. Git Bash differences are noted where they matter.

---

## 1. Repository layout

```
Demo/
├── README.md        ← overview table of all modules
├── backend/         ← backend API (port 8000)
├── ai_service/      ← AI service (port 8001)  ← this module
└── frontend/        ← frontend
```

| Branch | Purpose |
|---|---|
| `main` | The combined, working project. This is what gets demoed. Change it only through merges or pull requests. |
| `ai` | Day-to-day work on the AI service. |
| `frontend` | Day-to-day work on the frontend. |

**Golden rule:** each person commits only inside their own folder.

---

## 2. What went wrong (so it doesn't happen again)

| Commit | What happened |
|---|---|
| `99a0fa1` "Add smart library AI service" | The AI files were committed at the **repo root**, not inside a folder. |
| `e28db0c` "Resolve merge conflicts" | The AI `README.md` and `.gitignore` clashed with the backend's root files. |
| `4ff8171`, `0b45676` (two reverts) | Undoing the merge and the AI commit removed **everything**, so `main` ended up with 0 files. |

**Lessons:**
- Never put a module's files at the repo root.
- Don't use `git revert` to undo a merge on `main`.
- Nothing in git is really lost: every commit stays in history and can be restored.

---

## 3. How the AI service was restored

### Step 1: clone a fresh copy

The old local folder was left untouched as a backup.

```powershell
cd "C:\Users\fzdga\Downloads\smartlibrary - Copy"
git clone https://github.com/bhargav6324/Demo.git Demo
cd Demo
```

### Step 2: find the commit that had the latest AI code

```powershell
git log --oneline --all              # list commits, find "Add smart library AI service" -> 99a0fa1
git ls-tree -r --name-only 99a0fa1   # check which files that commit contains
```

### Step 3: export that commit into its own `ai_service/` folder

`git archive` packs a commit's files into a `.tar` without changing your branch. `tar` then unpacks them into the new folder.

```powershell
mkdir ai_service
git archive -o ..\ai_service.tar 99a0fa1
tar -xf ..\ai_service.tar -C ai_service
```

In **Git Bash**, add `--force-local`. Otherwise `tar` reads `C:` in a path as a network host:

```bash
tar --force-local -xf ../ai_service.tar -C ai_service
```

### Step 4: list the module in the root README

Add a row to the module table in `README.md`:

```
| AI service | [ai_service/](ai_service/) | Chat, RAG, recommendations, tool orchestration; ... |
```

### Step 5: check before committing

1. Make sure no secrets are going in. This command must print nothing; then search the same way for your API key.

   ```powershell
   git grep "GEMINI_API_KEY=." -- ai_service
   ```

2. Run the tests:

   ```powershell
   cd ai_service
   .\.venv\Scripts\python -m pytest -q
   cd ..
   ```

3. Stage only your folder and the README, then look at the list:

   ```powershell
   git add ai_service README.md
   git status
   ```

   It must **not** contain `.env`, `.venv`, `__pycache__`, `*.db` or `eval/report.json`.

### Step 6: commit and push

```powershell
git commit -m "Add AI service under ai_service/"
git push origin main
```

**When the push was rejected:** the first push failed because a teammate had pushed to `main` a few minutes earlier, restoring the backend with a newer version. We did **not** force-push. Instead, we put our change on top of theirs:

```powershell
git fetch origin
git reset --mixed origin/main               # move onto their latest commit, keeping our files on disk
git checkout origin/main -- backend README.md   # take THEIR backend and README exactly
git clean -fdq backend                      # remove leftover old backend files
# re-add the AI row to README.md, then:
git add ai_service README.md
git commit -m "Add AI service under ai_service/"
git push origin main
```

The normal, simpler way to handle a rejected push is:

```powershell
git pull --rebase origin main
git push origin main
```

---

## 4. How the `ai` branch was created

```powershell
cd "C:\Users\fzdga\Downloads\smartlibrary - Copy\Demo"
git checkout main          # start from main
git pull origin main       # make sure it's the latest (it already had backend + ai_service + frontend)
git checkout -b ai         # create the branch "ai" and switch to it
git push -u origin ai      # publish it to GitHub; -u links it so later you just type "git push"
git branch -vv             # check: "* ai ... [origin/ai]"
```

---

## 5. Everyday work on the `ai` branch

```powershell
cd "C:\Users\fzdga\Downloads\smartlibrary - Copy\Demo"
git checkout ai            # 1. be on your branch (git branch shows * next to the current one)
git pull                   # 2. get your latest work (e.g. pushed from another PC)

# 3. edit files inside ai_service\ ...

git add ai_service         # 4. stage only your folder
git status                 # 5. check what will be committed
git commit -m "Short description of the change"
git push                   # 6. send it to GitHub (origin/ai)
```

### Getting teammates' latest backend or frontend into your branch

```powershell
git checkout ai
git fetch origin
git merge origin/main      # brings in whatever was merged to main
git push
```

---

## 6. Merging `ai` into `main` (when a feature works)

Do this often, not only at the end: the demo runs from `main`.

### Recommended: a pull request on GitHub

1. Push your branch (`git push`).
2. On GitHub, go to **Pull requests** → **New pull request**.
3. Set **base: `main`** and **compare: `ai`**, then click **Create pull request**.
4. A teammate reviews it, then clicks **Merge pull request**.

### Command line alternative

```powershell
git checkout main
git pull origin main
git merge ai
git push origin main
git checkout ai            # go back to your branch
```

Because each module lives in its own folder, merges between `ai`, `frontend` and `main` should almost never conflict.

---

## 7. Running the AI service from this folder

```powershell
cd "C:\Users\fzdga\Downloads\smartlibrary - Copy\Demo\ai_service"
py -3.13 -m venv .venv
.\.venv\Scripts\python -m pip install torch --index-url https://download.pytorch.org/whl/cpu
.\.venv\Scripts\python -m pip install -r requirements.txt
copy .env.example .env     # then put your GEMINI_API_KEY in .env (never commit .env)
.\.venv\Scripts\python -m pytest -q
.\.venv\Scripts\python -m uvicorn app.main:app --port 8001
```

See [../README.md](../README.md) for the API and configuration.

---

## 8. Team rules

1. **Own folder only.** Commit only inside your module's folder; the shared root `README.md` table is the one exception.
2. **Pull before you push.** If a push is rejected, use `git pull --rebase`.
3. **Never `git push --force`** on `main` or on a teammate's branch.
4. **Never `git revert` a merge on `main`** to "undo" things. Ask the team first.
5. **Never commit `.env`**, API keys, `.venv/` or local databases. Check `git status` before every commit.
6. **Merge to `main` through pull requests**, so someone sees the change first.

---

## 9. Troubleshooting

| Problem | Fix |
|---|---|
| `! [rejected] ... (fetch first)` on push | `git pull --rebase origin <branch>`, then `git push` |
| Not sure which branch you're on | `git branch` (the `*` marks the current one) |
| Files disappeared after a pull or revert | They're still in history. Find the commit with `git log --oneline --all` and restore a file with `git checkout <commit> -- <path>` |
| Merge conflict | Open the files listed by `git status`, keep the right lines, delete the `<<<<<<<`, `=======` and `>>>>>>>` markers, then `git add <file>` and `git commit` |
| Committed something by mistake (not pushed yet) | `git reset --soft HEAD~1` (undoes the commit but keeps your changes) |
| `tar: Cannot connect to C:` in Git Bash | Add `--force-local` to the `tar` command |
