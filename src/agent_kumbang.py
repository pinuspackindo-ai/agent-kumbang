"""
Agent Kumbang - Database Fluktuasi
==================================
Satu alur penuh, berjalan di belakang layar:

  TAHAP 1  Tarik dari HashMicro (sekali login)
           1. Bills (Accounting)               -> baris kosong diisi dari bill induk
           2. Stock per-Warehouse (Inventory)  -> 3 kolom
           3. Pricelist Items "New" (POS)
  TAHAP 2  Upload ke portal PINUS Tools Purchase
           Import Excel <- Bills | Import Purchase UOM <- Stock | Import Pricelist <- Pricelist

Tahap 2 hanya berjalan jika KETIGA tarikan berhasil & lolos validasi. Jika satu saja gagal,
upload dibatalkan seluruhnya (portal tidak diubah). File lama tidak pernah diunggah ulang.

Pemakaian:
  python src/agent_kumbang.py           # jalankan penuh
  python src/agent_kumbang.py --cek     # tarik sungguhan, upload hanya dicek (tidak mengunggah)
  python src/agent_kumbang.py --lihat   # browser terlihat
"""
import argparse
import sys
from datetime import datetime

import upload_portal
from hm_common import jalankan_tugas, log, setup_logging
from tarik_bills import tarik_bills
from tarik_pricelist import tarik_pricelist
from tarik_stock import tarik_stock

NAMA_AGENT = "Agent Kumbang - Database Fluktuasi"

# nama tugas tarik -> nama import di portal
TARIK = {
    "bills": (tarik_bills, "bills"),
    "stock_wh": (tarik_stock, "purchase_uom"),
    "pricelist": (tarik_pricelist, "pricelist"),
}


def main() -> int:
    ap = argparse.ArgumentParser(description=NAMA_AGENT)
    ap.add_argument("--cek", action="store_true", help="tarik sungguhan, upload hanya dicek")
    ap.add_argument("--lihat", action="store_true", help="tampilkan browser (uji coba)")
    a = ap.parse_args()

    setup_logging()
    mulai = datetime.now()
    log.info("#" * 60)
    log.info("# %s  (mulai %s)", NAMA_AGENT, f"{mulai:%Y-%m-%d %H:%M:%S}")
    log.info("#" * 60)

    log.info(">>> TAHAP 1: TARIK DATA DARI HASHMICRO")
    hasil_tarik = {}
    kode_tarik = jalankan_tugas({n: f for n, (f, _) in TARIK.items()}, lihat=a.lihat, hasil=hasil_tarik)
    files = {TARIK[n][1]: p for n, p in hasil_tarik.items()}

    log.info(">>> TAHAP 2: UPLOAD KE PORTAL")
    gagal_tarik = [n for n in TARIK if n not in hasil_tarik]
    if kode_tarik != 0 or gagal_tarik:
        # Aturan: data harus LENGKAP (ketiganya) baru boleh diunggah. Satu gagal -> semua batal.
        log.error("UPLOAD DIBATALKAN: tarikan belum lengkap, gagal: %s. Portal tidak diubah sama sekali.",
                  gagal_tarik or "login/lainnya")
        kode_upload = 1
    else:
        kode_upload = upload_portal.jalankan(cek_saja=a.cek, lihat=a.lihat, files=files)

    durasi = (datetime.now() - mulai).total_seconds()
    status = "SUKSES" if kode_tarik == 0 and kode_upload == 0 else "ADA YANG GAGAL (cek log)"
    log.info("#" * 60)
    log.info("# %s: %s  | durasi %.0f detik%s", NAMA_AGENT, status, durasi, " | MODE CEK" if a.cek else "")
    log.info("#" * 60)
    return 0 if status == "SUKSES" else 1


if __name__ == "__main__":
    sys.exit(main())
