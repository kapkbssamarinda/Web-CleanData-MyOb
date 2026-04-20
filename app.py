import streamlit as st
import pandas as pd
import io
import csv
import re
from datetime import datetime

st.set_page_config(page_title="GL Converter Pro - MYOB", layout="wide")
# Judul diubah menjadi V3 agar kita tahu kodenya sudah terupdate
st.title("📊 GL Converter Pro — MYOB Edition (V3)")
st.caption("Mendukung ekstraksi file General Ledger dari MYOB AccountRight (hanya format .txt)")

# ─────────────────────────────────────────────
#  HELPER FUNCTIONS
# ─────────────────────────────────────────────

def clean_num(val) -> float:
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)

    s = str(val).strip()
    if s == '' or s.lower() == 'none':
        return 0.0

    is_cr = s.lower().endswith('cr')
    s = re.sub(r'[Rp,"\s]', '', s)
    s = re.sub(r'cr$', '', s, flags=re.IGNORECASE)

    if s.startswith('(') and s.endswith(')'):
        s = '-' + s[1:-1]

    try:
        result = float(s)
        return -result if is_cr else result
    except ValueError:
        return 0.0


def fmt_date_txt(raw: str) -> str:
    raw = raw.strip()
    if re.match(r'^\d{2}/\d{2}/\d{4}$', raw):
        return raw
    if re.match(r'^\d{4}-\d{2}-\d{2}', raw):
        try:
            return datetime.strptime(raw[:10], '%Y-%m-%d').strftime('%d/%m/%Y')
        except ValueError:
            pass
    return raw


# ─────────────────────────────────────────────
#  PARSER TXT
# ─────────────────────────────────────────────

def parse_txt(content: str) -> list:
    reader = csv.reader(io.StringIO(content), delimiter=',')
    rows = list(reader)

    current_coa = ''
    current_account = ''
    data_bersih = []

    for row in rows:
        row = [str(x).strip() for x in row] + [''] * 10
        c0, c1, c2 = row[0], row[1], row[2]

        if c0 == '' or c0 == 'ID#':
            continue

        # ── Baris COA
        if re.match(r'^\d[-–]\d{3,5}', c0) and not re.match(r'^\d{2}/\d{2}/\d{4}', c2):
            current_coa = c0
            current_account = c1
            continue

        # ── Baris Beginning Balance
        if c0.startswith('Beginning Balance'):
            bb = clean_num(c1)
            data_bersih.append([
                '-', '-', current_coa, current_account, # Kolom ID dan Tanggal dikosongkan untuk Saldo Awal
                'Saldo Awal (Beginning Balance)',
                0.0, 0.0, bb
            ])
            continue

        # ── Baris Transaksi
        if re.match(r'^\d{2}/\d{2}/\d{4}$', c2):
            data_bersih.append([
                c0,                # ID (Dipindah ke Kolom 1 ujung kiri)
                fmt_date_txt(c2),  # Tanggal (Kolom 2)
                current_coa,       # ID COA (Kolom 3)
                current_account,   # Nama Akun (Kolom 4)
                row[3],            # Memo (Kolom 5)
                clean_num(row[4]), # Debit
                clean_num(row[5]), # Kredit
                clean_num(row[8]), # Ending Balance
            ])

    return data_bersih


# ─────────────────────────────────────────────
#  EXPORT EXCEL
# ─────────────────────────────────────────────

def build_excel(df: pd.DataFrame) -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='GL_Clean')
        wb  = writer.book
        ws  = writer.sheets['GL_Clean']

        hdr_fmt   = wb.add_format({'bold': True, 'bg_color': '#1F4E79',
                                   'font_color': 'white', 'border': 1,
                                   'align': 'center', 'valign': 'vcenter'})
        money_fmt = wb.add_format({'num_format': '#,##0', 'align': 'right'})
        date_fmt  = wb.add_format({'align': 'center'})

        for col_num, col_name in enumerate(df.columns):
            ws.write(0, col_num, col_name, hdr_fmt)

        # Penyesuaian lebar kolom dengan urutan baru
        ws.set_column('A:A', 10, date_fmt)   # ID
        ws.set_column('B:B', 13, date_fmt)   # Tanggal
        ws.set_column('C:C', 10)             # ID COA
        ws.set_column('D:D', 28)             # Nama Akun
        ws.set_column('E:E', 52)             # Memo
        ws.set_column('F:H', 20, money_fmt)  # Debit, Kredit, Ending Balance

        ws.freeze_panes(1, 0)
        ws.autofilter(0, 0, len(df), len(df.columns) - 1)

    output.seek(0)
    return output.read()


# ─────────────────────────────────────────────
#  UI
# ─────────────────────────────────────────────

uploaded = st.file_uploader(
    "Upload file General Ledger MYOB (Hanya format .txt)",
    type=["txt"]
)

if uploaded:
    try:
        progress = st.progress(0)
        status   = st.empty()

        status.text("📂 Membaca file...")
        progress.progress(20)

        status.text("🔍 Mengekstrak data dari TXT...")
        progress.progress(50)
        
        content = uploaded.getvalue().decode('utf-8', errors='ignore')
        data = parse_txt(content)

        progress.progress(80)
        status.text("🏗️  Menyusun tabel final...")

        if not data:
            st.warning("⚠️ Tidak ada data yang berhasil diekstrak. Pastikan file benar.")
            st.stop()

        # Pembuatan Kolom Tabel yang Baru (Hapus Src, Tambah ID di paling awal)
        df = pd.DataFrame(data, columns=[
            "ID", "Tanggal", "ID COA", "Nama Akun", 
            "Memo", "Debit", "Kredit", "Ending Balance"
        ])

        progress.progress(100)
        status.text("✅ Selesai!")
        status.empty()

        st.success(f"✅ Berhasil merapikan **{len(df):,} baris** dari **{uploaded.name}**")

        df_trx = df[df['Memo'] != 'Saldo Awal (Beginning Balance)']
        c1, c2, c3 = st.columns(3)
        c1.metric("Jumlah COA", df['ID COA'].nunique())
        c2.metric("Total Transaksi", f"{len(df_trx):,}")
        c3.metric("Total Baris (incl. Saldo Awal)", f"{len(df):,}")

        # Preview Table UI Streamlit
        st.write("**Preview 10 Baris Pertama:**")
        df_preview = df.head(10).copy()
        for col in ["Debit", "Kredit", "Ending Balance"]:
            df_preview[col] = df_preview[col].apply(
                lambda x: f"{x:,.0f}" if isinstance(x, (int, float)) and x != 0 else ("-" if x == 0 else x)
            )
        st.dataframe(df_preview, use_container_width=True)

        st.divider()
        excel_data = build_excel(df)
        st.download_button(
            label="📥 Download Hasil (.xlsx)",
            data=excel_data,
            # Nama file diubah agar kamu tidak salah buka file Excel yang lama
            file_name="GL_MYOB_Cleaned_V3.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    except Exception as e:
        import traceback
        st.error(f"❌ Terjadi kesalahan: {e}")
        with st.expander("Detail Error (untuk debugging)"):
            st.code(traceback.format_exc())