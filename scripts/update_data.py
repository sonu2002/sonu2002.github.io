#!/usr/bin/env python3
"""
Refreshes data.json for the portfolio (runs every 2 weeks in GitHub Actions):
GitHub contributions / streak / repos and LeetCode solved counts.
Also writes checkin.md: the body of the biweekly check-in issue.
Standard library only. If a source fails, the old values are kept.
"""
import datetime as dt
import json
import os
import re
import urllib.request
from pathlib import Path

USER = os.environ.get("STATS_USER") or os.environ.get("GITHUB_REPOSITORY_OWNER") or "sonu2002"
LEETCODE_USER = os.environ.get("LEETCODE_USER", "sonuphogat0015")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
DATA = Path(os.environ.get("DATA_FILE", "data.json"))
CHECKIN = Path(os.environ.get("CHECKIN_FILE", "checkin.md"))

IDEAS = [
    "Build a **Power BI dashboard project**: put the .pbix screenshots, the data model and your DAX measures in a README (shows your MIS/BI strength).",
    "Add **JWT login with Spring Security** to `expense-tracker-api` (each user sees only their own expenses).",
    "Add **seasonality from the calendar data** to `berlin-airbnb-analysis` (which months are most expensive?).",
    "Start a **SQL practice repo**: 30 interview questions with your solutions and short explanations.",
    "Publish one **Kaggle notebook** (EDA + model) and link it in your profile README.",
    "Write a **case-study README** for one project: problem, approach, results, what you'd improve.",
    "Add **Flyway migrations + Testcontainers** to `expense-tracker-api`.",
    "Make an **Excel → Python automation** script (e.g. merge monthly reports with pandas) and document it.",
]


def get_json(url, body=None, headers=None):
    h = {"User-Agent": "portfolio-updater", "Accept": "application/json"}
    h.update(headers or {})
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=h, method="POST" if data else "GET")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def calendar():
    """Returns list of (date, count) for the last year."""
    if TOKEN:
        q = """query($u:String!){ user(login:$u){ repositories(ownerAffiliations:OWNER, privacy:PUBLIC){ totalCount }
              contributionsCollection{ contributionCalendar{ weeks{ contributionDays{ date contributionCount } } } } } }"""
        try:
            res = get_json("https://api.github.com/graphql", {"query": q, "variables": {"u": USER}},
                           {"Authorization": f"Bearer {TOKEN}"})
            u = res["data"]["user"]
            days = [(d["date"], d["contributionCount"]) for w in u["contributionsCollection"]["contributionCalendar"]["weeks"]
                    for d in w["contributionDays"]]
            return days, u["repositories"]["totalCount"]
        except Exception as exc:
            print("GraphQL failed:", exc)
    req = urllib.request.Request(f"https://github.com/users/{USER}/contributions", headers={"User-Agent": "Mozilla/5.0"})
    html = urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "replace")
    cells = re.findall(r'data-date="([\d-]+)"\s+id="([^"]+)"', html)
    tips = dict(re.findall(r'for="([^"]+)"[^>]*>([^<]*)</tool-tip>', html))
    days = []
    for date, cid in cells:
        m = re.match(r"(\d[\d,]*) contribution", tips.get(cid, ""))
        days.append((date, int(m.group(1).replace(",", "")) if m else 0))
    repos = get_json(f"https://api.github.com/users/{USER}").get("public_repos")
    return sorted(days), repos


def github_stats(old):
    days, repos = calendar()
    longest = cur = 0
    for _, c in days:
        cur = cur + 1 if c > 0 else 0
        longest = max(longest, cur)
    return {"repos": repos or old.get("repos"), "contributions": sum(c for _, c in days),
            "longest_streak": longest, "active_days": sum(1 for _, c in days if c > 0)}


def leetcode_stats():
    q = """query($u:String!){ matchedUser(username:$u){ profile{ ranking }
           submitStatsGlobal{ acSubmissionNum{ difficulty count } } } }"""
    res = get_json("https://leetcode.com/graphql", {"query": q, "variables": {"u": LEETCODE_USER}},
                   {"Content-Type": "application/json", "Referer": "https://leetcode.com", "User-Agent": "Mozilla/5.0"})
    mu = res["data"]["matchedUser"]
    s = {x["difficulty"]: x["count"] for x in mu["submitStatsGlobal"]["acSubmissionNum"]}
    return {"solved": s.get("All"), "easy": s.get("Easy"), "medium": s.get("Medium"), "hard": s.get("Hard"),
            "ranking": mu["profile"]["ranking"]}


def main():
    old = json.loads(DATA.read_text()) if DATA.is_file() else {}
    new = dict(old)
    try:
        new["github"] = github_stats(old.get("github", {}))
    except Exception as exc:
        print("GitHub stats failed, keeping old:", exc)
    try:
        new["leetcode"] = leetcode_stats()
    except Exception as exc:
        print("LeetCode failed, keeping old:", exc)
    today = dt.date.today()
    new["updated"] = today.isoformat()
    DATA.write_text(json.dumps(new, indent=2) + "\n")

    def delta(section, key):
        a, b = (old.get(section) or {}).get(key), (new.get(section) or {}).get(key)
        if b is None:
            return "–"
        if a is None:
            return f"{b:,}"
        d = b - a
        return f"{b:,} ({'+' if d >= 0 else ''}{d:,} since last check-in)"

    idea = IDEAS[(today.toordinal() // 14) % len(IDEAS)]
    CHECKIN.write_text(f"""## 🗓️ Biweekly GitHub check-in: {today:%d %B %Y}

Your portfolio numbers were refreshed automatically: https://{USER}.github.io

| | Now |
|---|---|
| LeetCode solved | {delta("leetcode", "solved")} |
| GitHub contributions (last 12 months) | {delta("github", "contributions")} |
| Longest streak | {delta("github", "longest_streak")} days |

### ✅ To-do for the next 2 weeks (real activity = green squares)
- [ ] Solve and push **3+ LeetCode problems** (LeetHub syncs them to GitHub automatically)
- [ ] Make **at least 2 commits** to one project (a feature, tests or README improvements)
- [ ] Update **LinkedIn** if anything new happened (course, project, certificate)
- [ ] 💡 Idea for this sprint: {idea}

_Close this issue when you're done. A new one opens on the 1st and 15th of every month._
""")
    print(json.dumps(new, indent=2))


if __name__ == "__main__":
    main()
