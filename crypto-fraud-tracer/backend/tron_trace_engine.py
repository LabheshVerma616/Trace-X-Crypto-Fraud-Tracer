import collections
import time
from typing import Any, Dict, List, Union
import requests

try:
    from backend.tron_config import TRONGRID_API_URL
    from backend.utils import hex_to_base58_address
except ImportError:
    from tron_config import TRONGRID_API_URL
    from utils import hex_to_base58_address

def sun_to_trx(sun_value: Union[int, str, float]) -> float:
    try:
        return float(sun_value) / 1_000_000
    except (ValueError, TypeError):
        return 0.0

def get_tron_transactions(address: str) -> List[Dict[str, Any]]:
    url = f"{TRONGRID_API_URL}/v1/accounts/{address}/transactions"
    params = {"only_to": "false", "only_from": "true", "limit": 200}
    
    try:
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        if data.get("success") == True and isinstance(data.get("data"), list):
            return data["data"]
        if "data" in data and isinstance(data["data"], list):
            return data["data"]
        return []
    except Exception as e:
        print(f"[Warning] Failed to fetch TRON transactions for {address}: {e}")
        return []
    finally:
        time.sleep(0.3)

def get_tron_trc20_transactions(address: str) -> List[Dict[str, Any]]:
    url = f"{TRONGRID_API_URL}/v1/accounts/{address}/transactions/trc20"
    params = {"only_to": "false", "only_from": "true", "limit": 200}
    
    try:
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        if data.get("success") == True and isinstance(data.get("data"), list):
            return data["data"]
        if "data" in data and isinstance(data["data"], list):
            return data["data"]
        return []
    except Exception as e:
        print(f"[Warning] Failed to fetch TRON TRC20 transactions for {address}: {e}")
        return []
    finally:
        time.sleep(0.3)

def get_top_outgoing_tron(
    address: str,
    transactions: List[Dict[str, Any]],
    trc20_transactions: List[Dict[str, Any]],
    top_n: int = 3,
    min_value: float = 0.01,
) -> List[Dict[str, Any]]:
    outgoing = []
    
    # Process native TRX transactions
    for tx in transactions:
        # Check if successful
        rets = tx.get("ret", [])
        if not rets or rets[0].get("contractRet") != "SUCCESS":
            continue
            
        raw_data = tx.get("raw_data", {})
        contracts = raw_data.get("contract", [])
        if not contracts:
            continue
            
        contract = contracts[0]
        if contract.get("type") != "TransferContract":
            continue
            
        value_data = contract.get("parameter", {}).get("value", {})
        from_hex = value_data.get("owner_address", "")
        to_hex = value_data.get("to_address", "")
        
        if not from_hex or not to_hex:
            continue
            
        from_addr = hex_to_base58_address(from_hex)
        to_addr = hex_to_base58_address(to_hex)
        
        amount_sun = value_data.get("amount", 0)
        value_trx = sun_to_trx(amount_sun)
        
        if from_addr == address and value_trx >= min_value:
            outgoing.append({
                "to": to_addr,
                "value": value_trx,
                "symbol": "TRX",
                "hash": tx.get("txID", ""),
                "timestamp": raw_data.get("timestamp", 0)
            })

    # Process TRC20 transactions
    for tx in trc20_transactions:
        from_addr = tx.get("from", "")
        to_addr = tx.get("to", "")
        if from_addr != address:
            continue
            
        token_info = tx.get("token_info", {})
        symbol = token_info.get("symbol", "UNKNOWN")
        decimals = int(token_info.get("decimals", 6))
        
        raw_value = float(tx.get("value", 0))
        real_value = raw_value / (10 ** decimals)
        
        if real_value >= min_value:
            outgoing.append({
                "to": to_addr,
                "value": real_value,
                "symbol": symbol,
                "hash": tx.get("transaction_id", ""),
                "timestamp": tx.get("block_timestamp", 0)
            })
            
    outgoing.sort(key=lambda x: x["value"], reverse=True)
    return outgoing[:top_n]

def trace_tron_wallet(start_address: str, max_hops: int = 4) -> Dict[str, Any]:
    root_node: Dict[str, Any] = {
        "address": start_address,
        "hop_number": 0,
        "children": [],
    }

    queue = collections.deque([
        (root_node, start_address, 0, {start_address})
    ])

    while queue:
        parent_node, current_addr, current_hop, path_visited = queue.popleft()

        if current_hop >= max_hops:
            continue

        txs = get_tron_transactions(current_addr)
        trc20_txs = get_tron_trc20_transactions(current_addr)
        top_outgoing = get_top_outgoing_tron(current_addr, txs, trc20_txs, top_n=3, min_value=0.01)

        for tx in top_outgoing:
            to_addr = tx["to"]
            value = tx["value"]
            symbol = tx["symbol"]
            tx_hash = tx["hash"]
            timestamp = str(tx["timestamp"])

            child_node: Dict[str, Any] = {
                "to_address": to_addr,
                "value_eth": value,  # kept as value_eth for structural compatibility with UI
                "symbol": symbol,
                "tx_hash": tx_hash,
                "timestamp": timestamp,
                "hop_number": current_hop + 1,
                "children": [],
            }
            parent_node["children"].append(child_node)

            if to_addr not in path_visited and (current_hop + 1) < max_hops:
                queue.append((
                    child_node,
                    to_addr,
                    current_hop + 1,
                    path_visited | {to_addr},
                ))

    return root_node

