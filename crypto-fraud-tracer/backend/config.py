import os
from pathlib import Path

# 1. Try to get the API key from streamlit secrets if available
ETHERSCAN_API_KEY = ""
try:
    import streamlit as st
    if "ETHERSCAN_API_KEY" in st.secrets:
        ETHERSCAN_API_KEY = st.secrets["ETHERSCAN_API_KEY"]
except ImportError:
    pass

# 2. Only import dotenv for local dev convenience, do not crash if missing
try:
    from dotenv import load_dotenv
    BASE_DIR = Path(__file__).resolve().parent.parent
    dotenv_path = BASE_DIR / ".env"
    load_dotenv(dotenv_path=dotenv_path)
except ImportError:
    pass

# 3. Fallback to OS environment variables if st.secrets was missing or empty
if not ETHERSCAN_API_KEY:
    ETHERSCAN_API_KEY = os.environ.get("ETHERSCAN_API_KEY", "")

ETHERSCAN_BASE_URL = "https://api.etherscan.io/v2/api"
ETHERSCAN_CHAIN_ID = int(os.environ.get("ETHERSCAN_CHAIN_ID", "1"))
