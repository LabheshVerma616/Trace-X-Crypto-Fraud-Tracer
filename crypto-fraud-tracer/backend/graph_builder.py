"""
Fund-flow graph visualization using Pyvis.
"""

import tempfile
import os
from pyvis.network import Network

def format_address(address: str) -> str:
    if not address or len(address) < 10:
        return address
    return f"{address[:6]}...{address[-4:]}"

def build_graph_html(
    trace_tree: dict,
    chain: str = "ethereum",
    exchange_color: str = "#e63946",
    mixer_color: str = "#f4a261",
    normal_color: str = "#4a90d9",
    origin_color: str = "#a78bfa"
) -> str:
    """
    Creates an interactive Pyvis Network graph from a trace tree.
    Returns the graph HTML as a string.
    """
    unit = "ETH"
    decimals = 2
    if chain == "bitcoin":
        unit = "BTC"
        decimals = 6
    elif chain == "tron":
        unit = "TRX"
    net = Network(
        height="700px", 
        width="100%", 
        directed=True, 
        bgcolor="#0e1117", 
        font_color="white"
    )
    
    # Use a stable physics layout to prevent excessive bouncing
    net.force_atlas_2based(gravity=-50, central_gravity=0.01, spring_length=200, spring_strength=0.08, damping=0.4, overlap=0)
    
    nodes_added = set()

    def add_node_if_missing(node_addr: str, node_data: dict, is_origin: bool = False):
        if node_addr in nodes_added:
            return
            
        color = normal_color
        label = format_address(node_addr)
        title_text = node_addr
        
        exchange = node_data.get("exchange_match")
        obf = node_data.get("obfuscation", {})
        
        if is_origin:
            color = origin_color
            label = f"[ORIGIN] {label}"
            title_text = f"[ORIGIN] {title_text}"
        elif exchange:
            color = exchange_color
            label += f" [{exchange}]"
            title_text += f"\nExchange: {exchange}"
        elif obf.get("is_obfuscated"):
            color = mixer_color
            if obf.get("name"):
                label += f" [{obf['name']}]"
                title_text += f"\nObfuscation: {obf['name']}"
            else:
                label += f" [{obf.get('type', 'mixer')}]"
                title_text += f"\nObfuscation: {obf.get('type', 'mixer')}"
                
        net.add_node(
            node_addr, 
            label=label, 
            color=color, 
            title=title_text, 
            size=20,
            font={"size": 16, "color": "white"}
        )
        nodes_added.add(node_addr)

    def traverse(node: dict, parent_addr: str = None, edge_value: float = None):
        current_addr = node.get("to_address") or node.get("address")
        if not current_addr:
            return
            
        add_node_if_missing(current_addr, node, is_origin=(parent_addr is None))
        
        if parent_addr:
            # Create directed edge from parent to current
            edge_label = f"{edge_value:.{decimals}f} {unit}" if edge_value is not None else ""
            net.add_edge(parent_addr, current_addr, label=edge_label, title=edge_label)
            
        for child in node.get("children", []):
            traverse(child, current_addr, child.get("value_eth"))

    traverse(trace_tree)
    
    # Generate HTML string by writing to temp file and reading back
    with tempfile.NamedTemporaryFile(delete=False, suffix=".html") as tmp:
        tmp_name = tmp.name
        
    try:
        net.save_graph(tmp_name)
        with open(tmp_name, "r", encoding="utf-8") as f:
            html_data = f.read()
    finally:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)
            
    return html_data
