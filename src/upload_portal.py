"""
Upload file hasil tarikan HashMicro ke portal PINUS Tools Purchase.

Memakai fungsi import portal itu sendiri (sama seperti klik tombol manual), jadi semua aturan
portal tetap berlaku (retur/bonus diabaikan, harga < Rp 1 diabaikan, hanya "Sales New (IDR)", dll).

  Import Excel         <- bills_<jam>.xlsx          (MENGGANTI seluruh Database Purchase)
  Import Purchase UOM  <- stock_wh_<jam>.xlsx       (upsert per kode, tidak menghapus)
  Import Pricelist     <- pricelist_new_<jam>.xlsx  (upsert per kode, tidak menghapus)

Pemakaian:
  python src/upload_portal.py --cek      # login & cek saja, TIDAK mengunggah
  python src/upload_portal.py            # unggah file terbaru di data/hasil/
  python src/upload_portal.py --lihat    # browser terlihat
"""
import argparse
import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from hm_common import (LOGIN_DITOLAK, ROOT, buka_browser, langkah, log, screenshot_error, sensor,
                       setup_logging, terlihat)

PORTAL_URL = os.getenv("PORTAL_URL", "https://procurement.pinuspackindo.com").rstrip("/")
PORTAL_USER = os.getenv("PORTAL_USER", "")
PORTAL_PIN = os.getenv("PORTAL_PIN", "")
IMPORT_TIMEOUT_S = 10 * 60

# (nama, awalan file di data/hasil, id input file di portal, teks toast sukses)
IMPORTS = [
    ("bills", "bills_", "fileInput", "records diimport"),
    ("purchase_uom", "stock_wh_", "uomFileInput", "kode Purchase UOM"),
    ("pricelist", "pricelist_new_", "pricelistFileInput", "kode Pricelist"),
]

# Pengaman: Import Excel MENGHAPUS semua data lama. Jangan unggah file bills yang barisnya
# kurang dari persentase ini dibanding jumlah record di portal sekarang (mencegah data terhapus
# oleh file yang tidak lengkap).
BATAS_MIN_BILLS = 0.80

# Rekam semua toast (notifikasi) portal, karena toast hilang sendiri setelah 4,5 detik.
JS_REKAM_TOAST = """() => {
  window.__toasts = [];
  const wrap = document.getElementById('toastWrap');
  new MutationObserver(ms => ms.forEach(m => m.addedNodes.forEach(n => {
    if (n.classList && n.classList.contains('toast'))
      window.__toasts.push({type: [...n.classList].find(c => c !== 'toast') || 'info', msg: n.innerText.trim()});
  }))).observe(wrap, {childList: true});
}"""


class PortalDitolak(RuntimeError):
    """User/PIN portal ditolak -> jangan diulang."""


def file_terbaru(awalan: str) -> Path:
    calon = sorted((ROOT / "data" / "hasil").glob(f"*/{awalan}*.xlsx"), key=lambda p: p.stat().st_mtime)
    calon = [p for p in calon if not (awalan == "stock_wh_" and "raw" in p.name)]
    if not calon:
        raise RuntimeError(f"Tidak ada file '{awalan}*.xlsx' di data/hasil/")
    return calon[-1]


def jumlah_baris(path: Path) -> int:
    import openpyxl

    wb = openpyxl.load_workbook(path, read_only=True)
    n = sum(1 for r in wb.active.iter_rows(min_row=2, values_only=True) if any(v not in (None, "") for v in r))
    wb.close()
    return n


def login_portal(page) -> None:
    langkah("Buka portal & login")
    page.goto(PORTAL_URL, wait_until="domcontentloaded", timeout=60_000)
    terlihat(page.locator("#loginUserSelect"), 60_000).select_option(label=PORTAL_USER)
    page.locator("#loginPin").fill(PORTAL_PIN)
    page.locator("button.login-btn").click()
    # Tunggu: masuk (tombol import muncul) ATAU ditolak (pesan #loginErr muncul)
    for _ in range(120):
        if page.locator("#loginErr").is_visible():
            raise PortalDitolak("Login portal ditolak: " + page.locator("#loginErr").inner_text().strip())
        if page.locator("#importBtn").is_visible():
            break
        page.wait_for_timeout(500)
    else:
        raise RuntimeError("Halaman portal tidak terbuka setelah login (60 detik)")

    langkah("Tunggu data portal selesai dimuat dari Supabase")
    page.wait_for_function(
        "() => !document.getElementById('loadingOverlay').classList.contains('show')", timeout=180_000)
    if not page.evaluate("() => canImportDB()"):
        raise RuntimeError(f"User '{PORTAL_USER}' tidak punya akses import di portal")
    chip = page.locator("#cloudChip").get_attribute("class") or ""
    if "chip-online" not in chip:
        # tanpa koneksi Supabase portal hanya menyimpan lokal di browser -> tidak ada gunanya
        raise RuntimeError(f"Portal tidak terhubung ke Supabase (status: {chip})")
    log.info("   Login OK, akses import OK, Supabase online")


def jumlah_record_portal(page) -> int:
    return page.evaluate("""async () => {
        const r = await sb.from('purchase_records').select('id', {count: 'exact', head: true});
        if (r.error) throw new Error(r.error.message);
        return r.count;
    }""")


def unggah(page, nama: str, path: Path, input_id: str, teks_sukses: str) -> str:
    langkah(f"Import {nama}: {path.name}")
    page.evaluate("() => { window.__toasts = []; }")
    page.locator(f"#{input_id}").set_input_files(str(path))
    batas = IMPORT_TIMEOUT_S * 2
    while batas > 0:
        toasts = page.evaluate("() => window.__toasts")
        error = [t["msg"] for t in toasts if t["type"] == "error"]
        if error:
            raise RuntimeError(f"Portal menolak import {nama}: {error}")
        sukses = [t["msg"] for t in toasts if t["type"] == "success" and teks_sukses in t["msg"]]
        if sukses:
            log.info("   Portal: %s", sukses[-1])
            return sukses[-1]
        page.wait_for_timeout(500)
        batas -= 1
    raise RuntimeError(f"Import {nama} tidak selesai dalam {IMPORT_TIMEOUT_S} detik")


def jalankan(cek_saja: bool = False, lihat: bool = False, files: dict | None = None) -> int:
    """
    files: {nama_import: Path}. Jika None, pakai file terbaru di data/hasil/ untuk ketiganya.
    Import yang tidak ada di `files` dilewati (mis. tarikannya gagal hari ini).
    """
    setup_logging()
    if not PORTAL_USER or not PORTAL_PIN:
        log.error("PORTAL_USER / PORTAL_PIN belum diisi di file .env")
        return 2

    if files is None:
        files = {nama: file_terbaru(awalan) for nama, awalan, _, _ in IMPORTS}
    imports = [imp for imp in IMPORTS if imp[0] in files]
    for nama, _, _, _ in IMPORTS:
        if nama not in files:
            log.warning("   %s DILEWATI: tidak ada file baru dari tarikan ini", nama)
    if not imports:
        log.error("Tidak ada file untuk diunggah")
        return 1
    for nama, _, _, _ in imports:
        log.info("   File %s: %s (%d baris)", nama, files[nama], jumlah_baris(files[nama]))

    gagal = []
    with sync_playwright() as pw:
        browser = buka_browser(pw, lihat)
        page = browser.new_page(viewport={"width": 1600, "height": 1000})
        # Popup confirm() di akhir import pricelist ("download daftar baris perlu dicek?") -> tolak, catat saja
        page.on("dialog", lambda d: (log.warning("   Dialog portal: %s", d.message.replace("\n", " ")), d.dismiss()))
        try:
            log.info("===== UPLOAD PORTAL =====")
            login_portal(page)
            page.evaluate(JS_REKAM_TOAST)
            sebelum = jumlah_record_portal(page)
            log.info("   Record Database Purchase di portal sekarang: %d", sebelum)

            if "bills" in files:
                baris_bills = jumlah_baris(files["bills"])
                if baris_bills < sebelum * BATAS_MIN_BILLS:
                    raise RuntimeError(
                        f"Pengaman: file bills hanya {baris_bills} baris, < {BATAS_MIN_BILLS:.0%} dari "
                        f"{sebelum} record di portal. Upload dibatalkan supaya data portal tidak terhapus.")

            if cek_saja:
                log.info("MODE CEK: tidak ada yang diunggah")
                return 0

            for nama, _, input_id, teks in imports:
                try:
                    unggah(page, nama, files[nama], input_id, teks)
                except Exception as e:  # noqa: BLE001
                    gagal.append(nama)
                    log.error("%s: GAGAL - %s (screenshot: %s)", nama, sensor(e), screenshot_error(page, f"upload_{nama}"))
                    if nama == "bills":
                        log.error("   Upload bills gagal: CEK portal, data Database Purchase mungkin tidak lengkap")

            sesudah = jumlah_record_portal(page)
            log.info("   Record Database Purchase di portal setelah upload: %d (sebelumnya %d)", sesudah, sebelum)
        except PortalDitolak as e:
            log.error("UPLOAD GAGAL (PIN DITOLAK): %s (screenshot: %s)", sensor(e), screenshot_error(page, "upload"))
            return LOGIN_DITOLAK
        except Exception as e:  # noqa: BLE001
            log.error("UPLOAD GAGAL: %s (screenshot: %s)", sensor(e), screenshot_error(page, "upload"))
            return 1
        finally:
            for tutup in (page.close, browser.close):
                try:
                    tutup()
                except Exception:  # noqa: BLE001
                    pass

    log.info("RINGKASAN UPLOAD: %d import, %d gagal %s", len(imports), len(gagal), gagal or "")
    return 1 if gagal or len(imports) < len(IMPORTS) else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--cek", action="store_true", help="login & cek saja, tidak mengunggah")
    ap.add_argument("--lihat", action="store_true", help="tampilkan browser (uji coba)")
    a = ap.parse_args()
    sys.exit(jalankan(cek_saja=a.cek, lihat=a.lihat))
