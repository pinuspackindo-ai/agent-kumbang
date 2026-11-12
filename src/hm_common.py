"""
Bagian bersama untuk semua agent tarik HashMicro:
konfigurasi .env, logging, helper elemen, login, dan sesi browser headless.
"""
import logging
import os
import re
import sys
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

BASE_URL = os.getenv("HM_BASE_URL", "https://pinuspackindo.hashmicro.co").rstrip("/")
USER = os.getenv("HM_USER", "")
PASS = os.getenv("HM_PASS", "")

NOW = datetime.now()
STAMP = NOW.strftime("%Y%m%d_%H%M%S")
RAW_DIR = ROOT / "data" / "raw" / NOW.strftime("%Y-%m-%d")      # file asli dari HashMicro (arsip)
HASIL_DIR = ROOT / "data" / "hasil" / NOW.strftime("%Y-%m-%d")  # file siap pakai
LOG_DIR = ROOT / "logs"
EXPORT_TIMEOUT_MS = 10 * 60 * 1000  # export ribuan baris bisa lama

log = logging.getLogger("hashmicro")


def setup_logging() -> None:
    if log.handlers:
        return
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    log.setLevel(logging.INFO)
    fh = logging.FileHandler(LOG_DIR / f"tarik_{NOW:%Y%m%d}.log", encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    log.addHandler(fh)
    log.addHandler(sh)


def langkah(nama: str) -> None:
    log.info("-> %s", nama)


def sensor(teks) -> str:
    """Hapus password/PIN dari pesan sebelum ditulis ke log.
    Pesan error Playwright mencantumkan nilai yang diketik (mis. fill("password"))."""
    teks = str(teks)
    for rahasia in (PASS, os.getenv("PORTAL_PIN", "")):
        if rahasia:
            teks = teks.replace(rahasia, "***")
    return teks


def terlihat(locator, timeout_ms: int = 30_000):
    """Kembalikan elemen pertama yang terlihat dari sebuah locator (tunggu sampai ada)."""
    batas = datetime.now().timestamp() + timeout_ms / 1000
    while datetime.now().timestamp() < batas:
        for i in range(locator.count()):
            el = locator.nth(i)
            if el.is_visible():
                return el
        locator.page.wait_for_timeout(300)
    raise RuntimeError(f"Elemen tidak ditemukan/terlihat: {locator}")


def angka(teks: str) -> int:
    m = re.search(r"([\d.,]+)", teks or "")
    return int(re.sub(r"[.,]", "", m.group(1))) if m else -1


def login(page) -> None:
    langkah("Buka halaman login")
    page.goto(f"{BASE_URL}/web/login", wait_until="domcontentloaded")
    # Halaman ini punya 2 form login (satu tersembunyi) -> pakai yang terlihat
    terlihat(page.locator("input[name='login']")).fill(USER)
    terlihat(page.locator("input[name='password']")).fill(PASS)
    langkah("Klik Log in")
    terlihat(page.locator("button[type='submit']")).click()
    try:
        page.wait_for_url(re.compile(r"/web(#|\?|$)"), timeout=60_000)
    except PWTimeout:
        if page.locator(".alert-danger").count():
            raise RuntimeError("Login ditolak: " + page.locator(".alert-danger").first.inner_text().strip())
        raise RuntimeError("Login tidak berhasil (halaman sistem tidak terbuka).")
    # Tunggu sistem selesai dimuat
    terlihat(page.locator("input.parent_menu_autocomplete, .o_main_navbar"), 90_000)


def buka_menu(page, menu_id: int, action_id: int) -> None:
    """Buka menu HashMicro langsung lewat URL (lebih stabil daripada klik dropdown)."""
    page.goto(f"{BASE_URL}/web#menu_id={menu_id}&action={action_id}")
    page.reload()


def simpan_download(page, klik, nama: str) -> Path:
    """Jalankan fungsi `klik` yang memicu download, lalu simpan ke data/raw/<tanggal>/."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    with page.expect_download(timeout=EXPORT_TIMEOUT_MS) as dl_info:
        klik()
    tujuan = RAW_DIR / f"{nama}_{STAMP}.xlsx"
    dl_info.value.save_as(tujuan)
    log.info("   File asli: %s", tujuan)
    return tujuan


def path_hasil(raw: Path) -> Path:
    """Lokasi file siap pakai untuk sebuah file asli (nama sama, folder data/hasil/<tgl>/)."""
    HASIL_DIR.mkdir(parents=True, exist_ok=True)
    return HASIL_DIR / raw.name


def screenshot_error(page, label: str) -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    shot = LOG_DIR / f"error_{label}_{datetime.now():%Y%m%d_%H%M%S}.png"
    try:
        page.screenshot(path=str(shot), full_page=True)
    except Exception:  # noqa: BLE001
        pass
    return shot


def buka_browser(p, lihat: bool = False):
    """Windows: pakai Microsoft Edge terpasang (Chromium bawaan Playwright diblokir Kaspersky).
    Linux/cloud (GitHub Actions): pakai Chromium bawaan Playwright.
    Bisa dipaksa lewat env HM_BROWSER=msedge|chromium."""
    pilihan = os.getenv("HM_BROWSER") or ("msedge" if sys.platform == "win32" else "chromium")
    channel = None if pilihan == "chromium" else pilihan
    return p.chromium.launch(channel=channel, headless=not lihat)


@contextmanager
def sesi_browser(lihat: bool = False):
    """Buka Edge (headless kecuali lihat=True), login, dan berikan `page` yang siap dipakai."""
    if not USER or not PASS:
        raise RuntimeError("HM_USER / HM_PASS belum diisi di file .env")
    with sync_playwright() as p:
        browser = buka_browser(p, lihat)
        ctx = browser.new_context(accept_downloads=True, viewport={"width": 1600, "height": 1000})
        page = ctx.new_page()
        try:
            yield page
        finally:
            # Tutup dengan aman; error saat menutup tidak boleh menggagalkan hasil
            for tutup in (page.close, ctx.close, browser.close):
                try:
                    tutup()
                except Exception:  # noqa: BLE001
                    pass


def jalankan_tugas(tugas: dict, lihat: bool = False, hasil: dict | None = None) -> int:
    """
    Login sekali, lalu jalankan setiap tugas {nama: fungsi(page)} berurutan.
    Satu tugas gagal tidak menghentikan tugas lain. Return 0 jika semua sukses.
    Jika `hasil` diberikan, file hasil tiap tugas yang sukses disimpan ke dict itu {nama: Path}.
    """
    setup_logging()
    hasil = {} if hasil is None else hasil
    gagal = []
    try:
        with sesi_browser(lihat) as page:
            for percobaan in range(1, 4):  # ulangi jika jaringan/server sesaat bermasalah
                try:
                    login(page)
                    break
                except Exception as e:  # noqa: BLE001
                    shot = screenshot_error(page, "login")
                    if "ditolak" in str(e) or percobaan == 3:
                        log.error("GAGAL login: %s (screenshot: %s)", sensor(e), shot)
                        return 1
                    log.warning("Login percobaan %d gagal (%s), ulangi 15 detik lagi",
                                percobaan, sensor(e).splitlines()[0])
                    page.wait_for_timeout(15_000)
            for nama, fungsi in tugas.items():
                log.info("===== %s =====", nama.upper())
                try:
                    hasil[nama] = fungsi(page)
                    log.info("%s: SELESAI", nama)
                except Exception as e:  # noqa: BLE001
                    gagal.append(nama)
                    log.error("%s: GAGAL - %s (screenshot: %s)", nama, sensor(e), screenshot_error(page, nama))
    except RuntimeError as e:
        log.error(sensor(e))
        return 2
    log.info("RINGKASAN: %d tugas, %d gagal %s", len(tugas), len(gagal), gagal or "")
    return 1 if gagal else 0
