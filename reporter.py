from __future__ import annotations

import csv
import html
import json
import os
import re
import smtplib
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://zdsetf.com"
TZ = ZoneInfo("Asia/Taipei")
ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
REPORT_DIR = ROOT / "reports"
UA = "taiwan-active-etf-reporter/1.0 (+GitHub Actions)"


@dataclass(frozen=True)
class Holding:
    code: str
    name: str
    shares: int
    weight: float
    market_value_100m: float | None = None


def get_soup(url: str) -> BeautifulSoup:
    response = requests.get(url, headers={"User-Agent": UA}, timeout=30)
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


def discover_active_etfs(soup: BeautifulSoup | None = None) -> dict[str, str]:
    soup = soup or get_soup(f"{BASE_URL}/")
    result: dict[str, str] = {}
    for option in soup.select("select option[value]"):
        ticker = option.get("value", "").strip().upper()
        if re.fullmatch(r"\d{5}A", ticker):
            # The source uses optional closing tags; get_text() may include every
            # following option when parsed as HTML. The first text node is the label.
            label = str(option.contents[0]).strip() if option.contents else ticker
            result[ticker] = re.sub(rf"^{ticker}\s*[·・-]?\s*", "", label).strip() or ticker
    # Fallback for temporary/minified versions of the landing page.
    for link in soup.select('a[href*="/etf/"]'):
        match = re.search(r"/etf/(\d{5}A)(?:$|[/?#])", link.get("href", ""), re.I)
        if match:
            ticker = match.group(1).upper()
            result.setdefault(ticker, ticker)
    if not result:
        raise RuntimeError("找不到主動式 ETF 清單，來源頁格式可能已變更")
    return dict(sorted(result.items()))


def parse_holdings(soup: BeautifulSoup) -> list[Holding]:
    for table in soup.find_all("table"):
        headers = [th.get_text(" ", strip=True) for th in table.find_all("th")]
        if headers[:4] != ["代號", "名稱", "股數", "權重(%)"]:
            continue
        holdings: list[Holding] = []
        for row in table.find_all("tr")[1:]:
            cells = [td.get_text(" ", strip=True) for td in row.find_all("td")]
            if len(cells) < 4:
                continue
            shares = int(cells[2].replace(",", ""))
            market_value = float(cells[4].replace(",", "")) if len(cells) > 4 and cells[4] not in {"", "-"} else None
            holdings.append(Holding(cells[0], cells[1], shares, float(cells[3]), market_value))
        if holdings:
            return holdings
    raise RuntimeError("找不到完整持股表，來源頁格式可能已變更")


def fetch_holdings(ticker: str) -> list[Holding]:
    return parse_holdings(get_soup(f"{BASE_URL}/etf/{ticker}"))


def load_previous(ticker: str) -> list[Holding]:
    path = DATA_DIR / "latest" / f"{ticker}.json"
    if not path.exists():
        return []
    return [Holding(**item) for item in json.loads(path.read_text(encoding="utf-8"))["holdings"]]


def save_snapshot(ticker: str, name: str, holdings: list[Holding], stamp: str) -> None:
    payload = {"ticker": ticker, "name": name, "date": stamp, "source": f"{BASE_URL}/etf/{ticker}", "holdings": [asdict(x) for x in holdings]}
    for path in (DATA_DIR / stamp / f"{ticker}.json", DATA_DIR / "latest" / f"{ticker}.json"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    csv_path = DATA_DIR / stamp / f"{ticker}.csv"
    with csv_path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(asdict(holdings[0]).keys()))
        writer.writeheader()
        writer.writerows(asdict(x) for x in holdings)


def diff(previous: list[Holding], current: list[Holding]) -> list[dict]:
    old = {x.code: x for x in previous}
    new = {x.code: x for x in current}
    rows = []
    for code in sorted(old.keys() | new.keys()):
        before, after = old.get(code), new.get(code)
        if before is None:
            kind = "新增"
        elif after is None:
            kind = "刪除"
        elif before.shares == after.shares and abs(before.weight - after.weight) < 0.0001:
            continue
        else:
            kind = "增持" if after.shares > before.shares else "減持" if after.shares < before.shares else "權重變動"
        rows.append({"kind": kind, "code": code, "name": (after or before).name, "shares_before": before.shares if before else 0, "shares_after": after.shares if after else 0, "weight_before": before.weight if before else 0, "weight_after": after.weight if after else 0})
    return rows


def render_report(stamp: str, results: dict, failures: dict) -> str:
    def n(value: int) -> str:
        return f"{value:,}"
    sections = []
    total_changes = 0
    for ticker, item in results.items():
        changes = item["changes"]
        total_changes += len(changes)
        if changes:
            rows = "".join(f"<tr><td>{html.escape(x['kind'])}</td><td>{html.escape(x['code'])} {html.escape(x['name'])}</td><td>{n(x['shares_before'])} → {n(x['shares_after'])}</td><td>{x['weight_before']:.2f}% → {x['weight_after']:.2f}%</td></tr>" for x in changes)
        else:
            rows = '<tr><td colspan="4">無變動，或這是第一次建立快照</td></tr>'
        top = "、".join(f"{html.escape(x.name)} {x.weight:.2f}%" for x in item["holdings"][:5])
        sections.append(f"<section><h2>{ticker} {html.escape(item['name'])}</h2><p>共 {len(item['holdings'])} 檔；前五大：{top}</p><table><thead><tr><th>類型</th><th>標的</th><th>股數</th><th>權重</th></tr></thead><tbody>{rows}</tbody></table></section>")
    failed = "" if not failures else "<h2>抓取失敗</h2><ul>" + "".join(f"<li>{html.escape(k)}：{html.escape(v)}</li>" for k, v in failures.items()) + "</ul>"
    return f"""<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><style>body{{font-family:Arial,'Noto Sans TC',sans-serif;max-width:1000px;margin:auto;color:#172033}}h1{{color:#0d6b5f}}section{{margin:24px 0}}table{{border-collapse:collapse;width:100%}}th,td{{padding:8px;border-bottom:1px solid #ddd;text-align:left}}th{{background:#eef7f5}}.muted{{color:#657080}}</style></head><body><h1>台灣主動式 ETF 每日持股報告</h1><p class="muted">資料日期 {stamp}｜成功 {len(results)} 檔｜異動 {total_changes} 筆｜失敗 {len(failures)} 檔</p>{failed}{''.join(sections)}<p class="muted">資料來源為公開資訊彙整頁，僅供研究參考，不構成投資建議。</p></body></html>"""


def send_email(subject: str, body: str) -> None:
    username = os.environ.get("GMAIL_USERNAME")
    password = os.environ.get("GMAIL_APP_PASSWORD")
    recipient = os.environ.get("GMAIL_TO", username or "")
    if not username or not password or not recipient:
        print("未設定 Gmail secrets，跳過寄信（報告仍已產生）")
        return
    message = EmailMessage()
    message["Subject"], message["From"], message["To"] = subject, username, recipient
    message.set_content("此郵件包含 HTML 格式的台灣主動式 ETF 每日持股報告。")
    message.add_alternative(body, subtype="html")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as smtp:
        smtp.login(username, password)
        smtp.send_message(message)


def main() -> int:
    now = datetime.now(TZ)
    stamp = now.date().isoformat()
    only = {x.strip().upper() for x in os.environ.get("ETF_TICKERS", "").split(",") if x.strip()}
    # Explicit tickers also make a useful escape hatch if the discovery page is down.
    names = {ticker: ticker for ticker in sorted(only)} if only else discover_active_etfs()
    results, failures = {}, {}
    for ticker, name in names.items():
        try:
            previous = load_previous(ticker)
            holdings = fetch_holdings(ticker)
            changes = diff(previous, holdings)
            save_snapshot(ticker, name, holdings, stamp)
            results[ticker] = {"name": name, "holdings": holdings, "changes": changes}
            print(f"{ticker}: {len(holdings)} holdings, {len(changes)} changes")
        except Exception as exc:
            failures[ticker] = str(exc)
            print(f"{ticker}: ERROR {exc}", file=sys.stderr)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report = render_report(stamp, results, failures)
    (REPORT_DIR / "latest.html").write_text(report, encoding="utf-8")
    (REPORT_DIR / f"{stamp}.html").write_text(report, encoding="utf-8")
    send_email(f"主動式 ETF 每日持股｜{stamp}｜異動 {sum(len(x['changes']) for x in results.values())} 筆", report)
    return 1 if not results else 0


if __name__ == "__main__":
    raise SystemExit(main())
