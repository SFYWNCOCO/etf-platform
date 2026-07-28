# ETF analysis package
# NOTE: Lazy imports only. Top-level imports of signals/causal trigger
# socket python311.dll conflict via data.events -> sina -> urllib -> socket.
# All downstream consumers (cli.py, l9_signals_enhanced.py) already use lazy imports.
