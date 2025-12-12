# ProposalManager Improvements

## Issues Fixed

### 1. Session Loop Detection Too Aggressive ✅
**Problem:** Line 510 in `proposal_manager.py` checked `if count >= 1`, which meant proposals were suppressed after appearing just **twice** in a session.

**Fix:** Changed threshold to `count >= 5`, allowing up to 6 attempts before suppression.

**Impact:** System can now retry proposals more times before giving up.

---

### 2. LLM Rewriter Limited to 4 Issues ✅
**Problem:** `llm_rewriter.py` line 52 set `MAX_ISSUES = 4`, processing only 4 code issues per auto-improvement cycle.

**Fix:** Increased to `MAX_ISSUES = 20` to process 5x more issues per cycle.

**Impact:** More proposals generated per run, faster codebase improvement.

---

### 3. No Learning from Feedback ✅
**Problem:** LLM rewriter didn't consider previously rejected proposals, causing repeated suggestions of unwanted changes.

**Fix:** Added `_get_feedback_context()` method that:
- Analyzes last 50 proposal decisions
- Finds rejections for similar files/issues
- Passes up to 3 rejection examples to LLM
- Includes "learning_context" in prompts to guide away from failed patterns

**Impact:** System gets smarter with every yes/no decision, avoiding patterns you've rejected.

---

### 4. Cross-File Duplicate Detection ✅
**Note:** This is **working as intended**. The system skips duplicates that span multiple files "to respect role separation" - this prevents suggesting to merge code across architectural boundaries.

**Current behavior:**
- Within-file duplicates → Creates proposal ✓
- Cross-file duplicates → Skipped (intentional) ✓

---

## Enabling Full LLM Power

The system currently falls back to a template engine because the OpenAI package isn't installed. To enable full AI-powered rewriting:

```bash
pip install openai>=1.0.0
export OPENAI_API_KEY="your-api-key-here"
# Or set in .env file
```

Once enabled, the LLM rewriter will:
- Detect 8 issue types (inefficient loops, dead code, unused imports, etc.)
- Generate smart rewrites with full code context
- Learn from your feedback to avoid rejected patterns
- Process 20 issues per cycle (up from 4)

---

## How DEX Expansion Works

The system adds DEXs one at a time:

1. **Recommendation**: `dex_expander.recommend_new_dexes(limit=1)` finds unused DEXs
2. **Proposal**: Creates a proposal with code template for `pool_registry.json`
3. **Validation**: User must verify query calls work before accepting
4. **Next DEX**: After acceptance, next cycle recommends the next DEX

**Current status:**
- 7 DEXes with pools: QuickSwap_V2, Uniswap_V3, SushiSwap, Algebra, SushiSwap_V3, Retro, Dystopia
- 15 DEXes ready to add: ApeSwap, Dfyn, Polycat, JetSwap, etc.
- Next recommendation: Retro (queued)

---

## Testing the Improvements

Run the auto-improvement cycle:

```python
from ai_agent.driver import AIAgentDriver

driver = AIAgentDriver('.')
result = driver.auto_improvement_cycle(include_dex_growth=True)

print(f"Proposals queued: {len(driver.proposals.queue)}")
```

Or use the CLI:

```bash
python cli_ai_driver.py
```

---

## Summary of Changes

| File | Change | Impact |
|------|--------|--------|
| `proposal_manager.py:510` | Session loop threshold 1→5 | More retry attempts |
| `llm_rewriter.py:52` | MAX_ISSUES 4→20 | 5x more proposals/cycle |
| `llm_rewriter.py:238-267` | Added `_get_feedback_context()` | Learn from rejections |
| `llm_rewriter.py:207` | Added feedback to prompts | Smarter suggestions |

---

## Next Steps

1. **Install OpenAI** to enable full LLM rewriting (recommended)
2. **Run the improvement cycle** and review proposals
3. **Accept/Reject proposals** - system learns from each decision
4. **Add DEXs gradually** - system will queue next DEX after each acceptance
5. **Monitor proposal quality** - should improve over time as feedback accumulates
