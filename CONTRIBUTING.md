# Contributing to regrisk

## Branch naming

- `feat/<short-topic>` -- new agent, new graph node, new UI element
- `fix/<short-topic>` -- bug fix
- `refactor/<short-topic>` -- code reorganisation without behaviour change
- `chore/<short-topic>` -- dependency bumps, formatting, gitignore tweaks
- `docs/<short-topic>` -- doc-only change
- `cleanup/<short-topic>` -- multi-phase cleanup passes (like this repo's `cleanup/github-ready-pass`)

## Commit style

Conventional-commits-lite:

```
<type>: <imperative summary>

<optional body explaining why, not what>

<optional footer: refs / co-authors / breaking changes>
```

`<type>` is one of: `feat`, `fix`, `refactor`, `chore`, `docs`, `test`, `wip`.

Keep commits logical and self-contained. Prefer multiple small commits
over one large one. The cleanup pass on this repo demonstrates the
desired granularity (one commit per phase).

## How to add a new agent

1. **Subclass `BaseAgent`** in `src/regrisk/agents/<your_agent>.py`:

   ```python
   from regrisk.agents.base import AgentContext, BaseAgent

   class YourAgent(BaseAgent):
       def __init__(self, context: AgentContext):
           super().__init__(context, name="YourAgent")

       async def execute(self, *, obligation, ...) -> dict:
           prompt = self._build_prompt(obligation)
           raw = await self.call_llm(system_prompt=..., user_prompt=prompt)
           parsed = self.parse_json(raw)
           # validate + return
           return parsed
   ```

   Every agent's LLM output must pass through `validation/validator.py`
   and feed into the AI Governance review layer (`core/review.py`).
   `call_llm` raises `LLMRequiredError` if no client is configured --
   do not catch it; the UI/CLI surfaces it as a setup error.
   See `agents/obligation_classifier.py` for a reference implementation.

2. **Register** the class in the relevant graph's `_AGENT_CLASSES`:

   ```python
   _AGENT_CLASSES["your_role"] = YourAgent
   ```

3. **Add a node function** in `classify_graph.py` or `assess_graph.py`:

   ```python
   def your_node(state) -> dict:
       _infra.emit_event(EventType.ITEM_STARTED, "...")
       agent = _infra.get_agent("your_role", _AGENT_CLASSES, _infra.build_agent_context())
       loop = _infra.get_or_create_event_loop()
       result = loop.run_until_complete(agent.execute(...))
       _infra.emit_event(EventType.ITEM_COMPLETED, "...")
       return {"your_state_key": result}
   ```

4. **Wire edges** in `build_*_graph(...)` and update `<graph>_state.py`
   if you introduced new keys.

5. **Add validation** in `src/regrisk/validation/validator.py` if the
   agent emits structured output that needs schema or categorical-value
   checks. This is the first half of the AI Governance layer.

6. **Add an AI Governance review rule** for the artifact in
   `src/regrisk/core/review.py` and invoke it from the graph's terminal
   node (see how `assess_graph.finalize_node` already wires the other
   `review_*` functions). This is the second half of the AI Governance
   layer -- it stamps `needs_review` + named reason codes on every LLM
   output before it is exported or surfaced for human review.

7. **Add a test** in `tests/test_<your_agent>.py`. Use the
   `stub_llm_context` fixture (see `tests/_stub_llm.py`); add a
   response branch for your agent in `_AGENT_SIGNATURES` so the stub
   recognises your prompt and returns valid canned JSON. No real API
   key is needed.

## How to add a new demo dataset

Demo checkpoints live in `data/checkpoints/` and are surfaced
automatically by `ui/checkpoint.list_checkpoints()`. To add one:

1. Run the pipeline end-to-end on the new dataset (Tab 1 -> Launch Classification, then proceed through review -> assess).
2. The pipeline auto-saves checkpoints at each stage. The `Full_Assessment_*.json` produced at completion is the demo artifact.
3. Optionally rename it to a descriptive name (no scheme is enforced).
4. The Resume-from-Checkpoint dropdown will pick it up on next app start.

Do **not** modify the JSON shape -- the demo loading contract requires
that `apply_checkpoint()` can blindly write every top-level key into
`st.session_state`. See [ADR 0005](docs/adr/0005-checkpoint-demo-loading-contract.md).

## Smoke check (before pushing)

```bash
python -m pytest tests/ -q
python -c "from regrisk.graphs.classify_graph import build_classify_graph; \
           from regrisk.graphs.assess_graph import build_assess_graph; \
           build_classify_graph(); build_assess_graph(); print('OK')"
python -m streamlit run src/regrisk/ui/app.py
# Manually: load the latest Full_Assessment_*.json checkpoint, click
# through every visible tab, confirm no errors.
```

## Documentation

- Update `README.md` when changing setup, run, or architecture surface.
- Update or add an ADR when making a non-obvious design decision.
- Add a `CHANGELOG.md` entry under `## Unreleased` for user-visible changes.

## What not to touch

- `data/checkpoints/*.json` schema -- demo contract.
- `apply_checkpoint()` and `list_checkpoints()` -- demo plumbing.
- `src/regrisk/export/excel_export.py` sheet schema -- consumer-facing.
- `config/risk_taxonomy.json` content -- owner-managed.
