#!/usr/bin/env python3
"""
Update the group streak leaderboard in README.md.

Reads usernames from members.txt, fetches each member's contribution
calendar for the past year via the GitHub GraphQL API, computes:
  - current streak (consecutive days with >=1 contribution, ending today
    or yesterday so the streak isn't zeroed before you commit today)
  - longest streak within the past year
  - total contributions in the past year
then rewrites the table between the LEADERBOARD markers in README.md.

Requires env var GITHUB_TOKEN (provided automatically in GitHub Actions).
"""

import datetime as dt
import json
import os
import sys
import urllib.request

API_URL = "https://api.github.com/graphql"
README = "README.md"
MEMBERS_FILE = "members.txt"
START_MARK = "<!-- LEADERBOARD:START -->"
END_MARK = "<!-- LEADERBOARD:END -->"

QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays {
            date
            contributionCount
          }
        }
      }
    }
  }
}
"""


def fetch_calendar(login: str, token: str):
    payload = json.dumps({"query": QUERY, "variables": {"login": login}}).encode()
    req = urllib.request.Request(
        API_URL,
        data=payload,
        headers={
            "Authorization": f"bearer {token}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())
    if "errors" in data:
        raise RuntimeError(f"{login}: {data['errors'][0].get('message')}")
    cal = data["data"]["user"]["contributionsCollection"]["contributionCalendar"]
    days = [d for w in cal["weeks"] for d in w["contributionDays"]]
    days.sort(key=lambda d: d["date"])
    return cal["totalContributions"], days


def compute_streaks(days):
    """Return (current_streak, longest_streak) from a sorted day list."""
    today = dt.date.today().isoformat()

    # Longest streak in the window
    longest = run = 0
    for d in days:
        run = run + 1 if d["contributionCount"] > 0 else 0
        longest = max(longest, run)

    # Current streak: walk backwards from the last day.
    # If today has 0 contributions, skip it (streak isn't broken until
    # the day is over) and start counting from yesterday.
    current = 0
    idx = len(days) - 1
    if idx >= 0 and days[idx]["date"] == today and days[idx]["contributionCount"] == 0:
        idx -= 1
    while idx >= 0 and days[idx]["contributionCount"] > 0:
        current += 1
        idx -= 1
    return current, longest


def build_table(rows):
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    lines = [
        "| # | Member | 🔥 Current Streak | 🏅 Longest (1y) | 📦 Contributions (1y) |",
        "|---|--------|------------------:|----------------:|----------------------:|",
    ]
    for rank, r in enumerate(rows, start=1):
        badge = medals.get(rank, str(rank))
        lines.append(
            f"| {badge} | [@{r['login']}](https://github.com/{r['login']}) "
            f"| **{r['current']}** days | {r['longest']} days | {r['total']} |"
        )
    updated = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines.append("")
    lines.append(f"_Last updated: {updated}_")
    return "\n".join(lines)


def main():
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        sys.exit("GITHUB_TOKEN is not set")

    with open(MEMBERS_FILE) as f:
        members = [line.strip() for line in f if line.strip() and not line.startswith("#")]

    rows = []
    for login in members:
        try:
            total, days = fetch_calendar(login, token)
            current, longest = compute_streaks(days)
            rows.append({"login": login, "current": current, "longest": longest, "total": total})
        except Exception as e:
            print(f"WARNING: skipping {login}: {e}", file=sys.stderr)

    # Sort: current streak desc, then total contributions desc
    rows.sort(key=lambda r: (-r["current"], -r["total"]))
    table = build_table(rows)

    with open(README) as f:
        content = f.read()
    start = content.index(START_MARK) + len(START_MARK)
    end = content.index(END_MARK)
    new_content = content[:start] + "\n\n" + table + "\n\n" + content[end:]

    with open(README, "w") as f:
        f.write(new_content)
    print("Leaderboard updated.")


if __name__ == "__main__":
    main()
