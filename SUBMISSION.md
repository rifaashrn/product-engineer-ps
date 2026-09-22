# Product Engineering Challenge Submission

## Candidate

- **Name:** Rifa Sherin
- **Email:** rifasherin958@gmail.com
- **GitHub:** https://github.com/rifaashrn (repo: https://github.com/rifaashrn/product-engineer-ps, code in `solution/`)
- **Selected problem:** Problem 4, Observable Agent Loop
- **Demo video:** https://www.loom.com/share/7af20c62f4a24d18837879098410dae4

## Run the project

Prerequisites: Python 3.11 or newer and Git. I built and tested on Windows with Python 3.12.

```text
git clone https://github.com/rifaashrn/product-engineer-ps
cd product-engineer-ps
python -m venv .venv
.venv\Scripts\activate            
pip install -r requirements.txt
```

The only environment variable is `GEMINI_API_KEY`, and it is needed only for the live model. Optionally, `GEMINI_MODEL` selects the model (default `gemini-2.5-flash`). Copy `.env.example` to `.env` and fill it in. `.env` is git-ignored and no secret is committed.

**Successful scenario (multi-tool investigation):**

```text
python -m solution.agent.cli --fake multi
python -m solution.agent.cli "Why is checkout failing?"
```

The first runs a scripted fake model and needs no key. The second uses the live Gemini model.

**Failure and recovery scenario:**

```text
python -m solution.agent.cli --fake failure
python -m solution.agent.cli "What is the status of billing-worker?"
```

In the tool `get_service_status`, `billing-worker` always times out, on purpose. The trace shows the error, and the agent recovers with another tool call (scripted run) or stops after repeated failures (live run).

**Step limit scenario:**

```text
python -m solution.agent.cli --fake limit --max-steps 3
```

Every run saves its trace as JSONL in `solution/runs/`. Sample traces are in `solution/examples/`. `sample_trace_scripted.jsonl` comes from a scripted replay.`sample_trace_gemini.jsonl` comes from a live Gemini run.

## Run the tests

```text
pytest
```

There are 25 tests. They use a scripted fake model, so they need no API key and no network.

## Acceptance scenarios and verification

I completed all six scenarios for Problem 4:

- **AC1, tool selection and validation:** `test_parse_tool_call`, `test_search_logs_returns_matching_entries`, `test_unknown_tool_is_rejected`, `test_missing_argument_is_rejected`.
- **AC2, multi-step investigation using two sources, and AC3, ordered trace:** `test_multi_step_investigation_produces_ordered_trace`.
- **AC4, tool failure:** `test_tool_failure_is_visible_and_agent_can_recover`, `test_repeated_failures_stop_the_run`, `test_malformed_tool_result_is_a_visible_failure`, `test_model_unavailable_stops_immediately`, `test_invalid_model_output_is_logged_and_retried`.
- **AC5, step limit:** `test_step_limit_stops_without_extra_calls`. It asserts the fake model's call count, so no extra model or tool call happens after the limit.
- **AC6, evidence separate from conclusions:** `FinalAnswer` has separate `evidence` and `conclusion` fields, and the CLI prints them under separate headings.

**Verification commands:**

```text
pytest
python -m solution.agent.cli --fake multi
python -m solution.agent.cli --fake failure
python -m solution.agent.cli --fake limit --max-steps 3
python -m solution.agent.cli "Why is checkout failing?"
```

**Observed results** (Windows, Python 3.12.10):

- `pytest`: 25 passed in 0.21 s.
- `--fake multi`: 3 steps. Step 1 `search_logs`, step 2 `get_metrics`, step 3 `final_answer`. The trace order was objective, decision, tool call, tool result, and so on. The final answer listed evidence separately from the conclusion.
- `--fake failure`: step 1 `get_service_status` for `billing-worker` produced an `error` event ("ToolError: Status backend timed out for billing-worker"). Step 2 called `get_service_status` for `payments-db` and got a result. Step 3 was the `final_answer`.
- `--fake limit --max-steps 3`: 3 tool calls, then a `stopped` event with reason `max_steps_reached`.
- **Live Gemini runs:** in my first live attempts the model guessed service names (`checkout`, `payment`, `inventory`, `shipping`) that don't exist, and then the free-tier quota returned 429 errors. I fixed both (see Important decisions). After the fixes, a live Gemini run investigating checkout failures completed in 5 steps with 4 tool calls and no errors. It checked the status of checkout-api, searched its logs, checked the status of payments-db, searched the logs again, and concluded that checkout-api timeouts were caused by payments-db's saturated connection pool. I checked each evidence item against the tool results. Trace: `solution/examples/sample_trace_gemini.jsonl`.

**Failure scenario shown in the video and how to reproduce it:** run `python -m solution.agent.cli --fake failure` and look at the `error` line in step 1 and the recovery in step 2. With a key you can also run `python -m solution.agent.cli "What is the status of billing-worker?"`.

## Architecture and data flow

| File | Responsibility |
|---|---|
| `schemas.py` | Typed shapes: `ToolCall`, `FinalAnswer` (evidence kept separate from conclusion), `TraceEvent` |
| `tools.py` | Tool registry, argument schemas, `run_tool` (validate, then run), three tools over fixture data in `data/` |
| `models.py` | `ModelAdapter` interface, `FakeModel` (scripted), `GeminiModel`, `parse_decision` |
| `loop.py` | `run_agent`: the control loop, limits and failure handling |
| `trace.py` | Ordered events, secret redaction, JSONL persistence |
| `cli.py`, `demo.py` | Command-line presentation and scripted demo runs |

**Data flow:** the objective goes into a message list. Each step, the model returns a decision. `parse_decision` validates it. If it is a tool call, `run_tool` validates the arguments and runs the tool. The result, or the error, is appended to the conversation and to the trace. This repeats until the model gives a final answer or a stop condition fires. Stop reasons are `final_answer`, `max_steps_reached`, `too_many_failures` and `model_unavailable`.

## Technology choices

- **Python and pydantic.** pydantic validates both boundaries: what the model returns, and what arguments a tool receives.
- **JSON-in-text prompting instead of native function calling.** This works across providers and is easy to fake. The trade-off is that I depend on the model following the format, so every reply is validated, and unusable replies are logged and retried.
- **A small hand-written loop instead of an agent framework.** The brief evaluates the control loop itself, so I kept it visible and easy to test. The cost is that I built retries and limits myself.
- **The whole conversation is sent as one prompt each step.** This keeps the adapter stateless and simple. The prompt grows each step, which is fine for at most 8 steps.
- **Gemini free tier as the live model.** It costs nothing but has rate limits, which I ran into.

## Important decisions

1. **A fake model behind the same interface as the real one.** `FakeModel` replays scripted decisions, so every acceptance scenario is deterministic, and the tests need no key or network. The tests can assert exact call counts, which is how AC5 is proven.
2. **Errors go back to the model, and only repeated failures stop the run.** A tool error is written to the trace and returned to the model so it can try something else. Three consecutive failures stop the run. A rate limit (429) is different: retrying instantly cannot help, so it stops immediately as `model_unavailable`. I added this after my live run burned its whole failure budget in one second.
3. **An unknown service is an error, not an empty result.** In live testing, the model guessed service names, and `search_logs` returned an empty list, which looks the same as "no matching logs". Now unknown services raise an error listing the valid names, and the system prompt lists the known services. Empty results now mean what they say.

## Assumptions and limitations

- All data is synthetic. The service list is fixed in `data/status.json`.
- Evidence versus conclusion is enforced by the prompt and the schema. The code does not check that each evidence string actually appears in a tool result.
- Model errors count toward the consecutive-failure limit and use up a step.
- The whole conversation is resent each step, so long tool results would grow the prompt.
- Not implemented: resumable runs, human approval, parallel tool calls, token and cost accounting, and automatic retry with backoff for rate limits.
- The Gemini free tier has quota limits, so live runs can fail. The scripted demos and tests do not depend on it.

## Production and scale

**What the submission does now:** a single synchronous process, one run at a time, with traces written to local JSONL files, and an immediate stop when the model is rate limited.

**What I would change first, and why:**

1. Store runs and traces in a database with a run ID, because local files can't be queried or shared across workers.
2. Run agents as stateless workers pulling jobs from a queue, with per-run timeouts, and with backoff and concurrency limits per model provider, so rate limits become a scheduling problem instead of a failure.
3. Verify programmatically that each evidence item appears in a tool result, so the evidence/conclusion split is enforced by code and not only by the prompt.

## AI usage

I used Claude (Anthropic) in a chat as a pair-programming assistant. It helped with the architecture and with writing the initial code, and it explained the steps as I built them. Gemini is used only as the runtime model inside the project.

I did not paste output without checking it. I ran the tests and the demos after each stage, and I debugged the problems that came up:

- A duplicate `build_system_prompt` function left in `models.py` overrode the new one, so the service names never appeared in the prompt. I found it by printing the running function's source with `inspect`, and I removed the old copy.
- My scripted runs finished within the same second and overwrote each other's trace file. I added microseconds to the filename and a regression test.
- An edit to `loop.py` referenced a variable before it was assigned on tool errors. The tests caught it immediately, and I fixed it.

I can explain any part of the code.

## Credibility note

**Project:** Bank Cleansing and Validation System, built in UiPath during my internship at Power International Holding and run against real bank records.

- **The problem it solved:** bank records contain IBAN and SWIFT codes that must be correct before anyone relies on them. The system automates checking each record's codes across Qatar, Saudi Arabia and the UAE.
- **My personal contribution:** I built the workflows. A main controller (`Main.xaml`) loops through the Excel bank records and invokes the matching country-specific sub-workflow (`QATAR.xaml`, `SAUDI.xaml` or `UAE.xaml`) for each one.
- **Scale and operational complexity:** three countries, each with its own validation flow. Every record is validated through web lookups (bank.codes and ibancalculator.com) and cross-checked against an internal SWIFT database. So each result depends on several sources that can disagree or be unavailable, and the workflow has to handle that.
- **One difficult decision:** structuring the system as one controller plus a separate sub-workflow per country, instead of one large flow. This keeps each country's rules and lookups isolated, so one can change without touching the others.
- **Public link or evidence:** none available. The project used real bank data, so the code, data and screenshots are confidential. 

The shape is the same as this submission: a controller loop that dispatches work to specialised units, depends on external sources, and cross-checks results.
