# geo-ai-traffic

A GEO (Generative Engine Optimization) Skill for earning and measuring AI-assistant referral traffic. It deliberately covers only two lines of work: change the code so AI crawlers can read the site, and ask AI models a structured set of diagnostic questions and record what they answer.

This repository holds the methodology, nine standard-library scripts, prompt and question templates, and a probing protocol. `SKILL.md` — the rule source — is kept in its original Chinese; this README is the English guide to the package.

## Background

Three recurring problems produced this Skill. First, a site can be technically sound and still never be mentioned by an AI assistant, because the people asking "does ChatGPT recommend us?" have no repeatable way to check and no baseline to compare against. Second, even when the code work is done, nobody remembers what comes next — most GEO efforts stop at the three questions asked on launch day. Third, GEO is a continuing activity (launch-day check, a comparison seven days later, a re-test after every redesign), but state was stored per project directory, so switching projects made the whole queue disappear.

The design answers each problem directly. A seven-step state machine computes the next command from artifacts on disk and refuses to let later steps run without the data earlier steps should have produced. A cross-site registry keeps every domain, its stage and its due date in one place. A reminder-parameter script emits a self-contained payload for a one-off automation, because scheduling must be created by the agent's platform tool, not by a Python script writing config files.

A fourth, more specific finding shaped the attribution work: analytics tools recognise only `chatgpt.com` as a referrer, so a large share of assistant traffic is folded into `direct`. You cannot size that traffic, let alone set a paywall by source, until you instrument it yourself — and instrumentation has to ship before the traffic arrives, because historical data cannot be reconstructed afterwards.

## What it does

1. Defines the code-side changes: server-side rendering, title and H1 aligned to the target keyword, one intent per page, FAQ blocks, `robots.txt` allowing nine AI crawlers, `llms.txt` and `llms-full.txt`, Cloudflare edge-layer checks, sitemap reachability, and a first-party attribution snippet with source-based paywall configuration.
2. Ships `geo_audit.py`, which checks nine things against the live HTTP response rather than local files — including a second request with a GPTBot user agent to detect edge-layer blocking.
3. Provides the questioning workflow: three launch-day health questions, a five-tier question bank, a three-model reverse-questioning chain that writes answers back into an FAQ block, a nine-field probe log, separate tallies for different environments, and a mention-rate / competitor-ranking summary.
4. Generates ready-to-copy prompt packs with variables filled in, deliberately as plain prose rather than code blocks or tables.
5. Enforces a seven-step state machine with gates, a cross-site registry, and parameter generation for a one-off seven-day re-check reminder.
6. Handles IndexNow key generation, verification and URL submission as a supplement to Bing-side discovery.

## When to use it

Use it when an AI assistant never mentions your site, when you need to decide how to configure `robots.txt` or `llms.txt`, when deciding whether a page needs SSR or FAQ blocks, when you want a defensible way to ask an assistant whether it would recommend you, or when you need to verify whether a recommendation actually happened. Also use it when you cannot tell which of your sites is due for its next GEO pass.

It does not cover off-site article campaigns, keyword horse-racing, community case studies, or building and deploying the site itself. Those are separate jobs.

## Repository contents

- `SKILL.md` — the methodology (Chinese): code line, questioning line, state machine, gates, attribution and paywall rules.
- `references/probe-protocol.md` — how to ask, what to record, and how to keep environments separate.
- `assets/templates/` — `ask-gpt-prompts.md`, `llms.txt`, `llms-full.txt`, `robots-ai.txt`, `site-profile.md`, `question-bank.csv`, `probe-log.csv`.
- `scripts/geo_status.py` — step state machine: `status`, `registry`, `mark`, `gate`, `reset`.
- `scripts/geo_audit.py` — live-site nine-point audit.
- `scripts/geo_faq.py` — `seed`, `ask`, `collect`, `list`, `render` for the reverse-questioning chain.
- `scripts/prompt_pack.py` — prompt text packs by stage (`check`, `reverse`, `extra`, `bank`, `probe`).
- `scripts/summarize_probe.py` — mention rate, online rate, average position, consistency, competitor ranking.
- `scripts/geo_attribution.py` — `snippet`, `paywall`, `report`, `check`.
- `scripts/geo_registry.py` — cross-site ledger: `list`, `due`, `scan`, `add`, `update`, `done`, `path`.
- `scripts/geo_reminder.py` — `plan`, `pending`, `mark-created`, `clear` for the one-off re-check reminder.
- `scripts/indexnow_submit.py` — `keygen`, `check`, `submit`.

## How to use

1. Start from the cross-site view, not from memory of one project:

```bash
python3 scripts/geo_status.py registry
```

2. Move into the chosen site's project directory and let the state machine tell you the next command. On first run, pass the site details so the printed commands are already filled in:

```bash
cd /path/to/your-site
python3 scripts/geo_status.py status --domain example.com --keyword "ai poster generator" --scene "turn a photo into a movie poster"
```

3. Follow the printed command rather than reading the whole spec and guessing. Typical commands along the way:

```bash
python3 scripts/geo_audit.py example.com --keyword "ai poster generator" --path /best-ai-poster-generator
python3 scripts/prompt_pack.py --domain example.com --keyword "ai poster generator" --stage check
python3 scripts/geo_faq.py seed
python3 scripts/geo_faq.py ask --category "AI poster tools"
python3 scripts/geo_faq.py collect --dir .
python3 scripts/geo_faq.py render
python3 scripts/summarize_probe.py --csv probe-log.csv
python3 scripts/geo_status.py mark 4 --note "three opening questions asked, screenshots in shots/"
```

4. For attribution and Bing-side discovery:

```bash
python3 scripts/geo_attribution.py snippet
python3 scripts/geo_attribution.py check --domain example.com
python3 scripts/indexnow_submit.py keygen --domain example.com --out ./public
python3 scripts/indexnow_submit.py submit --domain example.com --key <key> --sitemap https://example.com/sitemap.xml --dry-run
```

5. On a site's first GEO run, generate the parameters for a one-off re-check reminder and hand them to the agent's automation tool; then write the returned id back:

```bash
python3 scripts/geo_reminder.py plan --domain example.com
python3 scripts/geo_reminder.py mark-created --domain example.com --id <automation-id> --at 2026-11-18T10:00
```

Scripts write their artifacts (`.geo-state.json`, FAQ and question CSVs, audit report, attribution snippet) into the current site project directory, so run them from there. The state machine prints absolute-path versions of commands for exactly this reason.

## Requirements

- Python 3, standard library only. No credentials or private services are bundled.
- State lives in `.geo-state.json` in the project directory and in a registry file at `~/.workbuddy/geo-sites.json`, overridable with the `GEO_REGISTRY` environment variable.
- Asking ChatGPT / Claude / Gemini and pasting their answers back is a manual step. The scripts generate prompts and consume the pasted answers; they do not call model APIs.
- `geo_audit.py` and `indexnow_submit.py` need outbound network access to inspect or submit to a live site.

## Scope and limitations

- `SKILL.md` and the templates are in Chinese. This README is the English entry point, not a translation.
- The scripts never create scheduled automations themselves; they emit parameters for the agent's platform tool to consume.
- IndexNow reaches Bing, Yandex, Naver and Seznam only — Google does not participate. A successful submission does not mean the URL is indexed.
- The gates are enforceable with `--force`, but skipping the probe step means giving up verification. That is a documented escape hatch, not a recommended path.

## Origin

Extracted from a personal WorkBuddy skill library and cleaned for public release: machine-specific absolute paths were replaced with portable ones, backup and build artifacts were excluded, and no credentials are included.
