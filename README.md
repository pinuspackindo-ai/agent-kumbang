# Agent Kumbang - Database Fluktuasi

Agent yang berjalan di belakang layar (browser tersembunyi) untuk memperbarui
**Database Purchase** di portal PINUS Tools Purchase dari data HashMicro, tanpa API.

## Alur

```
TAHAP 1 — Tarik dari HashMicro (sekali login, user dari .env)
  1. Accounting > Bills          → Export template "Tools Purchase (Daily)"
                                   → baris lanjutan diisi data bill induknya
  2. Inventory > Stock per-Warehouse (Gudang Pinus Packindo) → Export All
                                   → ambil 3 kolom: Internal Reference | Name | Purchase Unit of Measure
  3. Point of Sale > Pricelist Items, filter Pricelist "New" → Export All

TAHAP 2 — Upload ke portal procurement.pinuspackindo.com (user Admin)
  Import Excel         ← Bills      (MENGGANTI seluruh Database Purchase)
  Import Purchase UOM  ← Stock      (perbarui/tambah per kode)
  Import Pricelist     ← Pricelist  (perbarui/tambah per kode)
```

## Menjalankan

| Cara | Keterangan |
|---|---|
| Dobel-klik **`Agent Kumbang - Database Fluktuasi.bat`** | Jalankan penuh (±5 menit) |
| `Agent Kumbang - Database Fluktuasi.bat --cek` | Tarik sungguhan, upload hanya dicek (tidak mengunggah) |
| `Agent Kumbang - Database Fluktuasi.bat --lihat` | Browser terlihat, untuk uji coba |

## Pengaman

- Jumlah data di setiap file dicocokkan dengan jumlah di HashMicro; kalau beda → tarikan dianggap gagal.
- Hanya file yang berhasil ditarik **pada jalan ini** yang diunggah (file lama tidak pernah diunggah ulang).
- Bills tidak diunggah jika barisnya < 80% dari record portal saat ini (mencegah data portal terhapus).
- Upload dibatalkan jika portal tidak terhubung ke Supabase atau menampilkan notifikasi error.
- Di menu Action HashMicro hanya item yang teksnya persis "Export" yang diklik.
- Password/PIN disensor (`***`) di semua pesan log.

## Folder

| Folder | Isi |
|---|---|
| `data\hasil\<tanggal>\` | File siap pakai (yang diunggah ke portal) |
| `data\raw\<tanggal>\` | File asli dari HashMicro (arsip) |
| `logs\` | Log harian `tarik_<tanggal>.log` + screenshot jika ada error |
| `src\` | Kode: `agent_kumbang.py` (alur utama), `tarik_*.py`, `upload_portal.py`, `hm_common.py` |

## Konfigurasi (`.env`, diisi sendiri, jangan dibagikan)

`HM_USER`, `HM_PASS` (HashMicro) · `PORTAL_USER`, `PORTAL_PIN` (portal).
Template: `.env.example`.

## Catatan teknis

- Browser: Microsoft Edge terpasang (Chromium bawaan Playwright diblokir Kaspersky).
- Instal ulang paket: `.venv\Scripts\python.exe -m pip install --cert certs\ca-bundle.pem -r requirements.txt`
  (sertifikat root Kaspersky perlu karena HTTPS di-scan antivirus).
- ID menu HashMicro yang dipakai (dibaca 12-11-2026): Bills 3376/353, Stock per-Warehouse 889/1239,
  Pricelist Items 1796/2523. Jika HashMicro di-update dan menu berubah, perbarui di `src\tarik_*.py`.
