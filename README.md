# 台灣主動式 ETF 持有金額前 30 名通報

每天盤後自動找出台灣股票型主動式 ETF、擷取完整持股，將同一股票在不同 ETF 的持有市值合併加總，並把持有金額最高的 30 檔股票寄送到 Gmail。完整 JSON/CSV 歷史仍會保留在 GitHub。

## 功能

- 自動發現代號尾碼為 `A` 的股票型主動式 ETF，不用手動維護清單
- 依股票代號彙總所有主動式 ETF 的持有市值
- 通報合計持有金額最高的 30 檔股票，並顯示持有 ETF 數量
- 每檔 ETF 仍保存完整 JSON 與 Excel 可直接開啟的 UTF-8 CSV
- 個別 ETF 抓取失敗不會中止其他標的，信中列出失敗原因
- GitHub Actions 週一至週五台灣時間 17:30 自動執行，也可手動執行

## GitHub 設定

在 repository 的 **Settings → Secrets and variables → Actions** 新增：

| 類型 | 名稱 | 值 |
|---|---|---|
| Secret | `GMAIL_USERNAME` | 寄件 Gmail，例如 `you@gmail.com` |
| Secret | `GMAIL_APP_PASSWORD` | Google 帳戶開啟兩步驟驗證後產生的 16 碼應用程式密碼 |
| Secret | `GMAIL_TO` | 收件信箱，可與寄件信箱相同 |

請勿填入一般 Gmail 登入密碼。若只想追蹤部分標的，可新增 Repository variable `ETF_TICKERS`，值如 `00981A,00982A`；留白即追蹤全部。

到 **Actions → Daily active ETF report → Run workflow** 手動測試。通報會直接依當日完整持股統計前 30 名，因此第一次執行即可產生排名。

## 本機執行與測試

```bash
python -m pip install -r requirements.txt pytest
pytest -q
python reporter.py
```

未設定 Gmail 環境變數時不會寄信，但仍會在 `reports/latest.html` 產生報告。

## 資料與限制

名單依公開頁面動態取得，持股快照來自 [主動式 ETF 持股追蹤](https://zdsetf.com/)，原始揭露責任仍屬各投信。網站版型改動時解析器可能需要更新；本專案會明確回報錯誤，不會把空資料覆蓋成有效快照。資料僅供研究參考，不構成投資建議。
