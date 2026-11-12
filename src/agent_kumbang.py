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

Jika gagal, SELURUH alur diulang tiap 3 menit sampai sukses, berhenti di jam batas (19:00).
Kecuali username/password/PIN DITOLAK: langsung berhenti (mengulang bisa mengunci akun).

Pemakaian:
  python src/agent_kumbang.py           # jalankan penuh (dengan pengulangan)
  python src/agent_kumbang.py --sekali  # tanpa pengulangan
  python src/agent_kumbang.py --cek     # tarik sungguhan, upload hanya dicek (tidak mengunggah)
  python src/agent_kumbang.py --lihat   # browser terlihat
"""
import argparse
import os
import sys
import time
from datetime import datetime

import upload_portal
from hm_common import LOGIN_DITOLAK, jalankan_tugas, log, sensor, setup_logging
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


# Pengulangan: jika gagal, ulangi seluruh alur sampai sukses, tapi berhenti di jam batas
# (default 19:00) supaya masalah permanen (mis. password diganti) tidak menghabiskan
# jatah menit GitHub Actions. Ubah lewat env AGENT_BATAS_JAM / AGENT_JEDA_MENIT.
BATAS_JAM = os.getenv("AGENT_BATAS_JAM", "19:00")
JEDA_MENIT = float(os.getenv("AGENT_JEDA_MENIT", "3"))
PERKIRAAN_SATU_PUTARAN_MENIT = 8  # jangan mulai putaran baru jika tidak cukup waktu sebelum batas


SUKSES, GAGAL, DITOLAK = "sukses", "gagal", "ditolak"


def satu_putaran(cek: bool, lihat: bool) -> str:
    """Satu kali alur penuh (tarik 3 data -> upload). Return SUKSES / GAGAL / DITOLAK."""
    log.info(">>> TAHAP 1: TARIK DATA DARI HASHMICRO")
    hasil_tarik = {}
    kode_tarik = jalankan_tugas({n: f for n, (f, _) in TARIK.items()}, lihat=lihat, hasil=hasil_tarik)
    files = {TARIK[n][1]: p for n, p in hasil_tarik.items()}
    if kode_tarik == LOGIN_DITOLAK:
        return DITOLAK

    log.info(">>> TAHAP 2: UPLOAD KE PORTAL")
    gagal_tarik = [n for n in TARIK if n not in hasil_tarik]
    if kode_tarik != 0 or gagal_tarik:
        # Aturan: data harus LENGKAP (ketiganya) baru boleh diunggah. Satu gagal -> semua batal.
        log.error("UPLOAD DIBATALKAN: tarikan belum lengkap, gagal: %s. Portal tidak diubah sama sekali.",
                  gagal_tarik or "login/lainnya")
        kode_upload = 1
    else:
        kode_upload = upload_portal.jalankan(cek_saja=cek, lihat=lihat, files=files)
    if kode_upload == LOGIN_DITOLAK:
        return DITOLAK
    return SUKSES if kode_tarik == 0 and kode_upload == 0 else GAGAL


def main() -> int:
    ap = argparse.ArgumentParser(description=NAMA_AGENT)
    ap.add_argument("--cek", action="store_true", help="tarik sungguhan, upload hanya dicek")
    ap.add_argument("--lihat", action="store_true", help="tampilkan browser (uji coba)")
    ap.add_argument("--sekali", action="store_true", help="jangan ulangi jika gagal")
    a = ap.parse_args()

    setup_logging()
    mulai = datetime.now()
    jam, menit = (int(x) for x in BATAS_JAM.split(":"))
    batas = mulai.replace(hour=jam, minute=menit, second=0, microsecond=0)
    log.info("#" * 60)
    log.info("# %s  (mulai %s)", NAMA_AGENT, f"{mulai:%Y-%m-%d %H:%M:%S}")
    if not a.sekali:
        log.info("# Jika gagal: diulang tiap %.0f menit sampai sukses, batas jam %s", JEDA_MENIT, BATAS_JAM)
    log.info("#" * 60)

    putaran = 0
    while True:
        putaran += 1
        log.info("=" * 60)
        log.info("PUTARAN %d  (%s)", putaran, f"{datetime.now():%H:%M:%S}")
        log.info("=" * 60)
        try:
            hasil = satu_putaran(a.cek, a.lihat)
        except Exception as e:  # noqa: BLE001  (error tak terduga pun diulang)
            log.error("Putaran %d error tak terduga: %s", putaran, sensor(e))
            hasil = GAGAL
        if hasil == DITOLAK:
            log.error("USERNAME/PASSWORD/PIN DITOLAK: TIDAK diulang (bisa mengunci akun). "
                      "Perbarui secret/.env lalu jalankan lagi.")
            break
        if hasil == SUKSES or a.sekali:
            break
        sisa = (batas - datetime.now()).total_seconds() / 60
        if sisa < JEDA_MENIT + PERKIRAAN_SATU_PUTARAN_MENIT:
            log.error("Putaran %d GAGAL dan sudah mendekati batas jam %s, BERHENTI MENGULANG.", putaran, BATAS_JAM)
            break
        log.warning("Putaran %d GAGAL, diulang %.0f menit lagi (sisa waktu %.0f menit sebelum %s)",
                    putaran, JEDA_MENIT, sisa, BATAS_JAM)
        time.sleep(JEDA_MENIT * 60)

    durasi = (datetime.now() - mulai).total_seconds()
    sukses = hasil == SUKSES
    status = {SUKSES: "SUKSES", GAGAL: "GAGAL", DITOLAK: "GAGAL - PASSWORD/PIN DITOLAK"}[hasil]
    log.info("#" * 60)
    log.info("# %s: %s  | %d putaran | durasi %.0f detik%s", NAMA_AGENT, status, putaran, durasi,
             " | MODE CEK" if a.cek else "")
    log.info("#" * 60)
    return 0 if sukses else 1


if __name__ == "__main__":
    sys.exit(main())
