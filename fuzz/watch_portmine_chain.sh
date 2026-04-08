#!/bin/bash
# Wait for port_mine to drain, then chain downstream rebuilds.
cd /home/test/EP4CE6/fuzz
export PATH=$PATH:$HOME/intelFPGA_lite/21.1/quartus/bin
LOG=/tmp/portmine_chain.log
echo "[watch] start $(date)" > $LOG
while pgrep -f port_mine.py > /dev/null || pgrep -f 'quartus_map.*lits_pair' > /dev/null; do
  sleep 30
done
echo "[watch] mining drained $(date)" >> $LOG
python3 route_signatures.py >> $LOG 2>&1 && echo "[watch] route_signatures OK" >> $LOG
python3 chipdb_export.py >> $LOG 2>&1 && echo "[watch] chipdb_export OK" >> $LOG
python3 test_fasm_semantic.py >> $LOG 2>&1 && echo "[watch] test_fasm_semantic OK" >> $LOG
echo "[watch] done $(date)" >> $LOG
