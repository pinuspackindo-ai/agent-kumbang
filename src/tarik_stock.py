"""
Tarik data Stock per-Warehouse dari HashMicro.

Alur (sesuai panduan user):
  Inventory > Stock per-Warehouse -> Warehouse = "Gudang Pinus Packindo"
  -> tunggu data muncul -> klik ikon awan (Export All) -> file langsung terunduh

Hasil:
  data/raw/<tgl>/stock_wh_<jam>.xlsx    -> file asli dari HashMicro (arsip)
  data/hasil/<tgl>/stock_wh_<jam>.xlsx  -> siap pakai, hanya 3 kolom:
                                           Internal Reference | Name | Purchase Unit of Measure
Pemakaian:
  python src/tarik_stock.py [--lihat]
"""
import argparse
import os
import sys
from pathlib import Path

from hm_common import angka, buka_menu, jalankan_tugas, langkah, log, path_hasil, simpan_download, terlihat

WAREHOUSE = os.getenv("HM_WAREHOUSE_STOCK", "Gudang Pinus Packindo")

# ID menu HashMicro (dibaca dari sistem 12-11-2026)
MENU_STOCK_WH = 889
ACTION_STOCK_WH = 1239

# Kolom output -> kemungkinan nama kolom di file export HashMicro (dicek berurutan)
KOLOM_OUTPUT = {
    "Internal Reference": ["Product Code", "Internal Reference", "Default Code"],
    "Name": ["Product", "Name", "Product Name"],
    "Purchase Unit of Measure": ["Purchase Unit of Measure", "Purchase UoM"],
}


def tarik_stock(page) -> Path:
    langkah("Buka Inventory > Stock per-Warehouse")
    buka_menu(page, MENU_STOCK_WH, ACTION_STOCK_WH)
    wh_input = terlihat(page.locator(".o_warehouse_widget input.o_record_input"), 90_000)
    page.wait_for_timeout(4000)  # beri waktu halaman selesai memasang fungsi filter

    baris = page.locator("table tbody tr.o_data_row").first
    for percobaan in range(1, 4):
        langkah(f"Pilih Warehouse '{WAREHOUSE}' (percobaan {percobaan})")
        wh_input.click()
        terlihat(page.locator("ul.o_warehouse_dropdown li").filter(has_text=WAREHOUSE)).click()
        if wh_input.input_value().strip() != WAREHOUSE:
            raise RuntimeError(f"Warehouse tidak terpilih (terisi: '{wh_input.input_value()}')")
        langkah("Tunggu data muncul")
        try:
            baris.wait_for(timeout=45_000)
            break
        except Exception:  # noqa: BLE001
            log.warning("   Data belum muncul, pilih ulang warehouse")
            page.wait_for_timeout(3000)
    else:
        raise RuntimeError("Data stock tidak muncul setelah 3 kali memilih warehouse")
    page.wait_for_timeout(2000)
    jumlah_erp = angka(page.locator(".o_pager_limit").first.inner_text())
    log.info("   Jumlah produk di ERP: %s", jumlah_erp)

    langkah("Klik ikon awan (Export All) dan tunggu file terunduh")
    tombol = terlihat(page.locator("button.o_list_export_xlsx"))
    raw = simpan_download(page, tombol.click, "stock_wh")

    return olah_file(raw, jumlah_erp)


def olah_file(raw: Path, jumlah_erp: int) -> Path:
    """Ambil 3 kolom yang dipakai, validasi, simpan sebagai file baru."""
    import openpyxl
    from openpyxl.styles import Font

    wb = openpyxl.load_workbook(raw, read_only=True)
    rows = list(wb.active.iter_rows(values_only=True))
    wb.close()
    header = [str(h).strip() if h is not None else "" for h in rows[0]]
    data = [r for r in rows[1:] if any(v not in (None, "") for v in r)]
    log.info("   Kolom asli: %s", header)

    idx = {}
    for keluar, calon in KOLOM_OUTPUT.items():
        lower = [h.lower() for h in header]
        cocok = next((lower.index(c.lower()) for c in calon if c.lower() in lower), None)
        if cocok is None:
            raise RuntimeError(f"Kolom untuk '{keluar}' tidak ditemukan di file export (dicari: {calon})")
        idx[keluar] = cocok
        log.info("   '%s' <- kolom '%s'", keluar, header[cocok])

    log.info("   Baris data: %d", len(data))
    if jumlah_erp > 0 and len(data) != jumlah_erp:
        raise RuntimeError(f"Validasi GAGAL: baris di file ({len(data)}) != jumlah di ERP ({jumlah_erp})")
    log.info("   Validasi jumlah baris: COCOK")
    kosong = sum(1 for r in data if r[idx["Internal Reference"]] in (None, ""))
    if kosong:
        log.warning("   %d produk tanpa Internal Reference", kosong)

    out = openpyxl.Workbook()
    ws = out.active
    ws.title = "Stock"
    ws.append(list(KOLOM_OUTPUT))
    for r in data:
        ws.append([r[i] for i in idx.values()])
    for col, lebar in zip("ABC", (22, 60, 28)):
        ws.column_dimensions[col].width = lebar
    for cell in ws[1]:
        cell.font = Font(bold=True)
    hasil = path_hasil(raw)
    out.save(hasil)
    log.info("   File siap pakai (3 kolom): %s", hasil)
    return hasil


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--lihat", action="store_true", help="tampilkan browser (uji coba)")
    sys.exit(jalankan_tugas({"stock_wh": tarik_stock}, lihat=ap.parse_args().lihat))
