"""Prototype v2: Parse traces at proposal points with simplified timestamp annotation.

Only annotates timestamps on event messages:
- assistant messages (user agent reasoning/action) -> from llm_output world_log
- [TASK] messages (proactive proposal) -> from task world_log
- tool-response shares timestamp with preceding assistant
- environment notifications already self-timestamped in content
- system prompt, available_tools, current_app_state -> no timestamp needed
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
    """Find the user agent's first tool_call after a proposal."""
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


def annotate_event_timestamps(
    messages: list[dict], logs: list[dict], llm_input_idx: int, user_agent_id: str
) -> list[dict]:
    """Annotate llm_input messages with timestamps only for event messages.

    Collects timestamped world_log entries for the user agent, then matches:
    - assistant messages -> llm_output timestamps (by order)
    - tool-response -> inherits from preceding assistant
    - [TASK] user messages -> task log timestamps (by order)
    - everything else -> no timestamp (context)
    """
    # Collect ordered timestamps from world_logs for user agent
    llm_output_timestamps = []
    task_timestamps = []

    for i in range(0, llm_input_idx):
        log = logs[i]
        if log.get("agent_id") != user_agent_id:
            continue
        lt = log.get("log_type", "")
        ts = log.get("timestamp", 0)
        if lt == "llm_output":
            llm_output_timestamps.append(ts)
        elif lt == "task":
            # Only tasks with actual content (proposals, not empty initial tasks)
            content = log.get("content", "")
            if content and str(content).strip():
                task_timestamps.append(ts)

    llm_output_idx = 0
    task_idx = 0
    last_assistant_ts = None

    annotated = []
    for msg in messages:
        role = msg.get("role", "")
        content = str(msg.get("content", ""))
        ts = None
        msg_type = None

        if role == "assistant":
            # User agent reasoning/action
            if llm_output_idx < len(llm_output_timestamps):
                ts = llm_output_timestamps[llm_output_idx]
                llm_output_idx += 1
            last_assistant_ts = ts
            msg_type = "user_action"

        elif role == "tool-response":
            # Observation from tool call - shares timestamp with preceding assistant
            ts = last_assistant_ts
            msg_type = "tool_observation"

        elif role == "user" and content.startswith("[TASK]:"):
            # Proposal from proactive agent
            if task_idx < len(task_timestamps):
                ts = task_timestamps[task_idx]
                task_idx += 1
            msg_type = "proposal"

        elif role == "user" and content.startswith("Environment notifications"):
            msg_type = "environment_notification"
            # Self-timestamped in content, no annotation needed

        elif role == "user" and content.startswith("Available Actions"):
            msg_type = "available_tools"

        elif role == "user" and content.startswith("Current app state"):
            msg_type = "current_app_state"

        elif role == "system":
            msg_type = "system_prompt"

        else:
            msg_type = "unknown"

        annotated.append({
            **msg,
            "timestamp": ts,
            "msg_type": msg_type,
        })

    return annotated


def find_gathered_context(
    logs: list[dict], user_agent_id: str, first_action_idx: int, proposal_msg_count: int
) -> dict | None:
    """For gather_context decisions, find what was gathered before eventual accept/reject."""
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
                        final_messages = json.loads(content) if isinstance(content, str) else content
                        final_decision = "accept" if "accept_proposal" in tool_name else "reject"
                        delta_messages = final_messages[proposal_msg_count:]
                        return {
                            "final_decision": final_decision,
                            "final_llm_input_idx": j,
                            "delta_msg_count": len(delta_messages),
                            "total_msg_count": len(final_messages),
                            "delta_messages": delta_messages,
                        }
                break
    return None


def parse_single_trace(trace_path: str) -> dict | None:
    """Parse a single trace and return structured decision point data."""
    with open(trace_path) as f:
        data = json.load(f)
    logs = data.get("world_logs", [])
    logs = [json.loads(l) if isinstance(l, str) else l for l in logs]

    agents = identify_agents(logs)
    user_id = agents.get("user")
    observe_id = agents.get("observe")
    execute_id = agents.get("execute")

    if not user_id or not observe_id:
        return {"status": "error", "reason": "missing_agents", "file": trace_path}

    proposals = find_proposals(logs, observe_id)
    if not proposals:
        return {"status": "no_proposal", "file": trace_path}

    execute_first_ts = find_execute_agent_first_call(logs, execute_id)

    # Only process the first valid proposal (before execute agent)
    proposal = proposals[0]
    if execute_first_ts and proposal["timestamp"] >= execute_first_ts:
        return {"status": "skipped_post_execute", "file": trace_path}

    result = find_llm_input_after_proposal(logs, proposal["index"], user_id)
    if not result:
        return {"status": "error", "reason": "no_llm_input", "file": trace_path}
    llm_input_idx, messages = result

    # Annotate messages
    annotated = annotate_event_timestamps(messages, logs, llm_input_idx, user_id)

    # Classify decision
    first_action = find_first_user_action_after_proposal(logs, proposal["index"], user_id)
    if not first_action:
        return {"status": "error", "reason": "no_user_action", "file": trace_path}

    result_data = {
        "status": "ok",
        "file": trace_path,
        "proposal_content": str(proposal.get("content", ""))[:100],
        "proposal_timestamp": proposal["timestamp"],
        "decision": first_action["decision"],
        "decision_tool": first_action["tool_name"],
        "msg_count": len(messages),
        "annotated_messages": annotated,
        "msg_type_counts": {},
        "timestamps_assigned": 0,
        "timestamps_missing": 0,
    }

    # Count message types and timestamp coverage
    for msg in annotated:
        mt = msg.get("msg_type", "unknown")
        result_data["msg_type_counts"][mt] = result_data["msg_type_counts"].get(mt, 0) + 1
        if msg.get("timestamp") is not None:
            result_data["timestamps_assigned"] += 1
        else:
            # Only count as missing if this type SHOULD have a timestamp
            if mt in ("user_action", "tool_observation", "proposal"):
                result_data["timestamps_missing"] += 1

    # For gather_context, find delta
    if first_action["decision"] == "gather_context":
        gc_data = find_gathered_context(logs, user_id, first_action["index"], len(messages))
        result_data["gather_context"] = gc_data

    return result_data


def main(trace_path: str) -> None:
    """Run on a single trace with detailed output."""
    result = parse_single_trace(trace_path)
    if not result:
        print("ERROR: parse returned None")
        return

    if result["status"] != "ok":
        print(f"Status: {result['status']} ({result.get('reason', '')})")
        return

    print(f"File: {Path(result['file']).name}")
    print(f"Proposal: {result['proposal_content']}")
    print(f"Decision: {result['decision']} ({result['decision_tool']})")
    print(f"Messages: {result['msg_count']}")
    print(
        f"Timestamps: {result['timestamps_assigned']} assigned, {result['timestamps_missing']} missing (for event types)"
    )
    print(f"Message types: {result['msg_type_counts']}")

    print("\nAnnotated messages:")
    for i, msg in enumerate(result["annotated_messages"]):
        role = msg.get("role", "?")
        mt = msg.get("msg_type", "?")
        ts = msg.get("timestamp")
        content = str(msg.get("content", ""))[:80]
        ts_str = f"ts={ts:.2f}" if ts else "no-ts"
        print(f"  [{i:2d}] {role:15s} ({mt:25s}) {ts_str:>20s} | {content}")

    if result.get("gather_context"):
        gc = result["gather_context"]
        if gc:
            print(f"\nGather context -> final decision: {gc['final_decision']}")
            print(f"  Delta: {gc['delta_msg_count']} additional messages")
            for i, msg in enumerate(gc["delta_messages"]):
                role = msg.get("role", "?")
                content = str(msg.get("content", ""))[:80]
                print(f"  delta[{i}] {role:15s} | {content}")


def run_batch(traces_dir: str, max_traces: int = 50) -> None:
    """Run on multiple traces and produce consolidated analysis."""
    traces_base = Path(traces_dir)
    results = []
    per_model_stats: dict[str, dict[str, int]] = {}

    trace_count = 0
    for model_dir in sorted(traces_base.iterdir()):
        if not model_dir.is_dir():
            continue
        model_name = model_dir.name
        if model_name not in per_model_stats:
            per_model_stats[model_name] = {
                "accept": 0,
                "reject": 0,
                "gather_context": 0,
                "no_proposal": 0,
                "error": 0,
                "total": 0,
            }

        for trace_file in sorted(model_dir.glob("*.json")):
            if trace_count >= max_traces:
                break
            trace_count += 1
            per_model_stats[model_name]["total"] += 1

            result = parse_single_trace(str(trace_file))
            if not result:
                per_model_stats[model_name]["error"] += 1
                continue

            results.append(result)
            status = result["status"]
            if status == "ok":
                per_model_stats[model_name][result["decision"]] += 1
            elif status == "no_proposal":
                per_model_stats[model_name]["no_proposal"] += 1
            else:
                per_model_stats[model_name]["error"] += 1

        if trace_count >= max_traces:
            break

    # Summary
    ok_results = [r for r in results if r["status"] == "ok"]
    total = len(results)
    decisions = {"accept": 0, "reject": 0, "gather_context": 0}
    for r in ok_results:
        decisions[r["decision"]] += 1

    timestamp_issues = sum(1 for r in ok_results if r["timestamps_missing"] > 0)

    # Gather context analysis
    gc_results = [r for r in ok_results if r["decision"] == "gather_context" and r.get("gather_context")]
    gc_with_final = [r for r in gc_results if r["gather_context"] is not None]
    gc_final_accept = sum(1 for r in gc_with_final if r["gather_context"]["final_decision"] == "accept")
    gc_final_reject = sum(1 for r in gc_with_final if r["gather_context"]["final_decision"] == "reject")
    gc_no_final = sum(1 for r in ok_results if r["decision"] == "gather_context" and not r.get("gather_context"))

    print(f"\n{'=' * 70}")
    print(f"BATCH RESULTS ({trace_count} traces processed, {len(ok_results)} valid decision points)")
    print(f"{'=' * 70}")

    print("\n--- Overall Decision Distribution ---")
    for d, count in sorted(decisions.items()):
        pct = f"({count / len(ok_results) * 100:.1f}%)" if ok_results else ""
        print(f"  {d:20s}: {count:4d} {pct}")

    no_proposal = sum(1 for r in results if r["status"] == "no_proposal")
    errors = sum(1 for r in results if r["status"] in ("error", "skipped_post_execute"))
    print(f"  {'no_proposal':20s}: {no_proposal:4d}")
    print(f"  {'errors/skipped':20s}: {errors:4d}")

    print("\n--- Per Proactive Model ---")
    print(f"  {'Model':<60s} {'Acc':>4s} {'Rej':>4s} {'GC':>4s} {'NoPr':>4s} {'Err':>4s} {'Tot':>4s}")
    for model_name, stats in sorted(per_model_stats.items()):
        short_name = model_name.split("_enmi")[0].replace("obs_", "").replace("_exec_", " / ")
        print(
            f"  {short_name:<60s} {stats['accept']:4d} {stats['reject']:4d} {stats['gather_context']:4d} {stats['no_proposal']:4d} {stats['error']:4d} {stats['total']:4d}"
        )

    print("\n--- Timestamp Annotation Quality ---")
    print(f"  Traces with missing event timestamps: {timestamp_issues}/{len(ok_results)}")

    # Message type distribution
    all_msg_types: dict[str, int] = {}
    for r in ok_results:
        for mt, count in r["msg_type_counts"].items():
            all_msg_types[mt] = all_msg_types.get(mt, 0) + count

    print("\n--- Message Type Distribution (across all valid traces) ---")
    for mt, count in sorted(all_msg_types.items(), key=lambda x: -x[1]):
        print(f"  {mt:25s}: {count:5d}")

    if gc_results:
        print("\n--- Gather Context Analysis ---")
        print(f"  Total gather_context decisions: {decisions['gather_context']}")
        print(f"  With eventual accept/reject:    {len(gc_with_final)}")
        print(f"    -> accepted after gathering:  {gc_final_accept}")
        print(f"    -> rejected after gathering:  {gc_final_reject}")
        print(f"  No final decision found:        {gc_no_final}")
        if gc_with_final:
            avg_delta = sum(r["gather_context"]["delta_msg_count"] for r in gc_with_final) / len(gc_with_final)
            print(f"  Avg additional messages gathered: {avg_delta:.1f}")

    # Sample gather_context tools
    gc_tools: dict[str, int] = {}
    for r in ok_results:
        if r["decision"] == "gather_context":
            tool = r["decision_tool"]
            # Extract app name
            app = tool.split("__")[0] if "__" in tool else tool
            gc_tools[app] = gc_tools.get(app, 0) + 1

    if gc_tools:
        print("\n--- Gather Context: First Tool Called (by app) ---")
        for tool, count in sorted(gc_tools.items(), key=lambda x: -x[1]):
            print(f"  {tool:30s}: {count:3d}")

    print(f"\n{'=' * 70}")


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "--batch":
        traces_dir = (
            sys.argv[2] if len(sys.argv) > 2 else "traces/paper_benchmark_full_user_gpt-5-mini_mt_10_umi_1_omi_5_emi_10"
        )
        max_traces = int(sys.argv[3]) if len(sys.argv) > 3 else 50
        run_batch(traces_dir, max_traces)
    elif len(sys.argv) < 2:
        trace_path = "traces/paper_benchmark_full_user_gpt-5-mini_mt_10_umi_1_omi_5_emi_10/obs_claude-4.5-sonnet_exec_claude-4.5-sonnet_enmi_0_es_42_tfp_0.0/note_update_reflects_meeting_changes_run_4.json"
        main(trace_path)
    else:
        main(sys.argv[1])
