"""
MYOB General Ledger Cleaner
KAP Kuncara Budi Santosa & Rekan – Samarinda
Versi 1.0 | Juni 2025

Membersihkan export Buku Besar dari MYOB menjadi tabel terstruktur
dengan format: ID | COA | Nama Akun | Date | Memo | Debit | Credit | Ending Balance
"""

import streamlit as st
import pandas as pd
import re
import io
from openpyxl import load_workbook
import xlsxwriter
from datetime import datetime, date

# ─── Page Config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="MYOB GL Cleaner | KAP KCBS",
    page_icon="📒",
    layout="wide",
)

# ─── Styling ────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    /* ---- global ---- */
    html, body, [class*="css"] { font-family: 'Segoe UI', sans-serif; }

    /* ---- header banner ---- */
    .app-header {
        background: linear-gradient(135deg, #0d2a54 0%, #1a3f7a 100%);
        border-radius: 12px;
        padding: 24px 32px;
        margin-bottom: 24px;
        display: flex;
        align-items: center;
        gap: 18px;
    }
    .app-header h1 {
        color: #f0c040;
        font-size: 1.65rem;
        font-weight: 700;
        margin: 0;
        letter-spacing: .5px;
    }
    .app-header p {
        color: #b8cfee;
        font-size: .85rem;
        margin: 4px 0 0;
    }

    /* ---- metric cards ---- */
    .metric-row { display: flex; gap: 16px; flex-wrap: wrap; margin: 16px 0; }
    .metric-card {
        background: #f8faff;
        border: 1px solid #d0dff5;
        border-left: 4px solid #1a3f7a;
        border-radius: 8px;
        padding: 14px 20px;
        min-width: 160px;
        flex: 1;
    }
    .metric-card .label { font-size: .75rem; color: #6b7a99; text-transform: uppercase; letter-spacing: .6px; }
    .metric-card .value { font-size: 1.4rem; font-weight: 700; color: #0d2a54; margin-top: 4px; }
    .metric-card .sub   { font-size: .78rem; color: #8899bb; margin-top: 2px; }

    /* ---- section title ---- */
    .section-title {
        font-weight: 700;
        font-size: 1rem;
        color: #0d2a54;
        border-bottom: 2px solid #d0dff5;
        padding-bottom: 6px;
        margin: 20px 0 12px;
    }

    /* ---- badge ---- */
    .badge-ok   { background:#d4edda; color:#155724; border-radius:20px; padding:2px 10px; font-size:.78rem; }
    .badge-warn { background:#fff3cd; color:#856404; border-radius:20px; padding:2px 10px; font-size:.78rem; }
    .badge-err  { background:#f8d7da; color:#721c24; border-radius:20px; padding:2px 10px; font-size:.78rem; }

    /* ---- stDataFrame fix ---- */
    [data-testid="stDataFrame"] { border: 1px solid #dde8f5; border-radius: 8px; }

    /* ---- sidebar ---- */
    section[data-testid="stSidebar"] {
        background: #f0f4fb;
    }
    section[data-testid="stSidebar"] .stMarkdown h3 {
        color: #0d2a54;
        font-size: .95rem;
    }
</style>
""", unsafe_allow_html=True)

# ─── Header ─────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="app-header">
  <div>📒</div>
  <div>
    <h1>MYOB General Ledger Cleaner</h1>
    <p>KAP Kuncara Budi Santosa & Rekan · Samarinda · Konversi Buku Besar MYOB ke tabel bersih</p>
  </div>
</div>
""", unsafe_allow_html=True)

# ─── Helper Functions ────────────────────────────────────────────────────────────

COLUMN_ALIASES = {
    "id":              ["id#", "id", "no", "number", "trx id", "transaction id", "journal #", "journal no"],
    "src":             ["src", "source", "type", "journal type", "tipe"],
    "date":            ["date", "tanggal", "tgl", "transaction date"],
    "memo":            ["memo", "description", "keterangan", "narasi", "uraian", "particulars"],
    "debit":           ["debit", "dr", "debet"],
    "credit":          ["credit", "cr", "kredit"],
    "job":             ["job", "pekerjaan", "project"],
    "net_activity":    ["net activity", "net", "aktivitas bersih", "mutasi"],
    "ending_balance":  ["ending balance", "balance", "saldo akhir", "saldo", "running balance", "closing balance"],
}

def detect_header_row(ws):
    """Scan worksheet to find row containing column headers (ID#, Date, Memo, etc.)."""
    for i, row in enumerate(ws.iter_rows(max_row=30, values_only=True), start=1):
        vals = [str(v).strip().lower() for v in row if v is not None]
        # Minimum: must have at least 3 of the key columns
        hits = sum(1 for v in vals for alias_list in COLUMN_ALIASES.values() for a in alias_list if a == v)
        if hits >= 3:
            return i, row
    return None, None

def map_columns(header_row):
    """Return dict: semantic_name → column_index (0-based). Dynamic alias matching."""
    mapping = {}
    for col_idx, cell in enumerate(header_row):
        if cell is None:
            continue
        cell_norm = str(cell).strip().lower()
        for sem_key, aliases in COLUMN_ALIASES.items():
            if cell_norm in aliases and sem_key not in mapping:
                mapping[sem_key] = col_idx
                break
    return mapping

def detect_company_period(ws):
    """Try to extract company name and period from top rows."""
    company, period = "", ""
    for i, row in enumerate(ws.iter_rows(max_row=10, values_only=True), start=1):
        vals = [str(v).strip() for v in row if v is not None]
        for v in vals:
            if re.search(r'(pt|cv|ud|tb|kp)\b', v.lower()) and not company:
                company = v
            if re.match(r'\d{2}/\d{2}/\d{4}\s+to\s+\d{2}/\d{2}/\d{4}', v.lower()) and not period:
                period = v
    return company, period

def parse_myob_number(val):
    """
    Parse MYOB Indonesian number format:
    'Rp2.500.000,00'  → 2500000.0
    'Rp1.297.434,00cr' → -1297434.0  (cr = credit = negative for certain accounts)
    Returns float or None.
    """
    if val is None:
        return None
    s = str(val).strip()
    if s in ('', '-', 'None', ''):
        return None

    negative = s.lower().endswith('cr')
    s = re.sub(r'[Rr][Pp]', '', s)       # remove Rp prefix
    s = s.lower().replace('cr', '').strip()
    s = s.replace('.', '').replace(',', '.')
    try:
        result = float(s)
        return -result if negative else result
    except (ValueError, TypeError):
        return None

def parse_date(val):
    """Handle both datetime objects and string dates from MYOB export."""
    if val is None:
        return None
    if isinstance(val, (datetime, date)):
        return val.strftime('%d/%m/%Y')
    s = str(val).strip()
    # Try common formats
    for fmt in ('%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y', '%m/%d/%Y'):
        try:
            return datetime.strptime(s, fmt).strftime('%d/%m/%Y')
        except ValueError:
            continue
    return s  # return as-is if unparseable

def is_coa_header(val):
    """Detect COA code row: e.g. '1-1110', '2-2000', '6-3110'."""
    if val is None:
        return False
    return bool(re.match(r'^\d+\s*[-–]\s*\d+', str(val).strip()))

def is_beginning_balance(val):
    """Detect beginning balance row."""
    if val is None:
        return False
    return 'beginning balance' in str(val).strip().lower()

def is_total_row(row, col_mapping):
    """Detect 'Total:' summary row that should be skipped."""
    memo_idx = col_mapping.get('memo')
    if memo_idx is not None and memo_idx < len(row):
        v = str(row[memo_idx] or '').strip().lower()
        if v in ('total:', 'total', 'jumlah:', 'jumlah'):
            return True
    # Also check all cells
    for v in row:
        if str(v or '').strip().lower() in ('total:', 'total'):
            return True
    return False

def parse_myob_gl(uploaded_file):
    """
    Main parser. Returns:
    - df: cleaned DataFrame
    - meta: dict with company, period, sheet_name, total_accounts, total_rows
    - col_mapping: the detected column mapping
    - warnings: list of warning messages
    """
    warnings_list = []

    wb = load_workbook(uploaded_file, read_only=True, data_only=True)
    sheet_name = wb.sheetnames[0]
    ws = wb[sheet_name]

    company, period = detect_company_period(ws)

    # Find header row
    header_row_num, header_row = detect_header_row(ws)
    if header_row is None:
        return None, {}, {}, ["❌ Tidak dapat menemukan baris header kolom. Pastikan file adalah export Buku Besar MYOB."]

    col_mapping = map_columns(header_row)

    # Validate minimum required columns
    required = ['id', 'date', 'memo', 'ending_balance']
    missing = [k for k in required if k not in col_mapping]
    if missing:
        warnings_list.append(f"⚠️ Kolom berikut tidak terdeteksi: {', '.join(missing)}. Hasil mungkin tidak lengkap.")

    # Parse all rows
    records = []
    current_coa = None
    current_nama = None
    total_accounts = 0

    for row_num, row in enumerate(ws.iter_rows(values_only=True), start=1):
        if row_num <= header_row_num:
            continue

        # Skip completely empty rows
        if all(v is None for v in row):
            continue

        col_b = row[1] if len(row) > 1 else None  # Column B always COA or ID in MYOB

        # Detect COA header row
        if is_coa_header(col_b):
            current_coa = str(col_b).strip()
            # Nama akun: column C (index 2) if exists
            current_nama = str(row[2]).strip() if len(row) > 2 and row[2] else ''
            total_accounts += 1
            continue

        # Detect beginning balance row
        if is_beginning_balance(col_b):
            beg_val_raw = row[2] if len(row) > 2 else None  # col C has the balance
            beg_val = parse_myob_number(beg_val_raw)
            records.append({
                'ID':              'Beginning Balance',
                'COA':             current_coa or '',
                'Nama Akun':       current_nama or '',
                'Date':            '',
                'Memo':            'Beginning Balance',
                'Debit':           None,
                'Credit':          None,
                'Ending Balance':  beg_val,
                '_row_type':       'beginning_balance',
            })
            continue

        # Skip total summary rows
        if is_total_row(row, col_mapping):
            continue

        # Transaction row – must have a date
        date_idx = col_mapping.get('date', 3)
        date_val = row[date_idx] if date_idx < len(row) else None
        if date_val is None:
            continue

        id_idx      = col_mapping.get('id', 1)
        memo_idx    = col_mapping.get('memo', 4)
        debit_idx   = col_mapping.get('debit', 5)
        credit_idx  = col_mapping.get('credit', 6)
        ending_idx  = col_mapping.get('ending_balance', 9)

        id_val      = str(row[id_idx]).strip() if id_idx < len(row) and row[id_idx] else ''
        memo_val    = str(row[memo_idx]).strip() if memo_idx < len(row) and row[memo_idx] else ''
        debit_val   = parse_myob_number(row[debit_idx] if debit_idx < len(row) else None)
        credit_val  = parse_myob_number(row[credit_idx] if credit_idx < len(row) else None)
        ending_val  = parse_myob_number(row[ending_idx] if ending_idx < len(row) else None)
        date_str    = parse_date(date_val)

        # Skip if no meaningful data
        if not id_val and not memo_val:
            continue

        records.append({
            'ID':             id_val,
            'COA':            current_coa or '',
            'Nama Akun':      current_nama or '',
            'Date':           date_str,
            'Memo':           memo_val,
            'Debit':          debit_val,
            'Credit':         credit_val,
            'Ending Balance': ending_val,
            '_row_type':      'transaction',
        })

    if not records:
        return None, {}, col_mapping, ["❌ Tidak ada data yang berhasil diparse. Periksa format file."]

    df = pd.DataFrame(records)

    meta = {
        'company':        company,
        'period':         period,
        'sheet_name':     sheet_name,
        'total_accounts': total_accounts,
        'total_rows':     len(df[df['_row_type'] == 'transaction']),
        'total_records':  len(df),
        'header_row':     header_row_num,
    }

    return df, meta, col_mapping, warnings_list


def export_to_excel(df: pd.DataFrame, meta: dict) -> bytes:
    """Export ke Excel simple dengan header bold + AutoFilter, siap difilter."""
    import math

    output = io.BytesIO()

    df_export = df.drop(columns=['_row_type'], errors='ignore').copy()

    # Sanitasi NaN → None agar xlsxwriter tidak crash
    for col in ['Debit', 'Credit', 'Ending Balance']:
        if col in df_export.columns:
            df_export[col] = df_export[col].apply(
                lambda x: None if (x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x)))) else x
            )

    with xlsxwriter.Workbook(output, {'in_memory': True, 'nan_inf_to_errors': True}) as wb:
        fmt_header = wb.add_format({
            'bold': True, 'bg_color': '#D9E1F2', 'border': 1,
            'align': 'center', 'valign': 'vcenter', 'text_wrap': True
        })
        fmt_num = wb.add_format({'num_format': '#,##0.00'})

        ws = wb.add_worksheet('Buku Besar')
        ws.freeze_panes(1, 0)

        headers    = ['ID', 'COA', 'Nama Akun', 'Date', 'Memo', 'Debit', 'Credit', 'Ending Balance']
        col_widths = [14,    10,    28,           13,     52,     16,      16,       18]

        for c, (h, w) in enumerate(zip(headers, col_widths)):
            ws.write(0, c, h, fmt_header)
            ws.set_column(c, c, w)
        ws.set_row(0, 20)

        numeric_cols = {'Debit', 'Credit', 'Ending Balance'}
        records = df_export.to_dict('records')

        for r_idx, rec in enumerate(records, start=1):
            for c_idx, col in enumerate(headers):
                val = rec.get(col)
                if col in numeric_cols and val is not None:
                    ws.write_number(r_idx, c_idx, val, fmt_num)
                else:
                    ws.write(r_idx, c_idx, val if val is not None else '')

        # AutoFilter on header row
        ws.autofilter(0, 0, len(records), len(headers) - 1)

    output.seek(0)
    return output.read()


def export_to_csv(df: pd.DataFrame) -> bytes:
    df_out = df.drop(columns=['_row_type'], errors='ignore').copy()
    for col in ['Debit', 'Credit', 'Ending Balance']:
        if col in df_out.columns:
            df_out[col] = df_out[col].apply(lambda x: f"{x:,.2f}" if pd.notna(x) else '')
    return df_out.to_csv(index=False, sep=';').encode('utf-8-sig')


# ─── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ Opsi")
    show_raw      = st.checkbox("Tampilkan tipe baris (debug)", value=False)
    filter_coa    = st.checkbox("Filter per COA", value=False)
    exclude_beg   = st.checkbox("Sembunyikan baris Beginning Balance", value=False)
    st.markdown("---")
    st.markdown("### 📖 Tentang")
    st.markdown("""
Aplikasi ini membersihkan export **Buku Besar MYOB** menjadi tabel terstruktur.

**Fitur:**
- Deteksi header kolom otomatis (alias matching)
- Parse angka format Indonesia `Rp#.###,##`
- Deteksi saldo negatif `cr`
- Export Excel (2 sheet) dan CSV
- Ringkasan per akun

**Format yang didukung:** `.xlsx`, `.xls`

---
*KAP Kuncara Budi Santosa & Rekan*  
*Samarinda, Kalimantan Timur*
""")

# ─── Main Upload ─────────────────────────────────────────────────────────────────
st.markdown('<div class="section-title">📂 Upload File Buku Besar MYOB</div>', unsafe_allow_html=True)

uploaded = st.file_uploader(
    "Upload file Excel export dari MYOB (General Ledger Detail)",
    type=["xlsx", "xls"],
    help="Export dari MYOB: Laporan → Buku Besar → Export ke Excel"
)

if uploaded is None:
    st.info("Upload file MYOB General Ledger untuk memulai. Mendukung format `.xlsx` / `.xls`")
    st.markdown("""
**Cara mendapatkan file dari MYOB:**
1. Buka MYOB → **Reports** → **Accounts** → **General Ledger (Detail)**
2. Atur periode dan filter akun yang diinginkan  
3. Klik **Print** → **Export** → Pilih **Microsoft Excel Spreadsheet (.xlsx)**
""")
    st.stop()

# ─── Parse ───────────────────────────────────────────────────────────────────────
with st.spinner("Membaca dan membersihkan data…"):
    df, meta, col_mapping, warnings = parse_myob_gl(uploaded)

# Show warnings
for w in warnings:
    st.warning(w)

if df is None:
    st.error("Gagal memproses file. Periksa apakah file merupakan export Buku Besar MYOB yang valid.")
    st.stop()

# ─── Info Banner ─────────────────────────────────────────────────────────────────
if meta.get('company') or meta.get('period'):
    st.success(f"✅ **{meta.get('company', 'Perusahaan tidak terdeteksi')}** | Periode: {meta.get('period', '-')} | Sheet: `{meta.get('sheet_name', '')}`")

# Metrics
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Jumlah Akun", meta.get('total_accounts', 0))
with col2:
    st.metric("Total Transaksi", meta.get('total_rows', 0))
with col3:
    total_debit = df['Debit'].sum() if 'Debit' in df.columns else 0
    st.metric("Total Debit", f"Rp {total_debit:,.0f}")
with col4:
    total_credit = df['Credit'].sum() if 'Credit' in df.columns else 0
    st.metric("Total Credit", f"Rp {total_credit:,.0f}")

# ─── Column Mapping Info ──────────────────────────────────────────────────────────
with st.expander("🔍 Deteksi Kolom (Column Mapping)", expanded=False):
    st.markdown(f"**Header ditemukan di baris:** `{meta.get('header_row', '?')}`")
    mapping_df = pd.DataFrame([
        {"Kolom Semantik": k, "Index (0-based)": v, "Status": "✅ Terdeteksi"}
        for k, v in col_mapping.items()
    ] + [
        {"Kolom Semantik": k, "Index (0-based)": "—", "Status": "⚠️ Tidak ditemukan"}
        for k in COLUMN_ALIASES if k not in col_mapping
    ])
    st.dataframe(mapping_df, hide_index=True, use_container_width=True)

# ─── Filter ───────────────────────────────────────────────────────────────────────
df_display = df.copy()

if exclude_beg and '_row_type' in df_display.columns:
    df_display = df_display[df_display['_row_type'] != 'beginning_balance']

if filter_coa:
    all_coas = sorted(df_display['COA'].dropna().unique().tolist())
    selected_coas = st.multiselect("Pilih COA:", all_coas, default=all_coas[:5] if len(all_coas) > 5 else all_coas)
    if selected_coas:
        df_display = df_display[df_display['COA'].isin(selected_coas)]

# ─── Preview ─────────────────────────────────────────────────────────────────────
st.markdown('<div class="section-title">📋 Preview Data Bersih</div>', unsafe_allow_html=True)

display_cols = ['ID', 'COA', 'Nama Akun', 'Date', 'Memo', 'Debit', 'Credit', 'Ending Balance']
if show_raw:
    display_cols.append('_row_type')

df_show = df_display[[c for c in display_cols if c in df_display.columns]].copy()

# Format numbers for display
for col in ['Debit', 'Credit', 'Ending Balance']:
    if col in df_show.columns:
        df_show[col] = df_show[col].apply(lambda x: f"{x:,.2f}" if pd.notna(x) and x is not None else '')

st.dataframe(
    df_show,
    hide_index=True,
    use_container_width=True,
    height=450,
)

st.caption(f"Menampilkan {len(df_display):,} baris dari {len(df):,} total baris | "
           f"Debit: Rp {total_debit:,.0f} | Credit: Rp {total_credit:,.0f}")

# ─── Ringkasan per Akun ───────────────────────────────────────────────────────────
with st.expander("📊 Ringkasan per Akun", expanded=False):
    trx_only = df[df.get('_row_type', pd.Series('transaction', index=df.index)) == 'transaction'] if '_row_type' in df.columns else df
    summary = trx_only.groupby(['COA', 'Nama Akun'], sort=False).agg(
        Jml_Transaksi=('ID', 'count'),
        Total_Debit=('Debit', 'sum'),
        Total_Credit=('Credit', 'sum'),
    ).reset_index()
    summary['Net Activity'] = summary['Total_Debit'] - summary['Total_Credit']

    for col in ['Total_Debit', 'Total_Credit', 'Net Activity']:
        summary[col] = summary[col].apply(lambda x: f"{x:,.2f}" if pd.notna(x) else '')

    summary.columns = ['COA', 'Nama Akun', 'Jml Transaksi', 'Total Debit', 'Total Credit', 'Net Activity']
    st.dataframe(summary, hide_index=True, use_container_width=True)

# ─── Export ───────────────────────────────────────────────────────────────────────
st.markdown('<div class="section-title">💾 Export Data</div>', unsafe_allow_html=True)

fname_base = uploaded.name.replace('.xlsx', '').replace('.xls', '')
timestamp  = datetime.now().strftime('%Y%m%d_%H%M')

col_ex1, col_ex2 = st.columns(2)

with col_ex1:
    xlsx_bytes = export_to_excel(df_display, meta)
    st.download_button(
        label="⬇️ Download Excel (.xlsx)",
        data=xlsx_bytes,
        file_name=f"GL_Clean_{fname_base}_{timestamp}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
        type="primary",
    )
    st.caption("2 sheet: Detail + Ringkasan per Akun. Dengan styling KAP KCBS.")

with col_ex2:
    csv_bytes = export_to_csv(df_display)
    st.download_button(
        label="⬇️ Download CSV (;) – UTF-8",
        data=csv_bytes,
        file_name=f"GL_Clean_{fname_base}_{timestamp}.csv",
        mime="text/csv",
        use_container_width=True,
    )
    st.caption("Delimiter semicolon (;) siap import ke Accurate / Excel.")

# ─── Footer ───────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown(
    "<small style='color:#aaa'>MYOB GL Cleaner v1.0 · KAP Kuncara Budi Santosa & Rekan · Samarinda · 2025</small>",
    unsafe_allow_html=True
)