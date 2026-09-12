import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from the project root .env file
BASE_DIR = Path(__file__).resolve().parent.parent
dotenv_path = BASE_DIR / ".env"
load_dotenv(dotenv_path=dotenv_path)

ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY", "")
ETHERSCAN_BASE_URL = "https://api.etherscan.io/v2/api"
ETHERSCAN_CHAIN_ID = int(os.getenv("ETHERSCAN_CHAIN_ID", "1"))
