# Intelligent Category-Level Learning System

## The Problem You Identified

Your AI wasn't just learning "don't suggest THIS exact thing again" - it needed **common sense**:

- ✅ Accept math fix → **Actively search for MORE math issues**
- ❌ Reject many duplicates → **STOP suggesting duplicates entirely**
- ✅ Accept security improvements → **Prioritize finding security risks**
- ❌ Reject performance tweaks → **Deprioritize performance proposals**

## The Solution

Added **category-level intelligence** that recognizes PATTERNS, not just individual rejections.

---

## How It Works

### 1. **Category Tracking** (`feedback.py`)

Tracks acceptance/rejection rates for:
- **Proposal types**: `bugfix`, `security`, `performance`, etc.
- **Issue types**: `duplicate_logic`, `inefficient_math`, `unused_imports`, etc.

```python
stats = feedback.get_category_stats()
# Returns:
# {
#   "issue:inefficient_math": {
#     "acceptance_rate": 1.0,  # 100% accepted
#     "priority": "boost",      # Actively seek more
#     "recommendation": "User accepts 100% - actively seek more of these!"
#   },
#   "issue:duplicate_logic": {
#     "acceptance_rate": 0.0,  # 0% accepted
#     "priority": "suppress",   # STOP suggesting
#     "recommendation": "User rejects 100% - STOP suggesting these"
#   }
# }
```

### 2. **Smart Priority Levels**

| Acceptance Rate | Priority | Action |
|----------------|----------|--------|
| ≥75% | **boost** | Actively search for more (tell LLM to prioritize) |
| 40-74% | **normal** | Continue as usual |
| 20-39% | **low** | Deprioritize but still suggest occasionally |
| <20% | **suppress** | STOP suggesting (after 3+ decisions) |

### 3. **Automatic Filtering** (`proposal_manager.py`)

Before even creating a proposal, checks:

```python
should_suggest, reason = feedback.should_suggest_category(
    proposal_type="performance",
    issue_type="duplicate_logic"
)

if not should_suggest:
    print(f"[ProposalManager] Skipping {proposal_type}: {reason}")
    # Proposal never enters queue!
```

**Example output:**
```
[ProposalManager] Skipping performance: User rejects duplicate_logic issues (0% acceptance)
```

### 4. **LLM Guidance** (`llm_rewriter.py`)

Passes intelligence to the LLM in prompts:

**Rejections (what to avoid):**
```json
{
  "learning_context": {
    "note": "The user previously rejected similar proposals. Avoid these patterns.",
    "rejected_examples": [
      {"summary": "Unify duplicate functions", "reason": "User rejected"},
      {"summary": "Merge similar classes", "reason": "User rejected"}
    ]
  }
}
```

**Boosted categories (what to prioritize):**
```json
{
  "user_preferences": {
    "note": "The user consistently accepts these types of changes. Look for more opportunities like these.",
    "boosted_categories": [
      "issue:inefficient_math",
      "security"
    ]
  }
}
```

---

## Examples of Common Sense in Action

### Example 1: Math Corrections
```
You accept 3 math fixes → System learns:
  ✓ "inefficient_math" has 100% acceptance
  ✓ Priority: boost
  ✓ LLM told: "User loves math fixes - actively search for more calculation issues"

Result: System finds MORE math problems you care about
```

### Example 2: Duplicate Rejections
```
You reject 5 duplicate proposals → System learns:
  ✗ "duplicate_logic" has 0% acceptance
  ✗ Priority: suppress
  ✗ Future duplicate proposals BLOCKED before reaching queue

Result: You NEVER see duplicate proposals again
```

### Example 3: Mixed Security Results
```
You accept 2 security fixes, reject 1 → System learns:
  ~ "security" has 67% acceptance
  ~ Priority: normal
  ~ Continue suggesting but don't boost

Result: Security proposals continue at normal rate
```

---

## Full Metadata Tracking

Every decision now records:

```json
{
  "id": "proposal_12345",
  "decision": "accepted",
  "summary": "Fix integer division precision",
  "file": "price_calculator.py",
  "metadata": {
    "context": "direct",
    "proposal_type": "bugfix",
    "issue_type": "inefficient_math"
  }
}
```

This metadata enables pattern recognition across:
- **Same file** (avoid rejected patterns in specific files)
- **Same issue type** (learn what types of issues you care about)
- **Same proposal category** (understand your priorities)

---

## Verification Test

```python
from ai_agent.feedback import FeedbackStore

store = FeedbackStore('ai_agent/state.json')

# Simulate accepting 3 math fixes
# Simulate rejecting 3 duplicate proposals

stats = store.get_category_stats()
print(stats['issue:inefficient_math'])
# Output: {"acceptance_rate": 1.0, "priority": "boost", ...}

should_suggest, reason = store.should_suggest_category('performance', 'duplicate_logic')
# Output: (False, "User rejects duplicate_logic issues (0% acceptance)")
```

---

## Impact on Your Workflow

### Before:
- ❌ System suggests same type of unwanted change repeatedly
- ❌ No recognition that you LOVE certain fix types
- ❌ Dumb rejection cache only blocks exact duplicates

### After:
- ✅ **Accepts math fix → Hunts for MORE math issues**
- ✅ **Rejects duplicates → STOPS suggesting duplicates**
- ✅ **Smart about priorities → Focuses on what YOU value**
- ✅ **Gets smarter with every decision → Learns your patterns**

---

## Files Modified

| File | Changes | Purpose |
|------|---------|---------|
| `feedback.py` | +120 lines | Category stats, priority calculation, smart filtering |
| `proposal_manager.py` | +38 lines | Category suppression, metadata tracking |
| `llm_rewriter.py` | +14 lines | Pass boosted categories to LLM |
| `state.json` | structure | Store category metadata with decisions |

---

## Next Steps

1. **Run the system** - `python cli_ai_driver.py`
2. **Accept/reject proposals** - System tracks categories automatically
3. **After 3+ decisions per category** - Intelligence kicks in
4. **Watch it get smarter** - Stops suggesting unwanted types, boosts loved types
5. **Check learning**:
   ```python
   from ai_agent.feedback import FeedbackStore
   store = FeedbackStore('ai_agent/state.json')
   print(store.get_category_stats())
   ```

The system now has **common sense** - it generalizes from your decisions to understand your priorities! 🧠
