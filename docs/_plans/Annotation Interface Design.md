# Annotation Interface Design

## Overview

This document describes the design for a human annotation interface to collect accept/reject decisions on proactive agent proposals. The system samples decision points from existing traces and presents them to human annotators via a web interface.

## Goals

1. Sample balanced datasets (equal accept/reject by user agent) from existing traces
2. Present decision contexts to human annotators in a clean, mobile-like UI
3. Collect human annotations (accept/reject) with anonymous user tracking
4. Persist all data locally with support for incremental sampling and server restarts

## Architecture

### High-Level Flow

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Trace Files    │────▶│  Sample Command │────▶│ samples.parquet │
│  (JSON)         │     │  (CLI)          │     │ (append-only)   │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                                                        │
                                                        ▼
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Annotator      │◀───▶│  Launch Command │◀───▶│ annotations.csv │
│  (Browser)      │     │  (FastAPI)      │     │ (append-only)   │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

### Components

1. **Trace Parser** (`pas/annotation/trace_parser.py`)
   - Parses trace JSON files
   - Extracts decision points (accept/reject events)
   - Groups actions by turn with formatted observations

2. **Sampler** (`pas/annotation/sampler.py`)
   - Implements balanced sampling algorithm
   - Prioritizes unique scenarios
   - Supports incremental sampling (append to existing)

3. **Server** (`pas/annotation/server.py`)
   - FastAPI application
   - In-memory annotation count caching
   - REST API for sample distribution and annotation submission

4. **UI** (`pas/annotation/templates/index.html`)
   - Single-page application
   - TailwindCSS styling
   - Mobile-like observation formatting

## CLI Commands

### `pas annotation sample`

Creates/appends samples to the annotation pool.

```bash
pas annotation sample \
    --traces-dir traces/paper_benchmark_full_user_gpt-5-mini_mt_10_umi_1_omi_5_emi_10 \
    --sample-size 50 \
    --seed 42
```

**Options:**
- `--traces-dir`: Path to traces directory (required)
- `--sample-size`: Number of new samples to add (required)
- `--seed`: Random seed for reproducibility (optional)

**Behavior:**
- Reads existing `samples.parquet` if present
- Extracts all decision points from no-noise trace directories (`enmi_0`)
- Filters out already-sampled decision points
- Applies balanced sampling with unique scenario priority
- Appends new samples to `samples.parquet`

### `pas annotation launch`

Launches the annotation web server.

```bash
pas annotation launch \
    --annotators-per-sample 2 \
    --port 8000
```

**Options:**
- `--annotators-per-sample`: Number of annotations required per sample (default: 2)
- `--port`: Server port (default: 8000)

**Behavior:**
- Loads samples and existing annotations at startup
- Pre-builds in-memory annotation counts
- Serves annotation UI
- Distributes samples to annotators based on completion status

### `pas annotation status`

Shows annotation progress statistics.

```bash
pas annotation status
```

**Output:**
```
PAS Annotation Status
========================================
Data directory: ~/.cache/pas/annotations

Samples:
  Total: 80
  Complete (2+ annotations): 45
  In progress (1 annotation): 20
  Not started: 15

Annotations:
  Total: 110
  Unique annotators: 8

Balance:
  User agent accepts: 40/80 (50.0%)
  User agent rejects: 40/80 (50.0%)
```

### `pas annotation set-dir`

Sets the annotations directory (persistent config).

```bash
pas annotation set-dir /path/to/annotations --create
```

## Data Models

### DecisionPoint (Internal)

```python
@dataclass
class ActionWithObservation:
    """A single user action with its formatted observation."""
    action: str           # e.g., "Messages__open_conversation(conversation_id='fc78...')"
    observation: str      # Formatted, human-readable observation

@dataclass
class Turn:
    """A single turn of user interaction."""
    turn_number: int
    notifications: list[str]
    actions: list[ActionWithObservation]

@dataclass
class DecisionPoint:
    """A single decision point extracted from a trace."""
    sample_id: str                    # {scenario_id}_run_{run_number}_{content_hash}
    scenario_id: str
    run_number: int
    model_id: str
    trace_file: Path
    meta_task_description: str        # From scenario metadata (may be empty)
    turns: list[Turn]                 # All turns before this decision
    agent_proposal: str               # The proposal text
    user_agent_decision: bool         # True=accept, False=reject
```

### Sample (Parquet Schema)

| Column | Type | Description |
|--------|------|-------------|
| `sample_id` | str | Unique identifier |
| `scenario_id` | str | Scenario name |
| `run_number` | int | Run number within scenario |
| `model_id` | str | Model that generated the trace |
| `trace_file` | str | Path to source trace |
| `user_agent_decision` | bool | User agent's decision |
| `agent_proposal` | str | Proposal text |
| `context_json` | str | JSON-serialized turns and metadata |

### Annotation (CSV Schema)

| Column | Type | Description |
|--------|------|-------------|
| `annotation_id` | str | UUID |
| `sample_id` | str | Reference to sample |
| `annotator_id` | str | Anonymous user UUID |
| `human_decision` | bool | Human's accept/reject |
| `user_agent_decision` | bool | User agent's decision (for analysis) |
| `timestamp` | str | ISO format timestamp |

## Configuration

Following the existing PAS config pattern (`~/.config/pas/config.json`):

```json
{
  "cache_dir": "~/.cache/pas/scenario_results",
  "annotations_dir": "~/.cache/pas/annotations"
}
```

**Priority for annotations directory:**
1. `PAS_ANNOTATIONS_DIR` environment variable
2. `annotations_dir` in config file
3. Default: `~/.cache/pas/annotations`

## Sampling Algorithm

### Balanced Sampling with Unique Scenario Priority

```
Input: traces_dir, sample_size, existing_samples
Output: list of new DecisionPoints

1. Extract all decision points from no-noise traces (enmi_0 directories)
2. Filter out already-sampled decision points (by sample_id)
3. Separate into accept_pool and reject_pool
4. Track scenarios already used (from existing_samples)

5. While len(selected) < sample_size:
   a. Determine target: accept if accepts_selected <= rejects_selected, else reject
   b. Get appropriate pool (accept_pool or reject_pool)
   c. If pool empty, try other pool
   d. If both empty, break

   e. Prioritize candidates from unused scenarios:
      - unused = [c for c in pool if c.scenario_id not in scenarios_used]
      - If unused not empty, pick from unused
      - Else pick from pool (allowing scenario reuse)

   f. Add to selected, mark scenario as used, remove from pools

6. Return selected
```

### Duplicate Detection

Each sample has a unique `sample_id` generated as:
```python
content = f"{scenario_id}_{run_number}_{proposal_text}"
content_hash = hashlib.sha256(content.encode()).hexdigest()[:8]
sample_id = f"{scenario_id}_run_{run_number}_{content_hash}"
```

This ensures:
- Same decision point is never sampled twice
- Different proposals from same trace get different IDs

## Observation Formatting

Raw trace observations (JSON, Python objects) are formatted for human readability.

### Formatting Rules

| Observation Type | Raw Format | Formatted Output |
|-----------------|------------|------------------|
| App opened | `"Opened Messages App."` | `Opened Messages App.` |
| Conversation list | `[ConversationV2(...), ...]` | Formatted list with participant names |
| Messages | `{'messages': [MessageV2(...), ...]}` | Chat-style message display |
| Contact | `Contact(name='John', ...)` | Contact card format |
| Email | `Email(subject='...', from='...')` | Email preview format |
| Generic ID | `"fc78aea9-..."` | `Created/Updated: fc78aea9-...` |
| Error | `"Error: ..."` | `Error: ...` |

### Example Formatters

```python
def format_conversation_list(conversations: list) -> str:
    """Format a list of conversations for display."""
    lines = ["Recent Conversations:"]
    for conv in conversations[:5]:  # Limit to 5
        participants = ", ".join(conv.participant_names[:3])
        if len(conv.participant_names) > 3:
            participants += f" +{len(conv.participant_names) - 3} more"
        last_msg = conv.messages[0].content[:50] + "..." if conv.messages else "No messages"
        lines.append(f"  - {participants}")
        lines.append(f"    Last: {last_msg}")
    return "\n".join(lines)

def format_messages(messages: list) -> str:
    """Format messages in chat style."""
    lines = ["Messages:"]
    for msg in messages[:10]:  # Limit to 10
        sender = msg.sender_name or msg.sender_id[:8]
        content = msg.content[:100] + "..." if len(msg.content) > 100 else msg.content
        lines.append(f"  [{sender}]: {content}")
    return "\n".join(lines)
```

## Server Architecture

### In-Memory State

```python
class AnnotationServer:
    def __init__(self, data_dir: Path, annotators_per_sample: int):
        self.data_dir = data_dir
        self.annotators_per_sample = annotators_per_sample

        # Loaded at startup
        self.samples_df: pl.DataFrame

        # In-memory annotation tracking (updated on each submission)
        self._annotation_counts: dict[str, int]           # sample_id -> count
        self._user_annotations: dict[str, set[str]]       # user_id -> set of sample_ids
        self._lock: threading.Lock                        # Thread safety
```

### API Endpoints

#### `GET /api/sample`

Get next sample for the current annotator.

**Request Headers:**
- `X-Annotator-ID`: Anonymous user UUID (from browser localStorage)

**Response:**
```json
{
  "sample_id": "email_forward_run_1_a1b2c3d4",
  "scenario_context": "...",
  "turns": [
    {
      "turn_number": 1,
      "notifications": ["[2025-11-18 09:00:10] New message from Casey..."],
      "actions": [
        {
          "action": "System__open_app(app_name='Messages')",
          "observation": "Opened Messages App."
        }
      ]
    }
  ],
  "agent_proposal": "Casey Jordan in your 'Book Club' thread...",
  "progress": {
    "completed": 5,
    "total": 25
  }
}
```

**Response (no more samples):**
```json
{
  "sample_id": null,
  "message": "You have completed all available samples. Thank you!"
}
```

#### `POST /api/annotate`

Submit an annotation.

**Request Headers:**
- `X-Annotator-ID`: Anonymous user UUID

**Request Body:**
```json
{
  "sample_id": "email_forward_run_1_a1b2c3d4",
  "decision": true
}
```

**Response:**
```json
{
  "success": true,
  "next_sample": { ... }  // Next sample or null
}
```

**Behavior:**
1. Validate sample_id exists
2. Check user hasn't already annotated this sample
3. Append to CSV file (atomic write with lock)
4. Update in-memory counts
5. Return next sample

#### `GET /api/progress`

Get annotator's progress.

**Response:**
```json
{
  "completed": 5,
  "total": 25,
  "percentage": 20.0
}
```

### Data Persistence Flow

```
Browser submits annotation
         │
         ▼
┌─────────────────────────────────────┐
│  POST /api/annotate                 │
│  1. Acquire lock                    │
│  2. Append row to annotations.csv   │
│  3. Update in-memory counts         │
│  4. Release lock                    │
│  5. Return next sample              │
└─────────────────────────────────────┘
         │
         ▼
annotations.csv (immediately persisted)
```

**Key Points:**
- Each annotation is written immediately to CSV (no batching)
- In-memory state is updated atomically with file write
- Lock ensures thread safety for concurrent annotators
- Server restart re-reads CSV to rebuild state

## UI Design

### Layout

```
┌─────────────────────────────────────────────────────────────────┐
│  PAS Annotation Study                          Progress: 5/25   │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ SCENARIO CONTEXT                                          │  │
│  │ (meta_task_description - shown if available)              │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ════════════════════════ TURN 1 ════════════════════════════   │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ NOTIFICATIONS                                             │  │
│  │ [09:00:10] New message from Casey Jordan in Book Club...  │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ YOUR ACTIONS                                              │  │
│  │                                                           │  │
│  │ System__open_app(app_name='Messages')                     │  │
│  │ ┌─────────────────────────────────────────────────────┐   │  │
│  │ │ Opened Messages App.                                │   │  │
│  │ └─────────────────────────────────────────────────────┘   │  │
│  │                                                           │  │
│  │ Messages__list_recent_conversations(offset=0, limit=10)   │  │
│  │ ┌─────────────────────────────────────────────────────┐   │  │
│  │ │ Recent Conversations:                               │   │  │
│  │ │   - Casey Jordan, Alex Smith, +2 more               │   │  │
│  │ │     Last: I'll bring snacks! Email me your diet...  │   │  │
│  │ │   - Mom                                             │   │  │
│  │ │     Last: Call me when you get a chance             │   │  │
│  │ └─────────────────────────────────────────────────────┘   │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ════════════════════════ TURN 2 ════════════════════════════   │
│  ...                                                            │
│                                                                 │
│  ═══════════════════════════════════════════════════════════════│
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ ASSISTANT'S PROPOSAL                              [NEW]   │  │
│  │                                                           │  │
│  │ Casey Jordan in your "Book Club Monthly" thread asked     │  │
│  │ everyone to email dietary restrictions. I can draft the   │  │
│  │ email now and prep it to send from john@pas.com.          │  │
│  │                                                           │  │
│  │ Proposed email:                                           │  │
│  │ To: casey.jordan@email.com                                │  │
│  │ Subject: Dietary restrictions for Book Club - John Doe    │  │
│  │ Body:                                                     │  │
│  │ Hi Casey,                                                 │  │
│  │ Thanks for organizing snacks! My dietary restrictions...  │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                 │
│  Would you accept this proposal from your assistant?            │
│                                                                 │
│  ┌─────────────────────┐    ┌─────────────────────┐            │
│  │       ACCEPT        │    │       REJECT        │            │
│  │   (green button)    │    │    (red button)     │            │
│  └─────────────────────┘    └─────────────────────┘            │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Styling

- **Framework**: TailwindCSS via CDN
- **Color Scheme**: Clean, minimal with good contrast
- **Actions**: Monospace font for function calls
- **Observations**: Card-style boxes with subtle background
- **Proposal**: Highlighted box with border accent
- **Buttons**: Large, clear Accept (green) / Reject (red)

### Anonymous User ID

```javascript
// Stored in browser localStorage
function getOrCreateAnnotatorId() {
    let id = localStorage.getItem('pas_annotator_id');
    if (!id) {
        id = crypto.randomUUID();
        localStorage.setItem('pas_annotator_id', id);
    }
    return id;
}
```

## File Structure

```
pas/
├── annotation/
│   ├── __init__.py
│   ├── config.py              # Directory config helpers
│   ├── models.py              # Pydantic/dataclass models
│   ├── trace_parser.py        # Parse traces, format observations
│   ├── sampler.py             # Balanced sampling algorithm
│   ├── server.py              # FastAPI application
│   └── templates/
│       └── index.html         # Annotation UI
├── cli/
│   ├── annotation.py          # CLI commands
│   └── ...
```

## Deployment

### Local Development

```bash
# Sample 50 datapoints
pas annotation sample --traces-dir ./traces/... --sample-size 50

# Launch server
pas annotation launch --port 8000

# Access at http://localhost:8000
```

### Public Access via ngrok

```bash
# In terminal 1
pas annotation launch --port 8000

# In terminal 2
ngrok http 8000

# Share the ngrok URL with annotators
# e.g., https://abc123.ngrok-free.app
```

## Error Handling

### Sample Command Errors

| Error | Handling |
|-------|----------|
| Traces directory not found | Exit with error message |
| No valid traces found | Exit with error message |
| No decision points found | Exit with error message |
| Cannot create annotations dir | Exit with error message |

### Server Errors

| Error | Handling |
|-------|----------|
| Sample file not found | Exit with error, prompt to run sample first |
| CSV write failure | Return 500, log error, don't update memory |
| Invalid sample_id | Return 400 with error message |
| User already annotated | Return 409 Conflict |

## Future Enhancements

1. **Export command**: Export final annotations to various formats
2. **Admin dashboard**: View annotation progress, annotator stats
3. **Annotation review**: Allow reviewing/correcting annotations
4. **Multi-study support**: Separate annotation pools for different studies
