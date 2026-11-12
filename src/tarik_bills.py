"""
Tarik data Bills dari HashMicro.

Alur (sesuai panduan user):
  Accounting > Bills -> centang semua -> Select all -> Action -> Export
  -> template "Tools Purchase (Daily)" -> Export -> simpan Excel

Pemakaian:
  python src/tarik_bills.py            # headless (tidak terlihat)
  python src/tarik_bills.py --lihat    # browser terlihat, untuk uji coba
"""
import argparse
import os
import re
import sys
from pathlib import Path

from hm_common import angka, buka_menu, jalankan_tugas, langkah, log, path_hasil, simpan_download, terlihat

TEMPLATE = os.getenv("HM_TEMPLATE_BILLS", "Tools Purchase (Daily)")

# ID menu HashMicro (dibaca dari sistem 12-11-2026)
MENU_BILLS = 3376
ACTION_BILLS = 353


def tarik_bills(page) -> Path:
    langkah("Buka Accounting > Bills")
    buka_menu(page, MENU_BILLS, ACTION_BILLS)
    page.locator(".o_list_view, .o_list_renderer, table.o_list_table").first.wait_for(timeout=60_000)

    langkah("Centang semua baris")
    page.locator("thead .o_list_record_selector input, thead th.o_list_record_selector").first.click()

    langkah("Klik Select all")
    tombol = terlihat(page.get_by_text(re.compile(r"Select all", re.I)))
    jumlah_erp = angka(tombol.inner_text())
    tombol.click()
    log.info("   Jumlah record di ERP: %s", jumlah_erp)

    langkah("Klik Action")
    terlihat(page.get_by_role("button", name=re.compile(r"Action"))).click()

    langkah("Klik Export (harus persis 'Export')")
    item = page.locator(".dropdown-menu.show").get_by_text("Export", exact=True)
    if item.count() != 1:
        raise RuntimeError("Item menu 'Export' tidak ditemukan persis satu. Berhenti demi keamanan.")
    item.click()

    modal = page.locator(".modal:visible").last
    modal.wait_for(timeout=30_000)

    langkah("Pilih format XLSX")
    xlsx = modal.locator("input[value='xlsx']")
    if xlsx.count():
        xlsx.first.check()

    langkah(f"Pilih template '{TEMPLATE}'")
    modal.locator("select.o_exported_lists_select, select").first.select_option(label=TEMPLATE)
    page.wait_for_timeout(1500)  # beri waktu daftar kolom template termuat

    langkah("Klik Export dan tunggu file terunduh")
    raw = simpan_download(page, lambda: modal.get_by_role("button", name="Export", exact=True).click(), "bills")
    return olah_file(raw, jumlah_erp)


def kosong(v) -> bool:
    return v is None or (isinstance(v, str) and v.strip() == "")


def olah_file(raw: Path, jumlah_erp: int) -> Path:
    """
    1. Validasi: jumlah bill di file == jumlah di ERP.
    2. Isi baris kosong: pada export Odoo, baris detail item ke-2 dst. kolom data bill-nya kosong.
       Kolom data bill (yang namanya tanpa '/') disalin utuh dari baris induk bill di atasnya.
       Kolom detail item ('Invoice lines/...') tidak diubah.
    """
    import openpyxl
    from openpyxl.cell import WriteOnlyCell
    from openpyxl.styles import Font

    wb = openpyxl.load_workbook(raw, read_only=True)
    rows = [list(r) for r in wb.active.iter_rows(values_only=True)]
    wb.close()
    header, data = rows[0], [r for r in rows[1:] if any(not kosong(v) for v in r)]

    # Kolom detail item = awalan sebelum '/' dipakai >= 2 kolom (mis. 'Invoice lines/...').
    # 'Invoice/Bill Date' tetap kolom data bill karena awalan 'Invoice' hanya dipakai sekali.
    awalan = [str(h).split("/", 1)[0] if h and "/" in str(h) else None for h in header]
    kolom_bill = [i for i, a in enumerate(awalan) if a is None or awalan.count(a) < 2]
    log.info("   Kolom data bill (diisi dari atas): %s", [header[i] for i in kolom_bill])

    induk = None
    jumlah_bill = 0
    diisi = 0
    for r in data:
        if any(not kosong(r[i]) for i in kolom_bill):
            induk = r  # baris pertama sebuah bill
            jumlah_bill += 1
        elif induk is None:
            raise RuntimeError("Baris pertama data tidak punya data bill, format file tidak dikenali")
        else:
            for i in kolom_bill:
                r[i] = induk[i]
            diisi += 1

    log.info("   Baris data: %d | Bill: %d | Baris lanjutan yang diisi: %d", len(data), jumlah_bill, diisi)
    if jumlah_erp > 0 and jumlah_bill != jumlah_erp:
        raise RuntimeError(f"Validasi GAGAL: bill di file ({jumlah_bill}) != jumlah di ERP ({jumlah_erp})")
    log.info("   Validasi jumlah bill: COCOK")

    out = openpyxl.Workbook(write_only=True)
    ws = out.create_sheet("Bills")
    judul = []
    for h in header:
        c = WriteOnlyCell(ws, value=h)
        c.font = Font(bold=True)
        judul.append(c)
    ws.append(judul)
    for r in data:
        ws.append(r)
    hasil = path_hasil(raw)
    out.save(hasil)
    log.info("   File siap pakai: %s", hasil)
    return hasil


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--lihat", action="store_true", help="tampilkan browser (uji coba)")
    sys.exit(jalankan_tugas({"bills": tarik_bills}, lihat=ap.parse_args().lihat))
