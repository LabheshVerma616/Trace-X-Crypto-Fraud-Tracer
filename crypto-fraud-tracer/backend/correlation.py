"""
Multi-case correlation and address convergence engine for crypto-fraud-tracer.
"""

from collections import defaultdict
import json
from typing import Any, Dict, List, Optional, Set

try:
    from backend.trace_engine import trace_wallet
    from backend.exchange_match import annotate_tree, match_exchange
    from backend.risk_score import calculate_risk_score
except ImportError:
    from trace_engine import trace_wallet
    from exchange_match import annotate_tree, match_exchange
    from risk_score import calculate_risk_score


def extract_all_addresses(trace_tree: Dict[str, Any]) -> List[str]:
    """
    Recursively walks a single annotated trace tree and extracts all unique
    addresses present (root address and all descendant to_addresses).

    Args:
        trace_tree: Trace tree dictionary.

    Returns:
        List[str]: Flat list of unique lowercase Ethereum addresses found in the tree.
    """
    addresses: List[str] = []

    def _walk(node: Dict[str, Any]):
        if not isinstance(node, dict):
            return

        addr = node.get("to_address") or node.get("address")
        if addr:
            addresses.append(addr.strip().lower())

        for child in node.get("children", []):
            _walk(child)

    _walk(trace_tree)
    # Deduplicate while preserving discovery order
    return list(dict.fromkeys(addresses))


def find_convergence(list_of_case_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Identifies convergence points across multiple investigative cases where
    funds from 2 or more distinct cases touch the same address.

    Args:
        list_of_case_results: List of dicts containing:
            {
                "case_id": str,
                "reported_address": str,
                "trace_tree": dict,
                "summary": dict
            }

    Returns:
        List[Dict[str, Any]]: Convergence findings sorted by num_cases descending,
        each containing:
            {
                "address": str,
                "case_ids": list[str],
                "num_cases": int,
                "is_exchange": bool,
                "exchange_name": str | None
            }
    """
    address_to_cases: Dict[str, Set[str]] = defaultdict(set)

    for case in list_of_case_results:
        case_id = case.get("case_id", "")
        trace_tree = case.get("trace_tree", {})
        if not trace_tree:
            continue

        case_addresses = extract_all_addresses(trace_tree)
        for addr in case_addresses:
            address_to_cases[addr].add(case_id)

    findings: List[Dict[str, Any]] = []

    for addr, case_ids_set in address_to_cases.items():
        if len(case_ids_set) >= 2:
            exchange_name = match_exchange(addr)
            findings.append({
                "address": addr,
                "case_ids": sorted(list(case_ids_set)),
                "num_cases": len(case_ids_set),
                "is_exchange": exchange_name is not None,
                "exchange_name": exchange_name,
            })

    # Sort results by num_cases descending, then alphabetically by address
    findings.sort(key=lambda x: (-x["num_cases"], x["address"]))
    return findings


def run_multi_case_analysis(
    case_inputs: List[Dict[str, str]],
    max_hops: int = 2,
) -> Dict[str, Any]:
    """
    Executes the full trace, exchange matching, and risk scoring pipeline
    for multiple reported cases, then computes convergence patterns across them.

    Args:
        case_inputs: List of {"case_id": str, "reported_address": str} dicts.
        max_hops: Maximum trace depth for each case (default: 2).

    Returns:
        Dict[str, Any]: {
            "case_results": list of individual case analysis results,
            "convergence_findings": list of detected convergence points
        }
    """
    case_results: List[Dict[str, Any]] = []

    for item in case_inputs:
        case_id = item.get("case_id", "")
        reported_address = item.get("reported_address", "").strip()

        if not reported_address:
            continue

        print(f"Analyzing {case_id} ({reported_address}) with max_hops={max_hops}...")
        raw_tree = trace_wallet(reported_address, max_hops=max_hops)
        annotated_tree = annotate_tree(raw_tree)
        final_tree, summary = calculate_risk_score(annotated_tree)

        case_results.append({
            "case_id": case_id,
            "reported_address": reported_address,
            "trace_tree": final_tree,
            "summary": summary,
        })

    convergence_findings = find_convergence(case_results)

    return {
        "case_results": case_results,
        "convergence_findings": convergence_findings,
    }


if __name__ == "__main__":
    fake_cases = [
        {
            "case_id": "CASE_001",
            "reported_address": "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
        },
        {
            "case_id": "CASE_002",
            "reported_address": "0x1db3439a222c519ab44bb1144fc28167b4fa6ee6",
        },
    ]

    print("Running multi-case analysis...\n")
    analysis_output = run_multi_case_analysis(fake_cases, max_hops=2)

    print("\nConvergence Findings:")
    print(json.dumps(analysis_output["convergence_findings"], indent=2))
