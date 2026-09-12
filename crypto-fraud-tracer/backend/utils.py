import re

def is_ethereum_address(address: str) -> bool:
    """Check if the address is a valid Ethereum format (0x followed by 40 hex chars)."""
    return bool(re.match(r"^0x[a-fA-F0-9]{40}$", address))

def is_tron_address(address: str) -> bool:
    """Check if the address is a valid TRON format (Starts with T, Base58, 34 chars long)."""
    # Base58 does not contain 0, O, I, l
    return bool(re.match(r"^T[123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz]{33}$", address))


import hashlib
import base58

def hex_to_base58_address(hex_str: str) -> str:
    """Convert TRON hex address to Base58Check string format."""
    if hex_str.startswith("0x"):
        hex_str = hex_str[2:]
    if len(hex_str) == 42 and hex_str.startswith("41"):
        b = bytes.fromhex(hex_str)
        return base58.b58encode_check(b).decode("utf-8")
    return hex_str

