"""
Exchange matching and wallet annotation module for identifying custodial endpoints.
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional

# Base directory of the project
BASE_DIR = Path(__file__).resolve().parent.parent
ETH_DATA_PATH = BASE_DIR / "data" / "exchange_addresses.json"
TRON_DATA_PATH = BASE_DIR / "data" / "tron_exchange_addresses.json"

# In-memory cache for exchange databases keyed by chain
_EXCHANGE_DB: Dict[str, Dict[str, str]] = {"ethereum": None, "tron": None}


def load_exchange_db(chain: str = "ethereum", filepath: Optional[Path] = None) -> Dict[str, str]:
    """
    Loads known exchange addresses from the JSON data file for the specified chain.
    """
    global _EXCHANGE_DB
    
    if _EXCHANGE_DB.get(chain) is not None and filepath is None:
        return _EXCHANGE_DB[chain]

    if filepath:
        target_file = filepath
    else:
        target_file = TRON_DATA_PATH if chain == "tron" else ETH_DATA_PATH

    exchange_map: Dict[str, str] = {}

    if not target_file.exists():
        print(f"[Warning] Exchange database file not found at: {target_file}")
        return exchange_map

    try:
        with open(target_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                for entry in data:
                    addr = entry.get("address", "").strip()
                    # TRON addresses are case-sensitive Base58, so don't lowercase them.
                    if chain == "ethereum":
                        addr = addr.lower()
                    
                    name = entry.get("exchange_name", "").strip()
                    if addr and name:
                        exchange_map[addr] = name
    except Exception as e:
        print(f"[Error] Failed to load exchange database: {e}")

    if filepath is None:
        _EXCHANGE_DB[chain] = exchange_map

    return exchange_map


def match_exchange(address: Optional[str], chain: str = "ethereum") -> Optional[str]:
    """
    Checks if a given address matches a known cryptocurrency exchange for the chain.
    """
    if not address:
        return None

    db = load_exchange_db(chain=chain)
    
    lookup_addr = address.strip()
    if chain == "ethereum":
        lookup_addr = lookup_addr.lower()
        
    return db.get(lookup_addr, None)


def annotate_tree(trace_tree: Dict[str, Any], chain: str = "ethereum") -> Dict[str, Any]:
    """
    Recursively walks a trace tree from trace_wallet(), annotating each node
    with exchange identity if matched.
    """
    if not isinstance(trace_tree, dict):
        return trace_tree

    # Check root address or node destination address
    target_addr = trace_tree.get("to_address") or trace_tree.get("address")
    exchange = match_exchange(target_addr, chain=chain)
    trace_tree["exchange_match"] = exchange

    if exchange:
        trace_tree["trace_stopped"] = True
        trace_tree["children"] = []
        return trace_tree

    # Recursively annotate child nodes
    annotated_children = []
    for child in trace_tree.get("children", []):
        annotated_child = annotate_tree(child, chain=chain)
        annotated_children.append(annotated_child)

    trace_tree["children"] = annotated_children
    return trace_tree


if __name__ == "__main__":
    try:
        from backend.trace_engine import trace_wallet
    except ImportError:
        from trace_engine import trace_wallet

    test_addr = "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"
    print(f"Tracing and annotating wallet: {test_addr} with max_hops=2...\n")
    raw_tree = trace_wallet(test_addr, max_hops=2)
    annotated_tree = annotate_tree(raw_tree)
    print(json.dumps(annotated_tree, indent=2))
