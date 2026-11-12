"""
Tarik data Pricelist Items dari HashMicro.

Alur (sesuai panduan user):
  Point of Sale > Pricelist Items -> filter kolom PRICELIST = "New"
  -> klik ikon awan (Export All) -> file langsung terunduh

Hasil:
  data/raw/<tgl>/pricelist_new_<jam>.xlsx    -> file asli (arsip)
  data/hasil/<tgl>/pricelist_new_<jam>.xlsx  -> siap pakai

Pemakaian:
  python src/tarik_pricelist.py [--lihat]
"""
import argparse
import os
import shutil
import sys
from pathlib import Path

from hm_common import angka, buka_menu, jalankan_tugas, langkah, log, path_hasil, simpan_download, terlihat

FILTER_PRICELIST = os.getenv("HM_FILTER_PRICELIST", "New")

# ID menu HashMicro (dibaca dari sistem 12-11-2026)
MENU_PRICELIST_ITEMS = 1796
ACTION_PRICELIST_ITEMS = 2523


def tarik_pricelist(page) -> Path:
    langkah("Buka Point of Sale > Pricelist Items")
    buka_menu(page, MENU_PRICELIST_ITEMS, ACTION_PRICELIST_ITEMS)
    page.locator("table tbody tr.o_data_row").first.wait_for(timeout=90_000)
    page.wait_for_timeout(2000)
    pager = page.locator(".o_pager_limit").first
    sebelum = angka(pager.inner_text())
    log.info("   Jumlah item sebelum filter: %s", sebelum)

    langkah(f"Filter kolom PRICELIST = '{FILTER_PRICELIST}'")
    # Kotak Search... pertama di header tabel = kolom PRICELIST
    kotak = terlihat(page.locator("thead input.custom-control-searchbar-advance"))
    kotak.fill(FILTER_PRICELIST)
    kotak.press("Enter")

    langkah("Tunggu data terfilter")
    batas = 60
    while batas > 0 and angka(pager.inner_text()) == sebelum:
        page.wait_for_timeout(1000)
        batas -= 1
    page.wait_for_timeout(2000)
    jumlah_erp = angka(pager.inner_text())
    if jumlah_erp == sebelum:
        raise RuntimeError(f"Filter '{FILTER_PRICELIST}' tidak mengubah jumlah data ({sebelum}), cek filter")
    log.info("   Jumlah item setelah filter: %s", jumlah_erp)

    langkah("Klik ikon awan (Export All) dan tunggu file terunduh")
    raw = simpan_download(page, terlihat(page.locator("button.o_list_export_xlsx")).click, "pricelist_new")
    cek_file(raw, jumlah_erp)
    hasil = path_hasil(raw)
    shutil.copy2(raw, hasil)  # belum ada olahan; salin apa adanya ke folder hasil
    log.info("   File siap pakai: %s", hasil)
    return hasil


def cek_file(path: Path, jumlah_erp: int) -> None:
    """Validasi: jumlah baris == ERP, dan semua baris memang pricelist yang mengandung filter."""
    import openpyxl

    wb = openpyxl.load_workbook(path, read_only=True)
    rows = list(wb.active.iter_rows(values_only=True))
    wb.close()
    header = [str(h).strip() if h is not None else "" for h in rows[0]]
    data = [r for r in rows[1:] if any(v not in (None, "") for v in r)]
    log.info("   Kolom: %s", header)
    log.info("   Baris data: %d", len(data))
    if jumlah_erp > 0 and len(data) != jumlah_erp:
        raise RuntimeError(f"Validasi GAGAL: baris di file ({len(data)}) != jumlah di ERP ({jumlah_erp})")

    kol = next((i for i, h in enumerate(header) if h.lower() == "pricelist"), None)
    if kol is not None:
        salah = [r[kol] for r in data if FILTER_PRICELIST.lower() not in str(r[kol] or "").lower()]
        if salah:
            raise RuntimeError(f"Validasi GAGAL: {len(salah)} baris bukan pricelist '{FILTER_PRICELIST}', contoh: {salah[:3]}")
        nama = sorted({str(r[kol]) for r in data})
        log.info("   Pricelist yang ikut: %s", nama)
    log.info("   Validasi: COCOK")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--lihat", action="store_true", help="tampilkan browser (uji coba)")
    sys.exit(jalankan_tugas({"pricelist": tarik_pricelist}, lihat=ap.parse_args().lihat))
