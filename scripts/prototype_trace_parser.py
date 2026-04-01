"""Prototype: Parse a trace at the proposal point and produce annotated output.

Demonstrates the new parsing logic:
1. Identify agents by system prompt content (not fixed IDs)
2. Find proposals (send_message_to_user from observe agent)
3. Find the llm_input at the proposal point
4. Annotate each message with its timestamp from world_logs
5. Classify the user's first action after the proposal (accept/reject/gather_context)
6. For gather_context, capture the delta (additional context gathered before decision)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def identify_agents(logs: list[dict]) -> dict[str, str]:
    """Identify agent IDs by matching system prompt content."""
    agents: dict[str, str] = {}
    for log in logs:
        if log.get("log_type") != "system_prompt":
            continue
        content = log.get("content", "")
        aid = log.get("agent_id", "")
        if not isinstance(content, str):
            continue
        if "simulating a real human user" in content:
            agents["user"] = aid
        elif "proactive assistant that monitors" in content:
            agents["observe"] = aid
        elif "proactive assistant executing" in content:
            agents["execute"] = aid
    return agents


def find_proposals(logs: list[dict], observe_agent_id: str) -> list[dict]:
    """Find all proposals (send_message_to_user from observe agent)."""
    proposals = []
    for i, log in enumerate(logs):
        if (
            log.get("log_type") == "tool_call"
            and log.get("agent_id") == observe_agent_id
            and "send_message_to_user" in log.get("tool_name", "")
        ):
            proposals.append({
                "index": i,
                "timestamp": log.get("timestamp", 0),
                "content": log.get("tool_arguments", {}).get("content", ""),
            })
    return proposals


def find_execute_agent_first_call(logs: list[dict], execute_agent_id: str | None) -> float | None:
    """Find the timestamp of the execute agent's first tool call."""
    if not execute_agent_id:
        return None
    for log in logs:
        if log.get("log_type") == "tool_call" and log.get("agent_id") == execute_agent_id:
            return log.get("timestamp", 0)
    return None


def find_llm_input_after_proposal(
    logs: list[dict], proposal_idx: int, user_agent_id: str
) -> tuple[int, list[dict]] | None:
    """Find the user agent's llm_input immediately after a proposal."""
    for i in range(proposal_idx + 1, min(proposal_idx + 50, len(logs))):
        log = logs[i]
        if log.get("log_type") == "llm_input" and log.get("agent_id") == user_agent_id:
            content = log.get("content")
            messages = json.loads(content) if isinstance(content, str) else content
            return i, messages
    return None


def find_first_user_action_after_proposal(logs: list[dict], proposal_idx: int, user_agent_id: str) -> dict | None:
    """Find the user agent's first tool_call after a proposal.

    This is the 'decision': accept, reject, or gather_context.
    """
    for i in range(proposal_idx + 1, len(logs)):
        log = logs[i]
        if log.get("log_type") == "tool_call" and log.get("agent_id") == user_agent_id:
            tool_name = log.get("tool_name", "")
            if "accept_proposal" in tool_name:
                decision = "accept"
            elif "reject_proposal" in tool_name:
                decision = "reject"
            else:
                decision = "gather_context"
            return {
                "index": i,
                "timestamp": log.get("timestamp", 0),
                "tool_name": tool_name,
                "tool_arguments": log.get("tool_arguments", {}),
                "decision": decision,
            }
    return None


def annotate_messages_with_timestamps(
    messages: list[dict], logs: list[dict], llm_input_idx: int, user_agent_id: str
) -> list[dict]:
    """Annotate each llm_input message with its timestamp from world_logs.

    Uses content matching: for each message in llm_input, find the world_log
    entry whose content appears in the message. Match from the end backward
    to handle dynamic log types (available_tools, current_app_state) that
    get overwritten each turn - we want the latest instance.
    """
    # Collect user agent log entries that could contribute to llm_input
    contributing_log_types = {
        "system_prompt",
        "llm_output",
        "observation",
        "task",
        "environment_notifications",
        "available_tools",
        "current_app_state",
    }
    contributing_logs = []
    for i in range(0, llm_input_idx):
        log = logs[i]
        if log.get("agent_id") == user_agent_id and log.get("log_type") in contributing_log_types:
            content = log.get("content", "")
            if content and str(content).strip():
                contributing_logs.append(log)

    # For each message, find the matching world_log by content substring
    # Search from the end to prefer latest instance (for dynamic types)
    annotated = []
    used_indices: set[int] = set()

    for msg in messages:
        msg_content = str(msg.get("content", ""))
        best_match_ts = None
        best_match_type = None
        best_match_idx = None

        # Search backward through contributing logs
        for idx in range(len(contributing_logs) - 1, -1, -1):
            if idx in used_indices:
                continue
            log = contributing_logs[idx]
            log_content = str(log.get("content", ""))
            # Match first 50 chars of log content in message content
            if log_content[:50] and log_content[:50] in msg_content:
                best_match_ts = log.get("timestamp")
                best_match_type = log.get("log_type")
                best_match_idx = idx
                break

        if best_match_idx is not None:
            used_indices.add(best_match_idx)

        annotated.append({
            **msg,
            "timestamp": best_match_ts,
            "source_log_type": best_match_type,
        })

    return annotated


def run_batch(traces_dir: str, max_traces: int = 20) -> None:
    """Run the parser on multiple traces and summarize results."""
    traces_base = Path(traces_dir)
    results = {"accept": 0, "reject": 0, "gather_context": 0, "no_proposal": 0, "errors": 0, "skipped_post_execute": 0}
    total = 0
    annotation_failures = 0

    for model_dir in sorted(traces_base.iterdir()):
        if not model_dir.is_dir():
            continue
        for trace_file in sorted(model_dir.glob("*.json"))[: max_traces // 5 + 1]:
            total += 1
            try:
                with open(trace_file) as f:
                    data = json.load(f)
                logs = data.get("world_logs", [])
                logs = [json.loads(l) if isinstance(l, str) else l for l in logs]

                agents = identify_agents(logs)
                user_id = agents.get("user")
                observe_id = agents.get("observe")
                execute_id = agents.get("execute")

                if not user_id or not observe_id:
                    results["errors"] += 1
                    continue

                proposals = find_proposals(logs, observe_id)
                if not proposals:
                    results["no_proposal"] += 1
                    continue

                execute_first_ts = find_execute_agent_first_call(logs, execute_id)

                # Process first proposal only
                proposal = proposals[0]
                if execute_first_ts and proposal["timestamp"] >= execute_first_ts:
                    results["skipped_post_execute"] += 1
                    continue

                result = find_llm_input_after_proposal(logs, proposal["index"], user_id)
                if not result:
                    results["errors"] += 1
                    continue
                llm_input_idx, messages = result

                # Check annotation quality
                annotated = annotate_messages_with_timestamps(messages, logs, llm_input_idx, user_id)
                unannotated = sum(1 for m in annotated if m.get("timestamp") is None)
                if unannotated > 0:
                    annotation_failures += 1

                first_action = find_first_user_action_after_proposal(logs, proposal["index"], user_id)
                if not first_action:
                    results["errors"] += 1
                    continue

                results[first_action["decision"]] += 1

            except Exception as e:
                results["errors"] += 1
                print(f"ERROR in {trace_file.name}: {e}")

            if total >= max_traces:
                break
        if total >= max_traces:
            break

    print(f"\n{'=' * 60}")
    print(f"BATCH RESULTS ({total} traces)")
    print(f"{'=' * 60}")
    for k, v in sorted(results.items()):
        pct = f"({v / total * 100:.1f}%)" if total > 0 else ""
        print(f"  {k:25s}: {v:4d} {pct}")
    print(f"  {'annotation_failures':25s}: {annotation_failures:4d} (msgs with no timestamp)")
    print(f"{'=' * 60}")


def find_gathered_context_delta(
    logs: list[dict], user_agent_id: str, first_action_idx: int
) -> tuple[int | None, list[dict] | None]:
    """For gather_context decisions, find the llm_input at the eventual accept/reject.

    Returns the index and messages of the llm_input at the final decision point.
    """
    # Find the next accept/reject after the first action
    for i in range(first_action_idx + 1, len(logs)):
        log = logs[i]
        if log.get("log_type") == "tool_call" and log.get("agent_id") == user_agent_id:
            tool_name = log.get("tool_name", "")
            if "accept_proposal" in tool_name or "reject_proposal" in tool_name:
                # Find the llm_input before this decision
                for j in range(i - 1, max(i - 30, 0), -1):
                    l = logs[j]
                    if l.get("log_type") == "llm_input" and l.get("agent_id") == user_agent_id:
                        content = l.get("content")
                        messages = json.loads(content) if isinstance(content, str) else content
                        final_decision = "accept" if "accept_proposal" in tool_name else "reject"
                        return j, messages, final_decision
                break
    return None, None, None


def main(trace_path: str) -> None:
    with open(trace_path) as f:
        data = json.load(f)
    logs = data.get("world_logs", [])
    logs = [json.loads(l) if isinstance(l, str) else l for l in logs]

    agents = identify_agents(logs)
    print("=== Agents ===")
    for role, aid in sorted(agents.items()):
        print(f"  {role:10s} -> {aid[:12]}...")

    user_id = agents.get("user")
    observe_id = agents.get("observe")
    execute_id = agents.get("execute")

    if not user_id or not observe_id:
        print("ERROR: Could not identify user or observe agent")
        return

    # Find proposals and execute agent cutoff
    proposals = find_proposals(logs, observe_id)
    execute_first_call_ts = find_execute_agent_first_call(logs, execute_id)

    print(f"\n=== Proposals ({len(proposals)}) ===")
    for p in proposals:
        print(f"  [{p['index']:3d}] ts={p['timestamp']:.2f} | {p['content'][:100]}")

    if execute_first_call_ts:
        print(f"\n=== Execute agent first call: ts={execute_first_call_ts:.2f} ===")

    # Process each proposal as a potential decision point
    print("\n=== Decision Points ===")
    for p_idx, proposal in enumerate(proposals):
        # Skip proposals after execute agent has been called
        if execute_first_call_ts and proposal["timestamp"] >= execute_first_call_ts:
            print(f"\n--- Proposal {p_idx} SKIPPED (after execute agent) ---")
            continue

        print(f"\n--- Proposal {p_idx} (index={proposal['index']}, ts={proposal['timestamp']:.2f}) ---")

        # Find llm_input at proposal point
        result = find_llm_input_after_proposal(logs, proposal["index"], user_id)
        if not result:
            print("  ERROR: No llm_input found after proposal")
            continue
        llm_input_idx, messages = result
        print(f"  llm_input at index {llm_input_idx}, {len(messages)} messages")

        # Annotate with timestamps
        annotated = annotate_messages_with_timestamps(messages, logs, llm_input_idx, user_id)
        print("\n  Annotated messages:")
        for i, msg in enumerate(annotated):
            role = msg.get("role", "?")
            ts = msg.get("timestamp")
            src = msg.get("source_log_type", "?")
            content = str(msg.get("content", ""))[:80]
            ts_str = f"ts={ts:.2f}" if ts else "ts=None"
            print(f"    [{i}] {role:15s} ({src:25s}) {ts_str} | {content}")

        # Classify the decision
        first_action = find_first_user_action_after_proposal(logs, proposal["index"], user_id)
        if not first_action:
            print("\n  ERROR: No user action found after proposal")
            continue

        print(f"\n  Decision: {first_action['decision']}")
        print(f"  Tool: {first_action['tool_name']}")
        print(f"  Index: {first_action['index']}, ts={first_action['timestamp']:.2f}")

        # For gather_context, find what was gathered
        if first_action["decision"] == "gather_context":
            final_idx, final_messages, final_decision = find_gathered_context_delta(
                logs, user_id, first_action["index"]
            )
            if final_messages:
                delta_count = len(final_messages) - len(messages)
                print(f"\n  Gathered context: {delta_count} additional messages before {final_decision}")
                print(f"  Final llm_input at index {final_idx}, {len(final_messages)} messages")
                # Show the delta messages
                print("  Delta messages:")
                for i, msg in enumerate(final_messages[len(messages) :]):
                    role = msg.get("role", "?")
                    content = str(msg.get("content", ""))[:80]
                    print(f"    [{i}] {role:15s} | {content}")
            else:
                print("\n  WARNING: gather_context but no final accept/reject found")


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "--batch":
        traces_dir = (
            sys.argv[2] if len(sys.argv) > 2 else "traces/paper_benchmark_full_user_gpt-5-mini_mt_10_umi_1_omi_5_emi_10"
        )
        max_traces = int(sys.argv[3]) if len(sys.argv) > 3 else 20
        run_batch(traces_dir, max_traces)
    elif len(sys.argv) < 2:
        # Default to the trace we've been analyzing
        trace_path = "traces/paper_benchmark_full_user_gpt-5-mini_mt_10_umi_1_omi_5_emi_10/obs_claude-4.5-sonnet_exec_claude-4.5-sonnet_enmi_0_es_42_tfp_0.0/note_update_reflects_meeting_changes_run_4.json"
        main(trace_path)
    else:
        main(sys.argv[1])
