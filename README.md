# paper-pdf-translator

[English](#english) · [中文](#中文)

## English

Translate English research-paper PDFs into Traditional Chinese (Taiwan). The layout, figures, tables and formulas stay in place. The translation can run on a model on your own machine, or on a Claude or ChatGPT (Codex) subscription. No paid API key is necessary.

[PDFMathTranslate-next](https://github.com/PDFMathTranslate/PDFMathTranslate-next) and [BabelDOC](https://github.com/funstory-ai/BabelDOC) do the layout. This tool adds four things:

- It sends the translation requests to a local model, or to the Claude Code or Codex subscription CLI.
- It keeps the English terms that you list unchanged in the translation.
- With `--review`, it checks each batch against the source text a second time. Mechanical checks then reject a batch if the numbers, formula placeholders or listed terms changed.
- Each run writes a manifest and a log for each batch, so you can find which batch failed a check.

The output is a translated PDF, or a PDF with source pages and translated pages side by side (`--bilingual`). `--format pages` writes a web page instead: each source page as a row, with the translation on the left, the original page as an image beside it, and a question panel on the right that `paper-translate serve` connects to the same engine. Hovering a translated paragraph frames its position on the original page. The page format also takes other languages with `--from` and `--to` (English, Traditional and Simplified Chinese, Japanese, Korean, German, Spanish, French).

A model server on another machine can be used over SSH with `--remote-host`. The repository is also a Codex and Claude Code plugin: its skill lets the agent run the tool, try two pages first and report the checks.

Requirements: macOS (the only tested platform), Python 3.12, [uv](https://docs.astral.sh/uv/), and one translation engine: a local or remote `llama-server`, the [Claude Code CLI](https://claude.com/claude-code), or the [Codex CLI](https://github.com/openai/codex).

```sh
git clone https://github.com/minjunnzheng/paper-pdf-translator.git
cd paper-pdf-translator
uv sync --locked
uv run paper-translate doctor

# Try two pages first, then translate the full paper.
uv run paper-translate run --pdf paper.pdf --pages 1-2 --engine claude --review
uv run paper-translate run --pdf paper.pdf --pages 1-2 --engine codex --review
```

Limits:

- The output language is Traditional Chinese only.
- The translation is machine output. The checks are mechanical and do not find errors of meaning. Compare with the source before you cite or rely on the text.
- Table cells are not translated. The reference list is not translated by default (`--translate-references` turns it on).
- A subscription engine sends the paper text to Anthropic or OpenAI. A page uses approximately 8 to 14 requests, and `--review` doubles the number of requests.

The full documentation below is in Chinese. License: AGPL-3.0-or-later.

## 中文

把英文論文 PDF 翻成台灣繁體中文，版面、圖、表、公式留在原位。翻譯可以交給自己機器上的模型，也可以交給 Claude 或 ChatGPT（Codex）訂閱，不需要任何付費 API 金鑰。

排版由 [PDFMathTranslate-next](https://github.com/PDFMathTranslate/PDFMathTranslate-next) 與 [BabelDOC](https://github.com/funstory-ai/BabelDOC) 負責。這個工具在它們外面加了四件事：

- 翻譯請求改送本機模型，或 Claude、Codex 的訂閱 CLI。
- 指定的英文術語在翻譯前後原樣保留。
- 每段譯文可以再對照原文校對一次，並用機械檢查擋掉改到數字、公式或術語的譯文。
- 每次執行留下 manifest 與逐批紀錄，事後查得到哪一段沒通過檢查。

輸出有三種：只有譯文的 PDF、原文頁與譯文頁左右並排的 PDF，以及「左譯文、右原文整頁」的網頁（可在網頁右側直接問 AI）。

> 譯文是機器產生的。工具只做機械檢查，不保證翻譯正確；引用或依賴內容前請對照原文。

## 需求

- macOS（只在 macOS 上測過）、Python 3.12、[uv](https://docs.astral.sh/uv/)
- 翻譯引擎，四選一：
  - 本機的 `llama-server`（GGUF）或 `mlx-vlm`，提供 OpenAI 相容介面
  - 另一台機器上的 `llama-server`，可用 SSH 金鑰登入
  - 已登入訂閱帳號的 [Claude Code CLI](https://claude.com/claude-code)（`claude` 指令）
  - 已登入 ChatGPT 帳號的 [Codex CLI](https://github.com/openai/codex)（`codex` 指令）
- 使用 `--review` 或 `--format pages` 時需要 ICU 的 `uconv`（`brew install icu4c`），用來把簡體字轉成繁體
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

### Codex（ChatGPT 訂閱）

```sh
uv run paper-translate run --pdf paper.pdf --pages 1-2 --engine codex --review
```

每個請求用 `codex exec` 送出：唯讀沙箱、不保留對話、推理強度固定為 `low`。模型預設是你 Codex 設定檔裡的那個，可用 `--engine-model` 指定。

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

### 左譯文、右原文整頁的網頁，加上問答欄

```sh
uv run paper-translate run --pdf paper.pdf --format pages --engine claude --review
uv run paper-translate serve <上一步印出的輸出目錄>
```

`--format pages` 不經排版引擎：用 PyMuPDF 逐段抽出文字翻譯，輸出一個 `translated.html`。每一頁一列，左邊是該頁譯文，中間是原文整頁的圖（圖、表、公式都是原樣），右邊是問答欄。整篇論文約 30 次請求，比 PDF 輸出少很多；代價是左邊譯文沒有原排版，表格會被拆成零碎小段，要對照中間的原文頁看。

直接打開 `translated.html` 可以閱讀，但不能問答。要問答就用 `serve`：它在 `127.0.0.1` 開一個只有本機連得到的小伺服器並打開瀏覽器，問答欄送出的問題由它轉給翻譯時用的引擎（也可用 `--engine` 指定別的）。

- 滑鼠移到左邊某段譯文，中間的原文頁會框出它的位置；點一下可固定，固定的那段也會被帶進問題。
- 圖或表裡印的字（圖例、地名、軸標題）依字級辨認，收在每頁的「圖表內的文字」清單，短的照樣翻、長的（例如表格內文）不翻。
- 每個問題會附上當頁的原文與譯文；先點左邊某一段，則再附上那一段；勾「帶全文」則附上整篇。
- 會附上最近三則問答，方便追問。
- 問答存在輸出目錄的 `qa.json`，下次 `serve` 還在。
- 每個問題一次請求；用訂閱引擎時，問題與所附的論文內容會送到該供應商。
- 伺服器只接受本機連線，API 需要每次啟動時產生的金鑰（已放在開啟的網址裡），按 Ctrl+C 結束。

### 其他語言（只限 `--format pages`）

網頁格式不用把譯文塞回原排版，所以可以換語言：`--from` 是論文的語言，`--to` 是譯文的語言。可選 `en`、`zh-TW`、`zh-CN`、`ja`、`ko`、`de`、`es`、`fr`，預設是 `en` 翻 `zh-TW`。

```sh
uv run paper-translate run --pdf paper.pdf --format pages --to zh-CN --engine claude --review
uv run paper-translate run --pdf 論文.pdf --format pages --from ja --engine claude --review
```

- 譯成繁中或簡中時，會再用 `uconv` 統一成對應的字體。
- 校對後的檢查改看「譯文是否真的是目標語言」：例如譯成中文時不能留下日文假名或韓文。
- 參考文獻標題另外認得德、法、西、日、韓、中文的常見寫法。
- 問答欄用譯文的語言回答；頁面上的按鈕與說明文字仍是中文。
- PDF 輸出（預設格式）仍只支援英翻台灣繁中。

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
| `--format pages` | 輸出左譯文、右原文整頁的網頁，搭配 `serve` 問答 |
| `--from`、`--to` | 原文與譯文的語言（只限 `--format pages`） |
| `--bilingual` | 輸出原文頁與譯文頁並排的 PDF |
| `--review` | 每批譯文再對照原文校對一次（請求數加倍） |
| `--lenient` | 校對沒通過檢查的批次保留初譯，照樣輸出 PDF；`--engine claude` 與 `codex` 一律如此 |
| `--terms 檔案` | 要保留英文的術語清單，見下節 |
| `--translate-references` | 連參考文獻一起翻（預設不翻，見「已知限制」） |
| `--engine-model 名稱` | 訂閱 CLI 的模型名；Claude 預設 `sonnet`，Codex 預設用它設定檔裡的模型 |
| `--dry-run` | 只做檢查並印出設定，不送任何翻譯請求 |

## 當成 agent 外掛使用

repo 內附一個薄 skill（`skills/paper-translate/`）和外掛 manifest，讓 Codex 或 Claude Code 能用一句話叫它：agent 會選對應的訂閱引擎、先試兩頁、再回報檢查結果。skill 用 `uvx` 直接從這個 repo 執行 CLI，不必先 clone。

- Codex：manifest 在 `.codex-plugin/plugin.json`。把這個 repo 加成外掛市集（`codex plugin marketplace add minjunnzheng/paper-pdf-translator`）後安裝 `paper-pdf-translator`。
- Claude Code：manifest 在 `.claude-plugin/`。`/plugin marketplace add minjunnzheng/paper-pdf-translator`，再 `/plugin install paper-pdf-translator@paper-pdf-translator`。

在 Codex 裡實測過安裝與整篇翻譯，有兩點要注意：

- Codex 的預設沙箱會擋下 `uv` 的套件快取與巢狀的 `codex exec`，需要讓 Codex 提升權限才跑得動。
- 開著自動核准審查時，指令裡要明講同意把論文全文送到 OpenAI，否則審查會擋下來等你確認。

Claude Code 的外掛安裝流程尚未實測。CLI 本身不依賴外掛，照上面的方式直接執行即可。

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

- 數字、公式佔位符、樣式標籤的數量和原文一致（英文原文的 one、two、first、second 等數詞，譯文寫成阿拉伯數字時不算多出來，因為日文、韓文習慣這樣寫）
- 術語檔裡的每個術語，出現次數和原文一致
- 沒有出現術語檔列為錯譯的寫法
- 原文是敘述句時，譯文不能整段還是英文
- 段落數與段落編號沒有被改動

本機模型預設採嚴格模式：任何一批沒過就停止，不輸出 PDF。加 `--lenient`（或使用 Claude、Codex）時，沒過的批次保留未校對的初譯，PDF 照樣輸出，失敗原因寫進 manifest。

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
- **Codex 訂閱**：論文內容會送到 OpenAI。工具以 `codex exec` 呼叫，唯讀沙箱、不保留對話，走 ChatGPT 登入而不是 API 金鑰。模型身分同樣只能記錄「CLI 版本＋模型名」。
- **訂閱的用量**：排版引擎把一頁切成多批，每批是一次請求，加 `--review` 再加倍。實測每頁約 8 到 14 次請求，而且每次請求有固定的開場開銷（Claude CLI 實測約幾千 tokens）。整篇論文會用掉不少訂閱額度，請先用兩頁評估。
- **本機模型的取樣設定**：請求固定帶 `temperature: 0` 與 `presence_penalty: 0`。有些模型的伺服器預設值是為聊天調的（例如 presence penalty 1.5），會讓模型避開重複出現的術語、數字與佔位符，對翻譯不利。

## 實測

同一篇 13 頁、雙欄的英文期刊論文，整篇翻譯並開啟 `--review`，守門未過的批次保留初譯（2026-10-02）：

| 引擎 | 耗時 | 批次 | 校對後通過檢查 |
|---|---|---|---|
| Claude 訂閱（`sonnet`） | 15 分 15 秒 | 88 | 74 |
| 遠端 `llama-server`，Qwen3.8-Flash-Next Q4_K_XL，伺服器預設 presence penalty 1.5 | 22 分 46 秒 | 87 | 76 |
| 同上，請求帶 `presence_penalty: 0`（現行做法） | 22 分 29 秒 | 87 | 79 |

- 這三次是 0.1 版的結果，當時參考文獻也一併翻譯；現在預設跳過，這篇論文的參考文獻約佔全文文字的兩成。
- 三次都輸出完整的 13 頁 PDF。沒通過的批次以「數字或公式佔位符數量不符」最多，其次是術語次數不符。
- 這是單篇論文、各跑一次的結果，樣本太小，不足以判斷哪個引擎翻得比較好。表中只有機械檢查的通過數，沒有人逐句比對過譯文。
- 測試當時使用一份 69 個詞的領域術語檔，校對提示詞也含有針對該篇論文的例子；目前版本的提示詞已改為通用寫法，數字可能不同。
- 遠端模型跑在一台有兩張 32 GB 顯示卡的機器上。

同一篇論文的其中兩頁，不帶術語檔、開啟 `--review`，使用目前版本的通用提示詞：

| 引擎 | 耗時 | 批次 | 校對後通過檢查 |
|---|---|---|---|
| Codex 訂閱（Codex 設定的預設模型，推理強度 `low`） | 4 分 19 秒 | 8 | 8 |
| Claude 訂閱（`sonnet`） | 2 分 41 秒 | 10 | 8 |
| 遠端 `llama-server`，Qwen3.8-Flash-Next Q4_K_XL | 3 分 15 秒 | 9 | 8 |

兩頁、各跑一次，只能說明三條路都跑得通，不能用來比較翻譯品質。

## 已知限制

- 只測過少數幾篇有文字層的英文期刊論文。掃描檔、文字層不足的頁面會被拒絕。
- PDF 輸出的譯文語言固定為台灣繁體中文；其他語言只限網頁格式。英翻簡中用真實論文測過兩頁，英翻日、韓、德、西、法各測過一頁；日、韓、德、西、法、中文作為原文時，只用自編的一頁測試文字驗證過流程，沒有用真實論文測過。
- 術語檔的比對依英文的字詞邊界設計，原文是日、韓、中文時術語保護不可靠。
- 表格儲存格不翻譯。
- 參考文獻預設不翻：工具找文末的 `References`（或 `Bibliography`、`Literature cited` 等）標題，標題之後到文件結尾的段落原樣保留，也不送給模型。放在參考文獻後面的附錄因此也不會被翻；找不到標題時則照舊全部翻譯。兩種情況都記在 manifest 的 `references` 欄。
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
