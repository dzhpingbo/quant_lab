@echo off
cd /d E:\dzhwork\quant\quant_lab
python scripts\agent_loop\run_codex_auth_loop.py --config scripts\agent_loop\loop_config_auth.yaml --max-rounds 10
pause
