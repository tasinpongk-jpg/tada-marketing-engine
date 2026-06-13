#!/usr/bin/env python3
"""Email today's intel brief — the report's 'alert the team' step, using the
same Gmail app-password pattern as the IS1 dashboard's daily emails.

Env (set as GitHub secrets, same names as the IS1 repo):
    EMAIL_USERNAME      Gmail address that sends
    EMAIL_APP_PASSWORD  Gmail app password
    EMAIL_FROM          From header (usually same as EMAIL_USERNAME)
    EMAIL_TO            Recipient(s), comma-separated

Exits 0 quietly when the email env isn't configured, so the CI step is
optional. Usage: python3 notify.py [reports/intel-YYYY-MM-DD.md]
"""

import os
import smtplib
import sys
from datetime import datetime
from email.mime.text import MIMEText
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    user = os.environ.get("EMAIL_USERNAME")
    pwd = os.environ.get("EMAIL_APP_PASSWORD")
    to = os.environ.get("EMAIL_TO")
    if not (user and pwd and to):
        print("email not configured (EMAIL_USERNAME/EMAIL_APP_PASSWORD/"
              "EMAIL_TO) — skipping notify")
        return

    if len(sys.argv) > 1:
        brief = Path(sys.argv[1])
    else:
        briefs = sorted((HERE / "reports").glob("intel-*.md"))
        if not briefs:
            print("no intel brief found — skipping notify")
            return
        brief = briefs[-1]

    body = brief.read_text(encoding="utf-8")
    body += ("\n\n---\nFull dashboard: "
             "https://tada-marketing-dashboard.tasinpong-k.workers.dev\n")
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = (f"TADA competitor intel "
                      f"{datetime.now().strftime('%Y-%m-%d')} — {brief.name}")
    msg["From"] = os.environ.get("EMAIL_FROM", user)
    msg["To"] = to

    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as s:
        s.login(user, pwd)
        s.sendmail(msg["From"], [a.strip() for a in to.split(",")], msg.as_string())
    print(f"emailed {brief.name} to {to}")


if __name__ == "__main__":
    main()
