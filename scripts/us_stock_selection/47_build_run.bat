@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d E:\dzhwork\quant\quant_lab
"C:\Users\Administrator\.conda\envs\aimodel\python.exe" -u "E:\dzhwork\quant\quant_lab\scripts\us_stock_selection\47_build_unified_adjusted_ohlcv_store.py" > "E:\dzhwork\quant\quant_lab\47_build_output.log" 2>&1
