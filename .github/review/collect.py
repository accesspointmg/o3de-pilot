"""Collect a pull request as text for the AI review, and mark its head commit pending.

Runs from the base branch's copy (pr-review.yml copies it out of the checkout
before anything else touches the workspace). Uses only the standard library.

Env: GITHUB_TOKEN, GITHUB_REPOSITORY, PR_NUMBER, RUN_URL, REVIEW_DIR, GITHUB_OUTPUT.
Outputs: head_sha, prompt (empty if too large), too_large, incomplete, reason, claude_args.
"""
import json
import os
import secrets
import urllib.request

API = "https://api.github.com"
MAX_PROMPT_CHARS = 100_000      # the prompt reaches the action as one environment variable
STATUS_CONTEXT = "AI review"


def api(path, method="GET", body=None):
    req = urllib.request.Request(
        API + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": "Bearer " + os.environ["GITHUB_TOKEN"],
                 "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read() or b"null")


def set_output(name, value):
    delim = "EOF_" + secrets.token_hex(16)   # untrusted text can't end the block early
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
        f.write(f"{name}<<{delim}\n{value}\n{delim}\n")


def main():
    repo, number = os.environ["GITHUB_REPOSITORY"], os.environ["PR_NUMBER"]
    pr = api(f"/repos/{repo}/pulls/{number}")
    head_sha = pr["head"]["sha"]
    api(f"/repos/{repo}/statuses/{head_sha}", "POST", {
        "state": "pending", "context": STATUS_CONTEXT,
        "description": "AI review running", "target_url": os.environ.get("RUN_URL", "")})

    files, page = [], 1
    while True:
        batch = api(f"/repos/{repo}/pulls/{number}/files?per_page=100&page={page}")
        files += batch
        if len(batch) < 100:
            break
        page += 1

    incomplete = []
    parts = [
        f"Title: {pr['title']}",
        f"Author: {pr['user']['login']} (association with the repository: {pr['author_association']})",
        f"From: {pr['head']['repo']['full_name'] if pr['head']['repo'] else '(deleted fork)'} "
        f"branch {pr['head']['ref']} into {pr['base']['ref']}",
        f"Commits: {pr['commits']}, files changed: {pr['changed_files']}, "
        f"+{pr['additions']} -{pr['deletions']}",
        "",
        "Description:",
        pr["body"] or "(empty)",
        "",
        "Files:",
    ]
    parts += [f"- {f['status']} {f['filename']} (+{f['additions']} -{f['deletions']})" for f in files]
    if pr["changed_files"] > len(files):
        incomplete.append(f"only {len(files)} of {pr['changed_files']} files listed")
    parts += ["", "Diff:"]
    for f in files:
        if "patch" not in f:
            incomplete.append(f"no diff for {f['filename']} (binary or too large)")
            parts.append(f"--- {f['filename']}: NO DIFF SHOWN (binary or too large)")
            continue
        parts += [f"--- {f['filename']}", f["patch"]]

    nonce = secrets.token_hex(8)
    body = "\n".join(parts).replace(nonce, "")
    with open(os.path.join(os.environ["REVIEW_DIR"], "prompt.md"), encoding="utf-8") as fh:
        template = fh.read()
    template = template.replace("UNTRUSTED PULL REQUEST =====", f"UNTRUSTED PULL REQUEST {nonce} =====")
    if incomplete:
        body += "\n\nNOTE: THE INPUT IS INCOMPLETE: " + "; ".join(incomplete)
    prompt = template.replace("{repository}", repo).replace("{pull_request}", body)

    too_large = len(prompt) > MAX_PROMPT_CHARS
    reason = ""
    if too_large:
        reason = f"too large for an automatic review ({len(prompt):,} characters)"
    elif incomplete:
        reason = "; ".join(incomplete)
    with open(os.path.join(os.environ["REVIEW_DIR"], "schema.json"), encoding="utf-8") as fh:
        schema = json.dumps(json.load(fh), separators=(",", ":"))
    assert "'" not in schema
    # No tools at all: the PR is in the prompt as text, so Claude needs none, and
    # an injected instruction has nothing to act with (no files, no shell, no web).
    # --setting-sources user: never load project settings, hooks or CLAUDE.md
    # from the workspace, in case a pull request's files ever end up there.
    claude_args = (f"--model opus --max-turns 5 --tools \"\" --disallowedTools \"mcp__*\" "
                   f"--setting-sources user --json-schema '{schema}'")

    set_output("head_sha", head_sha)
    set_output("prompt", "" if too_large else prompt)
    set_output("claude_args", claude_args)
    set_output("too_large", "true" if too_large else "false")
    set_output("incomplete", "true" if incomplete else "false")
    set_output("reason", reason)
    print(f"PR #{number} head {head_sha}: {len(files)} files, prompt {len(prompt):,} chars"
          + (f"; {reason}" if reason else ""))


if __name__ == "__main__":
    main()
