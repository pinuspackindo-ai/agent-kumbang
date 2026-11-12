"""
Tarik semua data HashMicro dengan SEKALI login:
  1. Bills (Accounting)
  2. Stock per-Warehouse (Inventory)
  3. Pricelist Items "New" (Point of Sale)

Pemakaian:
  python src/tarik_semua.py [--lihat]
"""
import argparse
import sys

from hm_common import jalankan_tugas
from tarik_bills import tarik_bills
from tarik_pricelist import tarik_pricelist
from tarik_stock import tarik_stock

TUGAS = {
    "bills": tarik_bills,
    "stock_wh": tarik_stock,
    "pricelist": tarik_pricelist,
}

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--lihat", action="store_true", help="tampilkan browser (uji coba)")
    sys.exit(jalankan_tugas(TUGAS, lihat=ap.parse_args().lihat))
