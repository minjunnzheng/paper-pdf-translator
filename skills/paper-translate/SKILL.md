---
name: paper-translate
description: 把英文論文 PDF 翻成台灣繁體中文並保留原版面（圖、表、公式留在原位），輸出只有譯文或原文與譯文並排的 PDF。使用者要「翻譯這篇論文／這個 PDF」「做中英對照 PDF」「把 Zotero 裡這篇翻成中文」時使用。不用於純文字翻譯、摘要或導讀。
---

# paper-translate

呼叫 `paper-translate` 這個 CLI。它負責排版、術語保護、對照原文校對與機械檢查；你負責選引擎、先試兩頁、讀結果並如實回報。

## 執行方式

不必先 clone：

```sh
uvx --from git+https://github.com/minjunnzheng/paper-pdf-translator@v0.2.0 paper-translate <子指令>
```

第一次會下載約 900 MB 的相依套件。已經 clone 過 repo 的話，在該目錄用 `uv run paper-translate <子指令>`。不確定環境是否就緒時先跑 `doctor`。

## 選引擎

| 你在哪裡執行 | 用哪個 | 參數 |
|---|---|---|
| Codex | Codex 訂閱 | `--engine codex` |
| Claude Code | Claude 訂閱 | `--engine claude` |
| 使用者指定本機或另一台機器上的模型 | 本機模型 | `--model <ID> --base-url http://127.0.0.1:<埠>/v1`，另一台機器再加 `--remote-host <ssh 主機>` |

訂閱引擎會把論文內容送到該供應商，並消耗訂閱額度：每頁約 8 到 14 次請求。第一次使用時要告訴使用者這兩點。

## 流程

1. **先試兩頁。** 除非使用者明說要整篇，先用 `--pages` 跑兩頁有內文的頁面，把成品路徑給使用者看過再翻整篇。
2. **預設加 `--review`**（每批對照原文校對一次，請求數加倍）。使用者在意額度時可以不加。
3. 使用者要原文對照就加 `--bilingual`。
4. 使用者有要保留英文的術語時，請他提供術語檔，用 `--terms` 指定。格式見 repo 的 `terms.example.txt`。不要自己編術語清單。
5. 來源是 Zotero 時，用 `search`、`attachments` 找到 PDF 附件代碼，再用 `--attachment`。

```sh
paper-translate run --pdf paper.pdf --pages 1-2 --engine codex --review
paper-translate run --pdf paper.pdf --engine codex --review --bilingual
```

整篇論文通常要十幾到二十幾分鐘，請用足夠長的逾時或背景執行。

## 回報結果

執行結束會印出成品與 `manifest.json` 的路徑。回報時：

- 給成品的完整路徑。
- 讀 `manifest.json` 的 `llm_review`：有幾批、幾批沒通過檢查、原因是什麼。沒通過的批次保留的是未校對的初譯。
- 明說這些只是機械檢查（數字、公式佔位符、術語次數），沒有人核對過譯文是否正確。不要自己宣稱翻譯品質好。
- 指令失敗時回報原始錯誤訊息，不要改用別的方法硬翻。

## 限制

只支援有文字層的英文 PDF，譯文固定為台灣繁體中文；表格儲存格不翻，參考文獻不會被排除。完整說明見 repo 的 README。
