# paper-pdf-translator

把英文論文 PDF 翻成台灣繁體中文，版面、圖、表、公式留在原位。翻譯可以交給自己機器上的模型，也可以交給 Claude 訂閱，不需要任何付費 API 金鑰。

排版由 [PDFMathTranslate-next](https://github.com/PDFMathTranslate/PDFMathTranslate-next) 與 [BabelDOC](https://github.com/funstory-ai/BabelDOC) 負責。這個工具在它們外面加了四件事：

- 翻譯請求改送本機模型或 Claude 訂閱 CLI。
- 指定的英文術語在翻譯前後原樣保留。
- 每段譯文可以再對照原文校對一次，並用機械檢查擋掉改到數字、公式或術語的譯文。
- 每次執行留下 manifest 與逐批紀錄，事後查得到哪一段沒通過檢查。

輸出有兩種：只有譯文的 PDF，或原文頁與譯文頁左右並排的 PDF。

> 譯文是機器產生的。工具只做機械檢查，不保證翻譯正確；引用或依賴內容前請對照原文。

## 需求

- macOS（只在 macOS 上測過）、Python 3.12、[uv](https://docs.astral.sh/uv/)
- 翻譯引擎，三選一：
  - 本機的 `llama-server`（GGUF）或 `mlx-vlm`，提供 OpenAI 相容介面
  - 另一台機器上的 `llama-server`，可用 SSH 金鑰登入
  - 已登入訂閱帳號的 [Claude Code CLI](https://claude.com/claude-code)（`claude` 指令）
- 使用 `--review` 時需要 ICU 的 `uconv`（`brew install icu4c`），用來把簡體字轉成繁體
- 想直接從 Zotero 取 PDF 時，Zotero 要開啟本機 API（設定 → 進階 → 允許其他應用程式與 Zotero 通訊）

## 安裝

```sh
git clone https://github.com/minjunnzheng/paper-pdf-translator.git
cd paper-pdf-translator
uv sync --locked
uv run paper-translate doctor
```

`doctor` 會列出各項相依是否就緒。排版引擎第一次執行時會下載版面模型與字型到 `~/.cache/babeldoc`。

## 使用

先用兩頁試跑，確認結果再翻整篇。`--pages` 是 PDF 的實體頁碼，從 1 起算。

### Claude 訂閱

```sh
uv run paper-translate run --pdf paper.pdf --pages 1-2 --engine claude --review
```

### 本機模型

```sh
uv run paper-translate run --pdf paper.pdf --pages 1-2 --review \
  --model <伺服器 /v1/models 回報的模型 ID> --base-url http://127.0.0.1:8080/v1
```

`--model` 與 `--base-url` 也可以用環境變數 `PAPER_TRANSLATE_MODEL`、`PAPER_TRANSLATE_BASE_URL` 設定。

### 另一台機器上的模型

```sh
uv run paper-translate run --pdf paper.pdf --pages 1-2 --review --lenient \
  --remote-host <ssh 主機名> --model <模型 ID> --base-url http://127.0.0.1:8080/v1
```

這裡的 `--base-url` 是伺服器在那台機器上的 loopback 位址。工具會自己開一條 SSH 通道（本機埠＝遠端埠加 10000），結束時關閉，並透過 SSH 計算模型檔的 SHA-256。遠端只支援 `llama-server`。

### 從 Zotero 取檔

```sh
uv run paper-translate search "關鍵字"
uv run paper-translate attachments <條目代碼>
uv run paper-translate run --attachment <PDF 附件代碼> --pages 1-2 --engine claude --review
```

只讀個人文獻庫，不會寫入 Zotero。

### 常用選項

| 選項 | 作用 |
|---|---|
| `--bilingual` | 輸出原文頁與譯文頁並排的 PDF |
| `--review` | 每批譯文再對照原文校對一次（請求數加倍） |
| `--lenient` | 校對沒通過檢查的批次保留初譯，照樣輸出 PDF；`--engine claude` 一律如此 |
| `--terms 檔案` | 要保留英文的術語清單，見下節 |
| `--engine-model 名稱` | Claude 的模型名，預設 `sonnet` |
| `--dry-run` | 只做檢查並印出設定，不送任何翻譯請求 |

## 術語檔

沒有術語檔時工具照常翻譯，只是不做術語保護。要保護術語，就把 `terms.example.txt` 複製一份改成自己領域的內容：

```text
your technical term
ABC
another term | 不要的譯法, 另一個不要的譯法
```

- 一行一個術語。翻譯前換成佔位符，翻完換回來，所以模型改不到它。
- 全大寫的詞視為縮寫，比對時區分大小寫。
- `|` 後面列的是要擋掉的錯譯：原文有這個術語、譯文卻出現這些寫法時，該段判定未過。
- 被 PDF 換行拆開的術語（例如 `SPECTRO- METRY`）會先接回去再比對。

## 檢查與紀錄

加 `--review` 後，每批校對過的譯文要通過下列檢查：

- 數字、公式佔位符、樣式標籤的數量和原文一致
- 術語檔裡的每個術語，出現次數和原文一致
- 沒有出現術語檔列為錯譯的寫法
- 原文是敘述句時，譯文不能整段還是英文
- 段落數與段落編號沒有被改動

本機模型預設採嚴格模式：任何一批沒過就停止，不輸出 PDF。加 `--lenient`（或使用 Claude）時，沒過的批次保留未校對的初譯，PDF 照樣輸出，失敗原因寫進 manifest。

每次執行的結果放在 `~/paper-translations/`（可用環境變數 `PAPER_TRANSLATE_OUTPUT` 改）下的一個工作目錄：

| 檔案 | 內容 |
|---|---|
| `translated.pdf` 或 `bilingual.pdf` | 成品 |
| `manifest.json` | 來源檔雜湊、所有設定、模型識別、通過與失敗的批次數、警告 |
| `review.json` | 每一批的原文、初譯、校對結果與錯誤訊息（有 `--review` 時） |

同樣的輸入和設定再跑一次會直接沿用既有成品，不重新翻譯。

## 資料流向與額度

- **本機與遠端模型**：只接受 loopback 位址，內容不離開你的機器（遠端模型則經由你自己的 SSH 通道）。執行時會移除環境裡的 OpenAI 金鑰與 proxy 設定。工具會核對伺服器回報的模型路徑並記錄模型檔的 SHA-256。
- **Claude 訂閱**：論文內容會送到 Anthropic。工具以 `claude -p` 呼叫、不給任何工具權限，並移除 `ANTHROPIC_API_KEY`，確保走訂閱登入而不是 API 計費。模型身分只能記錄「CLI 版本＋模型名」，無法驗證。
- **Claude 的用量**：排版引擎把一頁切成多批，每批是一次請求，加 `--review` 再加倍。實測每頁約 9 到 14 次請求，而且每次請求有幾千 tokens 的固定開場。整篇論文會用掉不少訂閱額度，請先用兩頁評估。
- **本機模型的取樣設定**：請求固定帶 `temperature: 0` 與 `presence_penalty: 0`。有些模型的伺服器預設值是為聊天調的（例如 presence penalty 1.5），會讓模型避開重複出現的術語、數字與佔位符，對翻譯不利。

## 實測

同一篇 13 頁、雙欄的英文期刊論文，整篇翻譯並開啟 `--review`，守門未過的批次保留初譯（2026-10-02）：

| 引擎 | 耗時 | 批次 | 校對後通過檢查 |
|---|---|---|---|
| Claude 訂閱（`sonnet`） | 15 分 15 秒 | 88 | 74 |
| 遠端 `llama-server`，Qwen3.8-Flash-Next Q4_K_XL，伺服器預設 presence penalty 1.5 | 22 分 46 秒 | 87 | 76 |
| 同上，請求帶 `presence_penalty: 0`（現行做法） | 22 分 29 秒 | 87 | 79 |

- 三次都輸出完整的 13 頁 PDF。沒通過的批次以「數字或公式佔位符數量不符」最多，其次是術語次數不符。
- 這是單篇論文、各跑一次的結果，樣本太小，不足以判斷哪個引擎翻得比較好。表中只有機械檢查的通過數，沒有人逐句比對過譯文。
- 測試當時使用一份 69 個詞的領域術語檔，校對提示詞也含有針對該篇論文的例子；目前版本的提示詞已改為通用寫法，數字可能不同。
- 遠端模型跑在一台有兩張 32 GB 顯示卡的機器上。

## 已知限制

- 只測過少數幾篇有文字層的英文期刊論文。掃描檔、文字層不足的頁面會被拒絕。
- 譯文語言固定為台灣繁體中文。
- 表格儲存格不翻譯。
- 參考文獻不會被排除，會一併送去處理。
- 版面模型可能誤判圖區與頁首；還原原圖的步驟不支援旋轉或裁切過的頁面。
- 機械檢查抓不到語意錯誤。術語保護只涵蓋你列在術語檔裡的詞。
- 相依套件版本固定在 `pdf2zh-next 2.9.0`、`babeldoc 0.6.2`、`pymupdf 1.25.2`；工具對 BabelDOC 做了兩處小範圍調整（拉丁字寬度、來源區域擷取），換版本可能失效。

## 開發

```sh
uv run python -m unittest discover -s tests
```

測試不送任何模型請求。

## 授權

AGPL-3.0-or-later，見 [LICENSE](LICENSE)。本工具依賴的 pdf2zh-next、BabelDOC 與 PyMuPDF 均以 AGPL-3.0 授權。

翻譯受著作權保護的論文前，請確認你的使用方式符合該論文的授權或所在地的合理使用規定；這個 repo 不包含任何論文或譯文。
