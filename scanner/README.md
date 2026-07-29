# Prompt-Injection & Jailbreak Scanner

> ⚡ An offensive security CLI tool that fires known prompt-injection and jailbreak payloads at any OpenAI-compatible LLM endpoint, judges results using Gemini as an LLM-as-judge, and outputs a structured JSON report with an interactive HTML dashboard viewer.

---

## Features

- **40 curated payloads** across 6 OWASP LLM Top 10 categories
- **Async concurrent scanning** with configurable rate limiting
- **LLM-as-judge scoring** using Gemini API (no brittle keyword matching)
- **Structured JSON reports** with per-category breakdown
- **Self-contained HTML dashboard** — dark UI, no server required
- **Rich CLI output** with progress bars, colored verdicts, and severity ratings

## Quick Start

### 1. Install Dependencies

```bash
cd scanner
pip install -r requirements.txt
```

### 2. Set API Keys

```bash
# Required: Gemini API key for the judge
export GEMINI_API_KEY="your-gemini-api-key"

# Optional: Target API key (can also use --api-key flag)
export TARGET_API_KEY="your-target-api-key"
```

Or create a `.env` file (already in `.gitignore`):

```
GEMINI_API_KEY=your-gemini-api-key
TARGET_API_KEY=your-target-api-key
```

### 3. Run a Scan

```bash
# Scan an OpenAI-compatible endpoint
python scanner.py --target https://api.openai.com/v1/chat/completions \
                  --api-key sk-... \
                  --model gpt-3.5-turbo

# Scan a local LLM app
python scanner.py --target http://localhost:8000/v1/chat/completions \
                  --model my-model \
                  --concurrency 10

# Custom payloads and output
python scanner.py --target https://api.yourapp.com/chat \
                  --payloads custom_payloads.yaml \
                  --output my_scan.json
```

### 4. View the Report

Open `viewer/report_viewer.html` in your browser and load the generated `report.json` file.

---

## CLI Reference

```
python scanner.py --help
```

| Flag | Default | Description |
|------|---------|-------------|
| `--target` | *(required)* | Target API endpoint URL |
| `--api-key` | `TARGET_API_KEY` env | API key for the target |
| `--model` | `gpt-3.5-turbo` | Model name at the target |
| `--payloads` | `payloads.yaml` | Path to payload library |
| `--output` | `report.json` | Output report path |
| `--concurrency` | `5` | Max concurrent requests |
| `--timeout` | `30` | Per-request timeout (seconds) |
| `--system-prompt` | *none* | System prompt for target requests |
| `--judge-model` | `gemini-2.0-flash` | Gemini model for judging |

---

## Project Structure

```
scanner/
├── scanner.py            # CLI entry point & orchestrator
├── runner.py             # Async attack engine (aiohttp)
├── judge.py              # LLM-as-judge scoring (Gemini API)
├── report.py             # JSON report builder
├── payloads.yaml         # Curated payload library (40 payloads)
├── requirements.txt      # Python dependencies
├── .gitignore
├── README.md
└── viewer/
    └── report_viewer.html  # Self-contained HTML dashboard
```

## Payload Categories

| Category | Count | Description |
|----------|-------|-------------|
| Direct Prompt Injection | 8 | Classic "ignore previous instructions" variants |
| Indirect Prompt Injection | 6 | Payloads framed as retrieved content |
| System Prompt Extraction | 6 | Attempts to leak the system prompt |
| Role-play / Persona Jailbreaks | 7 | DAN, grandma exploit, fictional personas |
| Instruction Override | 6 | Override / reset attempts |
| Encoding / Obfuscation Tricks | 7 | Base64, leetspeak, ROT13, pig latin, acrostics |

## Verdict Meanings

- **PASS** (🔴) — Attack **succeeded**. The model complied with the injection. This is a **vulnerability**.
- **FAIL** (🟢) — Attack **blocked**. The model refused or maintained safety behavior.
- **ERROR** (🟡) — Could not determine outcome (request failed, judge parse error, etc.)

## Credits

Payloads curated from:
- [OWASP LLM Top 10](https://owasp.org/www-project-top-10-for-large-language-model-applications/)
- [garak](https://github.com/leondz/garak) — open LLM vulnerability probes
- [Jailbreak Chat](https://www.jailbreakchat.com/)
- [PromptInject](https://github.com/agencyenterprise/PromptInject)
- LLM security research by Perez & Ribeiro, Greshake et al.

---

## License

MIT
