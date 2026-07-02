# ETF Daily Data Collection
# Runs via Hermes cron — collects market snapshot for research
Set-Location D:\龙虾\.openclaw\etf-platform
python -m etf_platform.archive.collector --quick 2>&1