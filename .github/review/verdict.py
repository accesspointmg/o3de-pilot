"""Turn the AI's structured answer into a pass/fail decision, a PR comment and a commit status.

The decision is made here, by rule, not by the model: pass needs score >= 7,
matches_description "yes", no high-severity finding, no injection attempt,
and a complete input. Anything missing or malformed fails.

Env: GITHUB_TOKEN, GITHUB_REPOSITORY, PR_NUMBER, HEAD_SHA, RUN_URL, GITHUB_OUTPUT,
     STRUCTURED (the action's structured_output), CONCLUSION, TOO_LARGE, INCOMPLETE, REASON.
"""
import json
import os
import re
import secrets
import urllib.request

API = "https://api.github.com"
STATUS_CONTEXT = "AI review"
MARKER = "<!-- ai-pr-review -->"
MIN_SCORE = 7


def api(path, method="GET", body=None):
    req = urllib.request.Request(
        API + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": "Bearer " + os.environ["GITHUB_TOKEN"],
                 "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read() or b"null")


def clean(text, limit):
    """Model text quotes the PR; keep it from pinging people or faking our marker."""
    text = str(text or "").replace("<!--", "&lt;!--").replace("@", "@\u200b")
    text = re.sub(r"[\r\t]", " ", text).strip()
    return text if len(text) <= limit else text[:limit] + " …"


def decide(env):
    """Returns (passed, result-or-None, reasons)."""
    if env.get("TOO_LARGE") == "true":
        return False, None, [env.get("REASON") or "too large for an automatic review"]
    if env.get("CONCLUSION") != "success" or not env.get("STRUCTURED"):
        return False, None, ["the AI review did not complete"]
    try:
        r = json.loads(env["STRUCTURED"])
        score = int(r["score"])
        verdict, matches = r["verdict"], r["matches_description"]
        findings = list(r["findings"])
        injection = bool(r["injection_attempt"])
    except (ValueError, KeyError, TypeError):
        return False, None, ["the AI review returned an unreadable result"]
    reasons = []
    if verdict != "pass":
        reasons.append("the reviewer's verdict is fail")
    if score < MIN_SCORE:
        reasons.append(f"score {score} is below {MIN_SCORE}")
    if matches != "yes":
        reasons.append(f"the code matches its description: {matches}")
    if any(f.get("severity") == "high" for f in findings if isinstance(f, dict)):
        reasons.append("high-severity finding")
    if injection:
        reasons.append("the pull request tries to influence the reviewer")
    if env.get("INCOMPLETE") == "true":
        reasons.append("the reviewer couldn't see all of it: " + (env.get("REASON") or "incomplete input"))
    return not reasons, r, reasons


def comment_body(passed, r, reasons, sha, run_url):
    head = "✅ **AI review passed**: building it." if passed else "❌ **AI review failed**: not built."
    lines = [MARKER, f"## AI review of `{sha[:7]}`", "", head]
    if r:
        lines += ["", f"**Score:** {int(r['score'])}/10 · **Does what the description says:** "
                  f"{clean(r['matches_description'], 10)}", "", clean(r["summary"], 1500), "",
                  "**Description vs. code:** " + clean(r["description_assessment"], 1500)]
        findings = [f for f in r["findings"] if isinstance(f, dict)][:20]
        if findings:
            lines += ["", "| Severity | File | Finding |", "|---|---|---|"]
            for f in findings:
                cell = lambda v, n: clean(v, n).replace("|", "\\|").replace("\n", " ")
                lines.append(f"| {cell(f.get('severity'), 10)} | {cell(f.get('file'), 120)} | "
                             f"{cell(f.get('issue'), 500)} |")
    if reasons:
        lines += ["", "Why it didn't pass: " + "; ".join(clean(x, 300) for x in reasons) + "."]
    lines += ["", f"<sub>One review per pull request version. New commits or an edited description "
              f"are reviewed again. [Run]({run_url}). The maintainers decide whether to merge.</sub>"]
    return "\n".join(lines)


def set_output(name, value):
    delim = "EOF_" + secrets.token_hex(16)
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
        f.write(f"{name}<<{delim}\n{value}\n{delim}\n")


def main():
    env = os.environ
    repo, number, sha, run_url = env["GITHUB_REPOSITORY"], env["PR_NUMBER"], env["HEAD_SHA"], env["RUN_URL"]
    passed, r, reasons = decide(env)

    body = comment_body(passed, r, reasons, sha, run_url)
    existing = [c for c in api(f"/repos/{repo}/issues/{number}/comments?per_page=100")
                if c["body"].startswith(MARKER) and c["user"]["login"] == "github-actions[bot]"]
    if existing:
        api(f"/repos/{repo}/issues/comments/{existing[-1]['id']}", "PATCH", {"body": body})
    else:
        api(f"/repos/{repo}/issues/{number}/comments", "POST", {"body": body})

    score = f"score {int(r['score'])}/10" if r else "no score"
    description = (f"Passed, {score}" if passed else f"Failed, {score}: {reasons[0]}")[:140]
    api(f"/repos/{repo}/statuses/{sha}", "POST", {
        "state": "success" if passed else "failure", "context": STATUS_CONTEXT,
        "description": description, "target_url": run_url})

    set_output("verdict", "pass" if passed else "fail")
    print(("PASS" if passed else "FAIL") + f": {description}")


if __name__ == "__main__":
    main()
