import collections
import time
import requests
import re
import json
import os
from typing import Any, Dict, List, Tuple

try:
    from backend.bitcoin_config import ESPLORA_BASE_URL, SATOSHIS_PER_BTC, MAX_HOPS
except ImportError:
    from bitcoin_config import ESPLORA_BASE_URL, SATOSHIS_PER_BTC, MAX_HOPS

def is_bitcoin_address(address: str) -> bool:
    if re.match(r"^[13][a-km-zA-HJ-NP-Z1-9]{25,34}$", address):
        return True
    if re.match(r"^bc1[a-zA-HJ-NP-Z0-9]{25,90}$", address):
        return True
    return False

def get_address_txs(address: str) -> list:
    url = ESPLORA_BASE_URL + "/address/" + str(address) + "/txs"
    try:
        print(f"[BTC DEBUG] Requesting URL: {url}", flush=True)
        response = requests.get(url, timeout=15)
        print(f"[BTC DEBUG] Status: {response.status_code}, Body preview: {response.text[:300]}", flush=True)
        response.raise_for_status()
        data = response.json()
        if isinstance(data, list):
            return data
        return []
    except Exception as e:
        print(f"[BTC DEBUG] Exception: {repr(e)}", flush=True)
        return []
    finally:
        time.sleep(0.3)

def get_tx_detail(txid: str) -> dict:
    url = ESPLORA_BASE_URL + "/tx/" + str(txid)
    try:
        print(f"[BTC DEBUG] Requesting URL: {url}", flush=True)
        response = requests.get(url, timeout=15)
        print(f"[BTC DEBUG] Status: {response.status_code}, Body preview: {response.text[:300]}", flush=True)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"[BTC DEBUG] Exception: {repr(e)}", flush=True)
        return {}
    finally:
        time.sleep(0.3)

def is_likely_change(output: dict, all_outputs: list, address_history_cache: dict) -> Tuple[bool, str]:
    address = output.get("scriptpubkey_address")
    if not address:
        return False, "low"
    
    if address not in address_history_cache:
        txs = get_address_txs(address)
        address_history_cache[address] = txs
    
    history_len = len(address_history_cache[address])
    has_prior_history = history_len > 1
    
    max_value = 0
    for out in all_outputs:
        val = out.get("value", 0)
        if val > max_value:
            max_value = val
            
    is_largest = (output.get("value", 0) == max_value)
    
    if not has_prior_history and not is_largest:
        return True, "medium"
    
    return False, "low"

def _load_bitcoin_exchanges():
    try:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        file_path = os.path.join(base_dir, "data", "bitcoin_exchange_addresses.json")
        if not os.path.exists(file_path):
            file_path = "data/bitcoin_exchange_addresses.json"
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[Warning] Could not load bitcoin_exchange_addresses.json: {e}")
        return []

def trace_bitcoin_wallet(origin_address: str, max_hops: int = MAX_HOPS) -> dict:
    root_node: Dict[str, Any] = {
        "address": origin_address,
        "hop_number": 0,
        "children": [],
    }

    queue = collections.deque([
        (root_node, origin_address, 0, {origin_address})
    ])

    address_history_cache = {}
    exchanges_data = _load_bitcoin_exchanges()
    exchange_addresses = {ex["address"]: ex["exchange_name"] for ex in exchanges_data if "address" in ex}
    
    if origin_address in exchange_addresses:
        root_node["exchange_match"] = exchange_addresses[origin_address]
        root_node["trace_stopped"] = True
        return root_node

    while queue:
        parent_node, current_addr, current_hop, path_visited = queue.popleft()

        if current_hop >= max_hops:
            continue
            
        if current_addr in exchange_addresses and current_hop > 0:
            continue

        if current_addr not in address_history_cache:
            address_history_cache[current_addr] = get_address_txs(current_addr)
        txs = address_history_cache[current_addr]
        
        outgoing_txs = []
        for tx in txs:
            is_outgoing = False
            for vin in tx.get("vin", []):
                prevout = vin.get("prevout", {})
                spk_address = prevout.get("scriptpubkey_address") if prevout else None
                match = (spk_address == current_addr)
                print(f"[BTC DEBUG COMPARISON] current_addr: '{current_addr}', prevout_addr: '{spk_address}', Match: {match}", flush=True)
                
                if prevout and prevout.get("scriptpubkey_address") == current_addr:
                    is_outgoing = True
                    break
            if is_outgoing:
                outgoing_txs.append(tx)
        
        for tx in outgoing_txs[:3]:
            txid = tx.get("txid")
            if not txid:
                continue
                
            tx_detail = get_tx_detail(txid)
            if not tx_detail:
                continue

            vout = tx_detail.get("vout", [])
            timestamp = str(tx_detail.get("status", {}).get("block_time", 0))
            
            total_outputs = len(vout)
            change_count = 0
            real_hop_count = 0
            
            for output in vout:
                to_addr = output.get("scriptpubkey_address")
                if not to_addr:
                    continue
                    
                value_sats = output.get("value", 0)
                if value_sats == 0:
                    continue
                    
                exch_name = exchange_addresses.get(to_addr)
                value_btc = value_sats / SATOSHIS_PER_BTC
                
                if exch_name:
                    # Skip change detection, mark directly as an exchange hop
                    child_node: Dict[str, Any] = {
                        "to_address": to_addr,
                        "value_eth": value_btc,
                        "tx_hash": txid,
                        "timestamp": timestamp,
                        "hop_number": current_hop + 1,
                        "children": [],
                        "exchange_match": exch_name,
                        "trace_stopped": True
                    }
                    parent_node["children"].append(child_node)
                    real_hop_count += 1
                    continue

                # Run change detection only for non-exchange outputs
                is_change, conf = is_likely_change(output, vout, address_history_cache)
                if is_change:
                    change_count += 1
                    continue
                    
                child_node: Dict[str, Any] = {
                    "to_address": to_addr,
                    "value_eth": value_btc,
                    "tx_hash": txid,
                    "timestamp": timestamp,
                    "hop_number": current_hop + 1,
                    "children": [],
                }
                
                parent_node["children"].append(child_node)
                real_hop_count += 1
                
                if to_addr not in path_visited and (current_hop + 1) < max_hops:
                    queue.append((
                        child_node,
                        to_addr,
                        current_hop + 1,
                        path_visited | {to_addr},
                    ))
            print(f"[BTC DEBUG] Tx {txid} processed. Total outputs: {total_outputs}, Change: {change_count}, Real Hops: {real_hop_count}", flush=True)
                    
    print(f"[BTC DEBUG] Returning tree. Root children count: {len(root_node['children'])}", flush=True)
    return root_node
