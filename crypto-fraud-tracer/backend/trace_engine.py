"""
Multi-hop blockchain transaction tracing engine for tracking fund movements across wallet addresses.
"""

import collections
import json
import time
from typing import Any, Dict, List, Union
import requests

try:
    from backend.config import ETHERSCAN_API_KEY, ETHERSCAN_BASE_URL, ETHERSCAN_CHAIN_ID
except ImportError:
    from config import ETHERSCAN_API_KEY, ETHERSCAN_BASE_URL, ETHERSCAN_CHAIN_ID


def wei_to_eth(wei_value: Union[int, str, float]) -> float:
    """
    Converts a Wei value (integer or string representation) to ETH as a float.

    Args:
        wei_value: The transaction value in Wei.

    Returns:
        float: Value in ETH (divided by 10^18). Returns 0.0 on invalid input.
    """
    try:
        return float(wei_value) / (10 ** 18)
    except (ValueError, TypeError):
        return 0.0


def get_transactions(address: str) -> List[Dict[str, Any]]:
    """
    Fetches the normal transaction list for a given Ethereum address using Etherscan V2 API.
    Enforces a 0.25-second delay after each call to respect rate limits.

    Args:
        address: Ethereum wallet address (0x...).

    Returns:
        List[Dict[str, Any]]: List of transaction dictionaries, or empty list on error.
    """
    params = {
        "chainid": ETHERSCAN_CHAIN_ID,
        "module": "account",
        "action": "txlist",
        "address": address,
        "startblock": 0,
        "endblock": 99999999,
        "sort": "asc",
        "apikey": ETHERSCAN_API_KEY,
    }

    try:
        response = requests.get(ETHERSCAN_BASE_URL, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()

        if data.get("status") == "1" and isinstance(data.get("result"), list):
            return data["result"]
        return []
    except (requests.exceptions.RequestException, ValueError, KeyError) as e:
        print(f"[Warning] Failed to fetch transactions for {address}: {e}")
        return []
    finally:
        time.sleep(0.25)


def get_top_outgoing(
    address: str,
    transactions: List[Dict[str, Any]],
    top_n: int = 3,
    min_eth: float = 0.01,
) -> List[Dict[str, Any]]:
    """
    Filters and returns the top outgoing transactions from a given address.

    Filters applied:
    - 'from' address matches the specified address (case-insensitive)
    - Successful transactions only (isError != '1')
    - Valid destination 'to' address
    - Value converted to ETH is greater than or equal to min_eth

    Args:
        address: The source Ethereum address.
        transactions: List of transaction dictionaries for the address.
        top_n: Maximum number of top transactions to return (sorted descending by value).
        min_eth: Minimum ETH threshold for transactions to include.

    Returns:
        List[Dict[str, Any]]: Top N outgoing transaction objects sorted by value descending.
    """
    normalized_addr = address.lower()
    outgoing = []

    for tx in transactions:
        from_addr = tx.get("from", "").lower()
        is_error = tx.get("isError", "0")
        to_addr = tx.get("to")
        value_eth = wei_to_eth(tx.get("value", 0))

        if from_addr == normalized_addr and is_error != "1" and to_addr and value_eth >= min_eth:
            outgoing.append(tx)

    # Sort descending by transaction value in Wei
    outgoing.sort(key=lambda tx: float(tx.get("value", 0)), reverse=True)
    return outgoing[:top_n]


def trace_wallet(start_address: str, max_hops: int = 4) -> Dict[str, Any]:
    """
    Performs a breadth-first search (BFS) trace of high-value fund movements starting
    from a source wallet address.

    At each hop:
    1. Fetches normal transactions for the current node's address.
    2. Identifies the top outgoing transfers (above min_eth threshold).
    3. Traverses each destination ('to') address up to max_hops.
    4. Prevents circular references by tracking visited addresses in the current path.

    Args:
        start_address: Starting Ethereum address for the trace.
        max_hops: Maximum hop depth to explore (default: 4).

    Returns:
        Dict[str, Any]: Nested tree representation of the fund flow where root has
        address, hop_number, and children list.
    """
    root_node: Dict[str, Any] = {
        "address": start_address,
        "hop_number": 0,
        "children": [],
    }

    # Queue contains: (parent_node_dict, current_address, current_hop, path_visited_set)
    queue = collections.deque([
        (root_node, start_address, 0, {start_address.lower()})
    ])

    while queue:
        parent_node, current_addr, current_hop, path_visited = queue.popleft()

        if current_hop >= max_hops:
            continue

        txs = get_transactions(current_addr)
        top_outgoing = get_top_outgoing(current_addr, txs, top_n=3, min_eth=0.01)

        for tx in top_outgoing:
            to_addr = tx.get("to", "")
            if not to_addr:
                continue

            value_eth = wei_to_eth(tx.get("value", 0))
            tx_hash = tx.get("hash", "")
            timestamp = tx.get("timeStamp", "")

            child_node: Dict[str, Any] = {
                "to_address": to_addr,
                "value_eth": value_eth,
                "tx_hash": tx_hash,
                "timestamp": timestamp,
                "hop_number": current_hop + 1,
                "children": [],
            }
            parent_node["children"].append(child_node)

            to_addr_lower = to_addr.lower()
            # Prevent circular loops within the active branch path
            if to_addr_lower not in path_visited and (current_hop + 1) < max_hops:
                queue.append((
                    child_node,
                    to_addr,
                    current_hop + 1,
                    path_visited | {to_addr_lower},
                ))

    return root_node


if __name__ == "__main__":
    test_addr = "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"
    print(f"Tracing wallet: {test_addr} with max_hops=2...\n")
    trace_result = trace_wallet(test_addr, max_hops=2)
    print(json.dumps(trace_result, indent=2))
