"""
Risk scoring and obfuscation analysis engine for cryptocurrency wallet traces.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# Base directory of the project
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_PATH = BASE_DIR / "data" / "mixer_addresses.json"

# In-memory cache for risk/obfuscation database
_RISK_DB: Optional[Dict[str, Dict[str, Any]]] = None


def load_risk_db(filepath: Optional[Path] = None) -> Dict[str, Dict[str, Any]]:
    """
    Loads known mixer and bridge addresses from the JSON data file into a dictionary
    keyed by lowercase address.

    Args:
        filepath: Optional custom path to mixer_addresses.json.

    Returns:
        Dict[str, Dict[str, Any]]: Mapping of lowercase address to metadata dict.
    """
    global _RISK_DB
    if _RISK_DB is not None and filepath is None:
        return _RISK_DB

    target_file = filepath or DATA_PATH
    risk_map: Dict[str, Dict[str, Any]] = {}

    if not target_file.exists():
        print(f"[Warning] Risk database file not found at: {target_file}")
        return risk_map

    try:
        with open(target_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                for entry in data:
                    addr = entry.get("address", "").strip().lower()
                    if addr:
                        risk_map[addr] = {
                            "type": entry.get("type"),
                            "name": entry.get("name"),
                            "label_source": entry.get("label_source"),
                        }
    except Exception as e:
        print(f"[Error] Failed to load risk database: {e}")

    if filepath is None:
        _RISK_DB = risk_map

    return risk_map


def check_obfuscation(address: Optional[str]) -> Dict[str, Any]:
    """
    Checks if a given Ethereum address matches a known mixer or cross-chain bridge.

    Args:
        address: Ethereum address string (0x...).

    Returns:
        Dict[str, Any]: {
            "is_obfuscated": bool,
            "type": "mixer" | "bridge" | None,
            "name": str | None
        }
    """
    if not address:
        return {"is_obfuscated": False, "type": None, "name": None}

    db = load_risk_db()
    entry = db.get(address.strip().lower())

    if entry:
        return {
            "is_obfuscated": True,
            "type": entry.get("type"),
            "name": entry.get("name"),
        }

    return {"is_obfuscated": False, "type": None, "name": None}


def calculate_risk_score(trace_tree: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Recursively walks an annotated trace tree, checking every node for mixer
    or bridge obfuscation, and calculates an overall risk score (0-100).

    Scoring rules:
    - +30 if any node reached a known exchange (exchange_match found)
    - +40 if any node interacted with a known mixer (high risk - active laundering)
    - +20 if any node interacted with a known bridge (cross-chain obfuscation attempt)
    - +10 if trace has multiple hops (3+) without reaching a custodial exchange

    Args:
        trace_tree: Tree dict produced by exchange_match.annotate_tree().

    Returns:
        Tuple[Dict[str, Any], Dict[str, Any]]:
            - Fully annotated trace tree (with "obfuscation" on each node)
            - Top-level summary dictionary:
              {
                  "risk_score": int,
                  "reached_exchange": bool,
                  "exchange_names": list[str],
                  "obfuscation_detected": bool,
                  "obfuscation_types": list[str]
              }
    """
    exchange_names: List[str] = []
    obfuscation_types: List[str] = []
    has_mixer = False
    has_bridge = False
    max_hop_recorded = 0

    def _walk_and_annotate(node: Dict[str, Any]):
        nonlocal has_mixer, has_bridge, max_hop_recorded

        if not isinstance(node, dict):
            return

        target_addr = node.get("to_address") or node.get("address")
        obf = check_obfuscation(target_addr)
        node["obfuscation"] = obf

        if obf.get("is_obfuscated"):
            obf_type = obf.get("type")
            if obf_type:
                obfuscation_types.append(obf_type)
                if obf_type == "mixer":
                    has_mixer = True
                elif obf_type == "bridge":
                    has_bridge = True

        exchange = node.get("exchange_match")
        if exchange:
            exchange_names.append(exchange)

        hop = node.get("hop_number", 0)
        if hop > max_hop_recorded:
            max_hop_recorded = hop

        for child in node.get("children", []):
            _walk_and_annotate(child)

    _walk_and_annotate(trace_tree)

    reached_exchange = len(exchange_names) > 0
    unique_exchanges = list(dict.fromkeys(exchange_names))
    unique_obfuscation_types = list(dict.fromkeys(obfuscation_types))
    obfuscation_detected = len(unique_obfuscation_types) > 0

    # Calculate overall risk score
    score = 0
    if reached_exchange:
        score += 30
    if has_mixer:
        score += 40
    if has_bridge:
        score += 20
    if max_hop_recorded >= 3 and not reached_exchange:
        score += 10

    final_risk_score = min(100, max(0, score))

    summary: Dict[str, Any] = {
        "risk_score": final_risk_score,
        "reached_exchange": reached_exchange,
        "exchange_names": unique_exchanges,
        "obfuscation_detected": obfuscation_detected,
        "obfuscation_types": unique_obfuscation_types,
    }

    # Also attach summary to tree for convenience
    trace_tree["summary"] = summary

    return trace_tree, summary


if __name__ == "__main__":
    try:
        from backend.trace_engine import trace_wallet
        from backend.exchange_match import annotate_tree
    except ImportError:
        from trace_engine import trace_wallet
        from exchange_match import annotate_tree

    test_addr = "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"
    print(f"Running full pipeline for {test_addr} with max_hops=2...\n")

    raw_tree = trace_wallet(test_addr, max_hops=2)
    annotated_tree = annotate_tree(raw_tree)
    _, summary = calculate_risk_score(annotated_tree)

    print("Summary:")
    print(json.dumps(summary, indent=2))
