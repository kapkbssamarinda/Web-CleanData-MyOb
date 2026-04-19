import streamlit as st
import pandas as pd
import io
import csv
import re
from datetime import datetime

st.set_page_config(page_title="GL Converter Pro - MYOB", layout="wide")
st.title("📊 GL Converter Pro — MYOB Edition")
st.caption("Mendukung ekstraksi file General Ledger dari MYOB AccountRight (hanya format .txt)")

# ─────────────────────────────────────────────
#  HELPER FUNCTIONS
# ─────────────────────────────────────────────

def clean_num(val) -> float:
    """
    Bersihkan nilai angka dari format MYOB.
    Contoh: 'Rp1,688,074.00' → 1688074.0
            'Rp2,129,926.00cr' → -2129926.0  (cr = credit / saldo negatif)
    """
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)

    s = str(val).strip()
    if s == '' or s.lower() == 'none':
        return 0.0

    # Deteksi suffix 'cr' = saldo kredit (bernilai negatif secara matematis)
    is_cr = s.lower().endswith('cr')

    # Buang semua karakter non-numerik kecuali titik dan minus
    s = re.sub(r'[Rp,"\s]', '', s)   # hapus Rp, koma, kutip, spasi
    s = re.sub(r'cr$', '', s, flags=re.IGNORECASE)

    # Format akuntansi (1500) → -1500
    if s.startswith('(') and s.endswith(')'):
        s = '-' + s[1:-1]

    try:
        result = float(s)
        return -result if is_cr else result
    except ValueError:
        return 0.0


def fmt_date_txt(raw: str) -> str:
    """
    TXT MYOB → DD/MM/YYYY.
    MYOB TXT menggunakan format DD/MM/YYYY.
    """
    raw = raw.strip()
    if re.match(r'^\d{2}/\d{2}/\d{4}$', raw):
        return raw                                  # sudah DD/MM/YYYY
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
    """
    Struktur baris MYOB TXT (CSV):
      Header laporan  : diabaikan
      Baris COA       : col[0]=ID COA (mis. '1-1101'), col[1]=Nama Akun
      Baris BB        : col[0]='Beginning Balance:', col[1]=jumlah
      Baris transaksi : col[0]=ID#, col[1]=Src, col[2]=Tanggal (DD/MM/YYYY),
                        col[3]=Memo, col[4]=Debit, col[5]=Kredit,
                        col[6]=Job, col[7]=Net Activity, col[8]=Ending Balance
    """
    reader = csv.reader(io.StringIO(content), delimiter=',')
    rows = list(reader)

    current_coa = ''
    current_account = ''
    data_bersih = []

    for row in rows:
        # Pad agar tidak index error
        row = [str(x).strip() for x in row] + [''] * 10
        c0, c1, c2 = row[0], row[1], row[2]

        # Skip baris kosong atau baris header tabel
        if c0 == '' or c0 == 'ID#':
            continue

        # ── Baris COA ──────────────────────────────
        # Format: '1-1101' atau '2-1000' dst.
        # Pastikan bukan transaksi (transaksi punya tanggal di c2)
        if re.match(r'^\d[-–]\d{3,5}', c0) and not re.match(r'^\d{2}/\d{2}/\d{4}', c2):
            current_coa = c0
            current_account = c1
            continue

        # ── Baris Beginning Balance ─────────────────
        if c0.startswith('Beginning Balance'):
            bb = clean_num(c1)
            data_bersih.append([
                '', current_coa, current_account, '',
                'Saldo Awal (Beginning Balance)',
                0.0, 0.0, bb
            ])
            continue

        # ── Baris Transaksi ─────────────────────────
        # Ciri khas: c2 adalah tanggal DD/MM/YYYY
        if re.match(r'^\d{2}/\d{2}/\d{4}$', c2):
            data_bersih.append([
                fmt_date_txt(c2),
                current_coa,
                current_account,
                c1,                # Src (GJ, CD, dll.)
                row[3],            # Memo
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

        # Format
        hdr_fmt   = wb.add_format({'bold': True, 'bg_color': '#1F4E79',
                                   'font_color': 'white', 'border': 1,
                                   'align': 'center', 'valign': 'vcenter'})
        money_fmt = wb.add_format({'num_format': '#,##0', 'align': 'right'})
        neg_fmt   = wb.add_format({'num_format': '#,##0', 'align': 'right',
                                   'font_color': '#C00000'})
        date_fmt  = wb.add_format({'align': 'center'})

        # Tulis ulang header dengan format
        for col_num, col_name in enumerate(df.columns):
            ws.write(0, col_num, col_name, hdr_fmt)

        # Lebar kolom
        ws.set_column('A:A', 13, date_fmt)   # Tanggal
        ws.set_column('B:B', 10)             # ID COA
        ws.set_column('C:C', 28)             # Nama Akun
        ws.set_column('D:D',  6)             # Src
        ws.set_column('E:E', 52)             # Memo
        ws.set_column('F:H', 20, money_fmt)  # Debit, Kredit, Ending Balance

        # Freeze header + autofilter
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

        # ── Baca & Parse ──────────────────────────
        status.text("📂 Membaca file...")
        progress.progress(20)

        status.text("🔍 Mengekstrak data dari TXT...")
        progress.progress(50)
        
        # Decode file .txt langsung
        content = uploaded.getvalue().decode('utf-8', errors='ignore')
        data = parse_txt(content)

        progress.progress(80)
        status.text("🏗️  Menyusun tabel final...")

        # ── Validasi ──────────────────────────────
        if not data:
            st.warning(
                "⚠️ Tidak ada data yang berhasil diekstrak. "
                "Pastikan file berasal dari ekspor General Ledger MYOB AccountRight."
            )
            st.stop()

        df = pd.DataFrame(data, columns=[
            "Tanggal", "ID COA", "Nama Akun", "Src",
            "Memo", "Debit", "Kredit", "Ending Balance"
        ])

        progress.progress(100)
        status.text("✅ Selesai!")
        status.empty()

        # ── Ringkasan ─────────────────────────────
        st.success(f"✅ Berhasil merapikan **{len(df):,} baris** dari **{uploaded.name}**")

        df_trx = df[df['Memo'] != 'Saldo Awal (Beginning Balance)']
        c1, c2, c3 = st.columns(3)
        c1.metric("Jumlah COA", df['ID COA'].nunique())
        c2.metric("Total Transaksi", f"{len(df_trx):,}")
        c3.metric("Total Baris (incl. Saldo Awal)", f"{len(df):,}")

        # ── Preview ───────────────────────────────
        st.write("**Preview 10 Baris Pertama:**")
        df_preview = df.head(10).copy()
        for col in ["Debit", "Kredit", "Ending Balance"]:
            df_preview[col] = df_preview[col].apply(
                lambda x: f"{x:,.0f}" if x != 0 else "-"
            )
        st.dataframe(df_preview, use_container_width=True)

        # ── Filter per COA ────────────────────────
        st.divider()
        st.subheader("🔍 Filter per Akun")
        coa_options = ['— Tampilkan Semua —'] + sorted(
            df['ID COA'].dropna().unique().tolist()
        )
        selected = st.selectbox("Pilih Akun (ID COA):", coa_options)

        if selected != '— Tampilkan Semua —':
            df_filtered = df[df['ID COA'] == selected].copy()
            df_show = df_filtered.copy()
            for col in ["Debit", "Kredit", "Ending Balance"]:
                df_show[col] = df_show[col].apply(
                    lambda x: f"{x:,.0f}" if x != 0 else "-"
                )
            st.write(f"Menampilkan **{len(df_filtered):,}** baris untuk akun **{selected}**")
            st.dataframe(df_show, use_container_width=True)

        # ── Download ──────────────────────────────
        st.divider()
        excel_data = build_excel(df)
        st.download_button(
            label="📥 Download Hasil (.xlsx)",
            data=excel_data,
            file_name="GL_MYOB_Cleaned.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    except Exception as e:
        import traceback
        st.error(f"❌ Terjadi kesalahan: {e}")
        with st.expander("Detail Error (untuk debugging)"):
            st.code(traceback.format_exc())