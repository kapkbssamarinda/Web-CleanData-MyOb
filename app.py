import streamlit as st
import pandas as pd
import csv
import io
import time

# ─────────────────────────────────────────
# 1. FUNGSI PEMBERSIHAN NOMINAL → return int
# ─────────────────────────────────────────
def clean_currency(val):
    if not val or (isinstance(val, float) and pd.isna(val)) or str(val).strip() == "":
        return None
    val = str(val).replace('Rp', '').replace('"', '').strip()
    val = val.replace(',', '')
    if val.endswith('.00'):
        val = val[:-3]
    if val.endswith('cr'):
        val = val.replace('cr', '').strip()
    try:
        num = int(float(val))
        return None if num == 0 else num
    except ValueError:
        return None

# ─────────────────────────────────────────
# 2. FUNGSI PEMBERSIHAN TANGGAL
# ─────────────────────────────────────────
def clean_date(val):
    if not val:
        return ""
    return str(val).split(" ")[0].strip()

# ─────────────────────────────────────────
# 3. FUNGSI UTAMA PROSES DATA
# ─────────────────────────────────────────
def process_gl_data(data_rows):
    parsed_data = []
    current_coa = ""
    current_account = ""
    start_reading = False

    idx_id, idx_date, idx_memo, idx_debit, idx_credit, idx_eb = 0, 2, 3, 4, 5, 8

    total_rows = len(data_rows)
    progress_bar = st.progress(0, text="Memulai proses cleaning...")

    for i, row in enumerate(data_rows):
        percent_complete = (i + 1) / total_rows
        progress_bar.progress(percent_complete, text=f"⚙️  Cleaning baris {i+1:,} dari {total_rows:,}...")

        clean_row = [str(cell).strip() for cell in row]

        if all(cell == "" for cell in clean_row):
            continue

        # Deteksi Header
        if "ID#" in clean_row and "Date" in clean_row:
            idx_id    = clean_row.index("ID#")
            idx_date  = clean_row.index("Date")
            idx_memo  = clean_row.index("Memo")
            idx_debit = clean_row.index("Debit")
            idx_credit= clean_row.index("Credit")
            for i_col, col in enumerate(clean_row):
                if "Ending Balance" in col:
                    idx_eb = i_col
                    break
            start_reading = True
            continue

        if not start_reading:
            continue

        # Deteksi COA
        coa_idx = -1
        for i_cell, cell in enumerate(clean_row):
            if "-" in cell and cell[0].isdigit() and len(cell) >= 5:
                coa_idx = i_cell
                break

        if coa_idx != -1 and (len(clean_row) <= idx_date or clean_row[idx_date] == ""):
            current_coa = clean_row[coa_idx]
            current_account = ""
            for cell in clean_row[coa_idx+1:]:
                if cell != "":
                    current_account = cell
                    break
            continue

        # Deteksi Saldo Awal
        bb_idx = -1
        for i_cell, cell in enumerate(clean_row):
            if "Beginning Balance" in cell:
                bb_idx = i_cell
                break

        if bb_idx != -1:
            balance = ""
            for cell in clean_row[bb_idx+1:]:
                if cell != "" and cell != ":":
                    balance = cell
                    break
            if not balance and len(clean_row) > idx_eb:
                balance = clean_row[idx_eb]
            parsed_data.append({
                "ID": "-", "Tanggal": "-",
                "COA": current_coa, "Nama Akun": current_account,
                "Memo": "Beginning Balance (Saldo Awal)",
                "Debit": None, "Kredit": None,
                "Ending Balance": clean_currency(balance)
            })
            continue

        # Deteksi Baris Transaksi
        if len(clean_row) > idx_id and clean_row[idx_id].isdigit():
            _id     = clean_row[idx_id]
            _date   = clean_row[idx_date]  if len(clean_row) > idx_date   else ""
            _memo   = clean_row[idx_memo]  if len(clean_row) > idx_memo   else ""
            _debit  = clean_row[idx_debit] if len(clean_row) > idx_debit  else ""
            _credit = clean_row[idx_credit]if len(clean_row) > idx_credit else ""
            _eb     = clean_row[idx_eb]    if len(clean_row) > idx_eb     else ""
            if not _eb and len(clean_row) > idx_eb + 1:
                _eb = clean_row[idx_eb + 1]

            parsed_data.append({
                "ID": _id, "Tanggal": clean_date(_date),
                "COA": current_coa, "Nama Akun": current_account,
                "Memo": _memo,
                "Debit": clean_currency(_debit),
                "Kredit": clean_currency(_credit),
                "Ending Balance": clean_currency(_eb)
            })

    progress_bar.empty()
    return pd.DataFrame(parsed_data)

# ─────────────────────────────────────────
# 4. EXPORT KE EXCEL (angka asli, bukan string)
# ─────────────────────────────────────────
def export_to_excel(df, original_filename):
    output = io.BytesIO()
    numeric_cols = ['Debit', 'Kredit', 'Ending Balance']

    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='GL_Detail')
        workbook  = writer.book
        worksheet = writer.sheets['GL_Detail']

        # ── Format Styles ──
        header_fmt = workbook.add_format({
            'bold': True, 'font_color': '#FFFFFF',
            'bg_color': '#1B3A6B', 'border': 1,
            'align': 'center', 'valign': 'vcenter',
            'font_size': 11, 'font_name': 'Calibri'
        })
        num_fmt = workbook.add_format({
            'num_format': '#,##0',
            'align': 'right', 'font_name': 'Calibri',
            'font_size': 10
        })
        dash_fmt = workbook.add_format({
            'align': 'center', 'font_color': '#AAAAAA',
            'font_name': 'Calibri', 'font_size': 10
        })
        text_fmt = workbook.add_format({
            'font_name': 'Calibri', 'font_size': 10
        })
        saldo_awal_fmt = workbook.add_format({
            'italic': True, 'font_color': '#555555',
            'bg_color': '#F5F5F5', 'font_name': 'Calibri',
            'font_size': 10
        })

        # ── Tulis Ulang Header dengan Style ──
        for col_idx, col_name in enumerate(df.columns):
            worksheet.write(0, col_idx, col_name, header_fmt)
            worksheet.set_row(0, 22)

        # ── Tulis Data Row by Row ──
        for row_idx, row in df.iterrows():
            excel_row = row_idx + 1
            is_saldo_awal = str(row.get('Memo', '')).startswith('Beginning Balance')

            for col_idx, col_name in enumerate(df.columns):
                val = row[col_name]

                if col_name in numeric_cols:
                    if val is None or (isinstance(val, float) and pd.isna(val)):
                        worksheet.write(excel_row, col_idx, '-', dash_fmt)
                    else:
                        try:
                            worksheet.write_number(excel_row, col_idx, int(val), num_fmt)
                        except (ValueError, TypeError):
                            worksheet.write(excel_row, col_idx, '-', dash_fmt)
                else:
                    fmt = saldo_awal_fmt if is_saldo_awal else text_fmt
                    worksheet.write(excel_row, col_idx, str(val) if val is not None else '', fmt)

        # ── Lebar Kolom Otomatis ──
        col_widths = {
            'ID': 8, 'Tanggal': 14, 'COA': 14,
            'Nama Akun': 35, 'Memo': 45,
            'Debit': 18, 'Kredit': 18, 'Ending Balance': 20
        }
        for col_idx, col_name in enumerate(df.columns):
            worksheet.set_column(col_idx, col_idx, col_widths.get(col_name, 15))

        # ── Freeze Header Row ──
        worksheet.freeze_panes(1, 0)

        # ── Auto Filter ──
        worksheet.autofilter(0, 0, len(df), len(df.columns) - 1)

    return output.getvalue()

# ═══════════════════════════════════════════════════════
#                    UI STREAMLIT
# ═══════════════════════════════════════════════════════

st.set_page_config(
    page_title="GL Converter Pro — MYOB",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ── Custom CSS ──
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');

html, body, [class*="css"] {
    font-family: 'Plus Jakarta Sans', sans-serif;
}

/* ── Background ── */
.stApp {
    background: linear-gradient(135deg, #0D1B2A 0%, #1B2E45 50%, #0D1B2A 100%);
    min-height: 100vh;
}

/* ── Hero Banner ── */
.hero-banner {
    background: linear-gradient(120deg, #1B3A6B 0%, #0D2B52 60%, #0A1F3D 100%);
    border: 1px solid rgba(99, 179, 237, 0.25);
    border-radius: 20px;
    padding: 2.5rem 3rem;
    margin-bottom: 2rem;
    position: relative;
    overflow: hidden;
    box-shadow: 0 8px 32px rgba(0,0,0,0.4);
}
.hero-banner::before {
    content: '';
    position: absolute;
    top: -60px; right: -60px;
    width: 220px; height: 220px;
    background: radial-gradient(circle, rgba(99,179,237,0.18) 0%, transparent 70%);
    border-radius: 50%;
}
.hero-banner::after {
    content: '';
    position: absolute;
    bottom: -40px; left: 20%;
    width: 150px; height: 150px;
    background: radial-gradient(circle, rgba(246,173,85,0.12) 0%, transparent 70%);
    border-radius: 50%;
}
.hero-title {
    font-size: 2.1rem;
    font-weight: 800;
    color: #FFFFFF;
    letter-spacing: -0.5px;
    margin: 0 0 0.4rem 0;
    line-height: 1.2;
}
.hero-title span {
    background: linear-gradient(90deg, #63B3ED, #F6AD55);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}
.hero-subtitle {
    color: rgba(255,255,255,0.60);
    font-size: 0.95rem;
    font-weight: 400;
    margin: 0;
}
.hero-badge {
    display: inline-block;
    background: rgba(99,179,237,0.15);
    border: 1px solid rgba(99,179,237,0.35);
    color: #63B3ED;
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    padding: 4px 12px;
    border-radius: 20px;
    margin-bottom: 1rem;
}

/* ── Upload Zone ── */
.upload-card {
    background: rgba(255,255,255,0.04);
    border: 2px dashed rgba(99,179,237,0.35);
    border-radius: 16px;
    padding: 2rem;
    text-align: center;
    transition: border-color 0.3s;
}

/* ── Metric Cards ── */
.metric-row {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 1rem;
    margin: 1.5rem 0;
}
.metric-card {
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,255,255,0.10);
    border-radius: 14px;
    padding: 1.2rem 1.5rem;
    position: relative;
    overflow: hidden;
    transition: transform 0.2s, border-color 0.2s;
}
.metric-card:hover {
    transform: translateY(-2px);
    border-color: rgba(99,179,237,0.4);
}
.metric-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 3px;
}
.metric-card.blue::before  { background: linear-gradient(90deg, #63B3ED, #4299E1); }
.metric-card.green::before { background: linear-gradient(90deg, #68D391, #48BB78); }
.metric-card.amber::before { background: linear-gradient(90deg, #F6AD55, #ED8936); }

.metric-label {
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 1.2px;
    text-transform: uppercase;
    color: rgba(255,255,255,0.45);
    margin-bottom: 0.5rem;
}
.metric-value {
    font-size: 1.75rem;
    font-weight: 800;
    color: #FFFFFF;
    font-family: 'JetBrains Mono', monospace;
    line-height: 1;
}
.metric-icon {
    position: absolute;
    top: 1.2rem; right: 1.2rem;
    font-size: 1.6rem;
    opacity: 0.25;
}

/* ── Section Label ── */
.section-label {
    font-size: 0.75rem;
    font-weight: 700;
    letter-spacing: 2px;
    text-transform: uppercase;
    color: #63B3ED;
    margin: 2rem 0 0.6rem 0;
    display: flex;
    align-items: center;
    gap: 8px;
}
.section-label::after {
    content: '';
    flex: 1;
    height: 1px;
    background: rgba(99,179,237,0.2);
}

/* ── Info Box ── */
.info-box {
    background: rgba(99,179,237,0.08);
    border: 1px solid rgba(99,179,237,0.25);
    border-left: 4px solid #63B3ED;
    border-radius: 10px;
    padding: 1rem 1.2rem;
    color: rgba(255,255,255,0.75);
    font-size: 0.875rem;
    margin-bottom: 1.5rem;
}
.info-box strong { color: #63B3ED; }

/* ── Success Box ── */
.success-box {
    background: rgba(72,187,120,0.10);
    border: 1px solid rgba(72,187,120,0.30);
    border-left: 4px solid #68D391;
    border-radius: 10px;
    padding: 1rem 1.2rem;
    color: rgba(255,255,255,0.80);
    font-size: 0.875rem;
    margin: 1rem 0;
}

/* ── Download Button ── */
.stDownloadButton > button {
    background: linear-gradient(135deg, #2B6CB0, #1A4A8A) !important;
    border: 1px solid rgba(99,179,237,0.4) !important;
    color: #FFFFFF !important;
    font-family: 'Plus Jakarta Sans', sans-serif !important;
    font-weight: 700 !important;
    font-size: 1rem !important;
    padding: 0.8rem 2.5rem !important;
    border-radius: 12px !important;
    width: 100% !important;
    letter-spacing: 0.3px !important;
    transition: all 0.2s !important;
    box-shadow: 0 4px 20px rgba(43,108,176,0.4) !important;
}
.stDownloadButton > button:hover {
    background: linear-gradient(135deg, #3182CE, #2B6CB0) !important;
    box-shadow: 0 6px 28px rgba(49,130,206,0.5) !important;
    transform: translateY(-1px) !important;
}

/* ── File Uploader ── */
[data-testid="stFileUploader"] {
    background: rgba(255,255,255,0.03);
    border-radius: 14px;
    padding: 0.5rem;
}

/* ── Dataframe ── */
[data-testid="stDataFrame"] {
    border-radius: 12px;
    overflow: hidden;
    border: 1px solid rgba(255,255,255,0.08);
}

/* ── Progress bar ── */
.stProgress > div > div > div {
    background: linear-gradient(90deg, #63B3ED, #F6AD55) !important;
    border-radius: 8px;
}

/* ── Status ── */
[data-testid="stStatusWidget"] {
    border-radius: 12px;
    background: rgba(255,255,255,0.04) !important;
    border: 1px solid rgba(255,255,255,0.10) !important;
}

/* ── Divider ── */
hr { border-color: rgba(255,255,255,0.08) !important; }

/* ── Steps indicator ── */
.steps-row {
    display: flex;
    align-items: center;
    gap: 0;
    margin: 1.5rem 0;
}
.step-item {
    display: flex;
    align-items: center;
    gap: 8px;
    flex: 1;
}
.step-circle {
    width: 32px; height: 32px;
    border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 0.8rem;
    font-weight: 700;
    flex-shrink: 0;
}
.step-circle.active {
    background: linear-gradient(135deg, #63B3ED, #4299E1);
    color: #fff;
    box-shadow: 0 0 12px rgba(99,179,237,0.5);
}
.step-circle.done {
    background: rgba(72,187,120,0.2);
    color: #68D391;
    border: 1.5px solid #68D391;
}
.step-circle.pending {
    background: rgba(255,255,255,0.06);
    color: rgba(255,255,255,0.3);
    border: 1.5px solid rgba(255,255,255,0.12);
}
.step-label {
    font-size: 0.78rem;
    font-weight: 600;
    color: rgba(255,255,255,0.55);
}
.step-label.active { color: #63B3ED; }
.step-label.done   { color: #68D391; }
.step-divider {
    width: 24px;
    height: 1px;
    background: rgba(255,255,255,0.12);
    margin: 0 4px;
    flex-shrink: 0;
}
</style>
""", unsafe_allow_html=True)


# ── HERO BANNER ──
st.markdown("""
<div class="hero-banner">
    <div class="hero-badge">✦ Audit Tools — KAP Suite</div>
    <h1 class="hero-title">GL Converter <span>Pro</span></h1>
    <p class="hero-subtitle">Ekstrak & bersihkan data Buku Besar dari MYOB ke Excel — cepat, rapi, siap audit.</p>
</div>
""", unsafe_allow_html=True)


# ── STEPS ──
st.markdown("""
<div class="steps-row">
    <div class="step-item">
        <div class="step-circle active">1</div>
        <span class="step-label active">Upload File</span>
    </div>
    <div class="step-divider"></div>
    <div class="step-item">
        <div class="step-circle pending">2</div>
        <span class="step-label">Cleaning Data</span>
    </div>
    <div class="step-divider"></div>
    <div class="step-item">
        <div class="step-circle pending">3</div>
        <span class="step-label">Preview</span>
    </div>
    <div class="step-divider"></div>
    <div class="step-item">
        <div class="step-circle pending">4</div>
        <span class="step-label">Download Excel</span>
    </div>
</div>
""", unsafe_allow_html=True)


# ── INFO BOX ──
st.markdown("""
<div class="info-box">
    📌 <strong>Petunjuk:</strong> Upload file <code>.txt</code> hasil ekspor General Ledger dari MYOB.
    Output Excel akan berisi angka murni (bukan teks) sehingga bebas dari warning &nbsp;<em>"Number Stored as Text"</em>.
</div>
""", unsafe_allow_html=True)


# ── UPLOAD ──
st.markdown('<div class="section-label">① Upload File GL</div>', unsafe_allow_html=True)
uploaded_file = st.file_uploader(
    "Pilih file General Ledger (.txt) dari MYOB",
    type=['txt'],
    help="File harus berformat .txt hasil ekspor langsung dari MYOB"
)


# ══════════════════════════════════════
# PROSES SETELAH FILE DIUPLOAD
# ══════════════════════════════════════
if uploaded_file is not None:

    # ── TAHAP 1: IMPORT ──
    with st.status("📂  Mengimport file...", expanded=True) as status:
        st.write("Membaca isi file ke memori...")
        file_content = uploaded_file.getvalue().decode("utf-8", errors="replace")
        reader = csv.reader(file_content.splitlines())
        data_rows = list(reader)
        time.sleep(0.4)
        status.update(label=f"✅  Import selesai — {len(data_rows):,} baris terdeteksi", state="complete", expanded=False)

    # ── TAHAP 2: CLEANING ──
    st.markdown('<div class="section-label">② Cleaning Data</div>', unsafe_allow_html=True)
    df = process_gl_data(data_rows)

    if not df.empty:

        # ── METRIC CARDS ──
        total_transaksi = len(df[df['ID'] != '-'])
        total_coa       = df['COA'].nunique()
        total_rows_all  = len(df)

        st.markdown(f"""
        <div class="metric-row">
            <div class="metric-card blue">
                <div class="metric-icon">📋</div>
                <div class="metric-label">Total Baris</div>
                <div class="metric-value">{total_rows_all:,}</div>
            </div>
            <div class="metric-card green">
                <div class="metric-icon">💳</div>
                <div class="metric-label">Transaksi</div>
                <div class="metric-value">{total_transaksi:,}</div>
            </div>
            <div class="metric-card amber">
                <div class="metric-icon">🗂️</div>
                <div class="metric-label">Jumlah COA</div>
                <div class="metric-value">{total_coa:,}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("""
        <div class="success-box">
            ✅ Data berhasil dibersihkan. Kolom <strong>Debit</strong>, <strong>Kredit</strong>, dan
            <strong>Ending Balance</strong> tersimpan sebagai angka murni di Excel — tidak ada warning
            <em>"Number Stored as Text"</em>.
        </div>
        """, unsafe_allow_html=True)

        # ── PREVIEW TABLE ──
        st.markdown('<div class="section-label">③ Preview Data</div>', unsafe_allow_html=True)

        # Tampilkan versi display (format ribuan) untuk preview saja
        df_display = df.copy()
        for col in ['Debit', 'Kredit', 'Ending Balance']:
            df_display[col] = df_display[col].apply(
                lambda x: f"{int(x):,}".replace(",", ".") if x is not None and not (isinstance(x, float) and pd.isna(x)) else "-"
            )

        st.dataframe(df_display, use_container_width=True, height=420)

        # ── TAHAP 3: EXPORT ──
        st.markdown('<div class="section-label">④ Download Excel</div>', unsafe_allow_html=True)

        with st.status("📊  Menyiapkan file Excel...", expanded=True) as status_export:
            st.write("Membuat format kolom, header, dan styling...")
            processed_data = export_to_excel(df, uploaded_file.name)
            time.sleep(0.6)
            status_export.update(label="🎉  File Excel siap diunduh!", state="complete", expanded=False)

        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            filename_out = f"GL_{uploaded_file.name.rsplit('.', 1)[0]}.xlsx"
            st.download_button(
                label="📥  Download Hasil (.xlsx)",
                data=processed_data,
                file_name=filename_out,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
            st.markdown(f"""
            <p style="text-align:center; color:rgba(255,255,255,0.35); font-size:0.78rem; margin-top:0.5rem;">
                {filename_out} &nbsp;·&nbsp; {len(df):,} baris &nbsp;·&nbsp; {total_coa} akun
            </p>
            """, unsafe_allow_html=True)

    else:
        st.error("❌  Data gagal diekstrak. Mohon periksa kembali isi file .txt Anda.")


# ── FOOTER ──
st.markdown("---")
st.markdown("""
<p style="text-align:center; color:rgba(255,255,255,0.20); font-size:0.78rem; font-family:'Plus Jakarta Sans',sans-serif; margin-top:0.5rem;">
    GL Converter Pro &nbsp;·&nbsp; KAP Kuncara Budi Santosa & Rekan &nbsp;·&nbsp; Cabang Samarinda
</p>
""", unsafe_allow_html=True)