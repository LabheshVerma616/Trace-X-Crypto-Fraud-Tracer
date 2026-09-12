import json
import requests
from config import ETHERSCAN_API_KEY, ETHERSCAN_BASE_URL, ETHERSCAN_CHAIN_ID

TEST_ADDRESS = "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"


def test_etherscan_connection():
    """
    Tests connection to Etherscan API (V2) by fetching the transaction list
    for a sample address and printing the first transaction object.
    """
    params = {
        "chainid": ETHERSCAN_CHAIN_ID,
        "module": "account",
        "action": "txlist",
        "address": TEST_ADDRESS,
        "startblock": 0,
        "endblock": 99999999,
        "sort": "asc",
        "apikey": ETHERSCAN_API_KEY,
    }

    try:
        print(f"Connecting to Etherscan API ({ETHERSCAN_BASE_URL})...")
        response = requests.get(ETHERSCAN_BASE_URL, params=params, timeout=10)
        print(f"HTTP Status Code: {response.status_code}")

        response.raise_for_status()
        data = response.json()

        status = data.get("status")
        message = data.get("message")
        result = data.get("result")

        if status == "1" and isinstance(result, list) and len(result) > 0:
            print("\nFirst transaction object (result[0]):")
            print(json.dumps(result[0], indent=2))
        else:
            print(f"Etherscan Status: {status}, Message: {message}")
            if isinstance(result, list) and len(result) > 0:
                print("\nFirst transaction object (result[0]):")
                print(json.dumps(result[0], indent=2))
            elif isinstance(result, str):
                print(f"Result: {result}")
            else:
                print(f"Result: {result}")

    except requests.exceptions.RequestException as e:
        print(f"API request failed: {e}")
    except ValueError as e:
        print(f"Failed to parse JSON response: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")


if __name__ == "__main__":
    test_etherscan_connection()
