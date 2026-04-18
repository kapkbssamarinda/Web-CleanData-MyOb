import streamlit as st
import pandas as pd
import csv
import io
import time

# Fungsi untuk membersihkan dan memformat nominal uang
def clean_currency(val):
    if not val or pd.isna(val) or str(val).strip() == "":
        return "-"
    
    val = str(val).replace('Rp', '').replace('"', '').strip()
    val = val.replace(',', '') 
    
    if val.endswith('.00'):
        val = val[:-3]
    if val.endswith('cr'):
        val = val.replace('cr', '').strip()
        
    try:
        num = int(float(val))
        if num == 0:
            return "-"
        return f"{num:,}".replace(",", ".")
    except ValueError:
        return val if val else "-"

# Fungsi untuk membersihkan format tanggal
def clean_date(val):
    if not val:
        return ""
    return str(val).split(" ")[0].strip()

# Fungsi utama untuk memproses baris data secara dinamis
def process_gl_data(data_rows):
    parsed_data = []
    current_coa = ""
    current_account = ""
    start_reading = False
    
    idx_id, idx_date, idx_memo, idx_debit, idx_credit, idx_eb = 0, 2, 3, 4, 5, 8
    
    for row in data_rows:
        clean_row = [str(cell).strip() for cell in row]
        
        if all(cell == "" for cell in clean_row):
            continue
            
        if "ID#" in clean_row and "Date" in clean_row:
            idx_id = clean_row.index("ID#")
            idx_date = clean_row.index("Date")
            idx_memo = clean_row.index("Memo")
            idx_debit = clean_row.index("Debit")
            idx_credit = clean_row.index("Credit")
            
            for i, col in enumerate(clean_row):
                if "Ending Balance" in col:
                    idx_eb = i
                    break
            
            start_reading = True
            continue
            
        if not start_reading:
            continue
            
        coa_idx = -1
        for i, cell in enumerate(clean_row):
            if "-" in cell and cell[0].isdigit() and len(cell) >= 5:
                coa_idx = i
                break
                
        if coa_idx != -1 and (len(clean_row) > idx_date and clean_row[idx_date] == ""):
            current_coa = clean_row[coa_idx]
            current_account = ""
            for cell in clean_row[coa_idx+1:]:
                if cell != "":
                    current_account = cell
                    break
            continue
            
        bb_idx = -1
        for i, cell in enumerate(clean_row):
            if "Beginning Balance" in cell:
                bb_idx = i
                break
                
        if bb_idx != -1:
            memo = "Beginning Balance (Saldo Awal)"
            balance = ""
            for cell in clean_row[bb_idx+1:]:
                if cell != "" and cell != ":":
                    balance = cell
                    break
            if not balance and len(clean_row) > idx_eb:
                balance = clean_row[idx_eb]
                
            parsed_data.append({
                "ID": "-",
                "Tanggal": "-",
                "COA": current_coa,
                "Nama Akun": current_account,
                "Memo": memo,
                "Debit": "-",
                "Kredit": "-",
                "Ending Balance": clean_currency(balance)
            })
            continue
            
        if len(clean_row) > idx_id and clean_row[idx_id].isdigit():
            _id = clean_row[idx_id]
            _date = clean_row[idx_date] if len(clean_row) > idx_date else ""
            _memo = clean_row[idx_memo] if len(clean_row) > idx_memo else ""
            _debit = clean_row[idx_debit] if len(clean_row) > idx_debit else ""
            _credit = clean_row[idx_credit] if len(clean_row) > idx_credit else ""
            _eb = clean_row[idx_eb] if len(clean_row) > idx_eb else ""
            if not _eb and len(clean_row) > idx_eb + 1:
                _eb = clean_row[idx_eb + 1]
                
            parsed_data.append({
                "ID": _id,
                "Tanggal": clean_date(_date),
                "COA": current_coa,
                "Nama Akun": current_account,
                "Memo": _memo,
                "Debit": clean_currency(_debit),
                "Kredit": clean_currency(_credit),
                "Ending Balance": clean_currency(_eb)
            })
            
    return pd.DataFrame(parsed_data)

# ================= UI STREAMLIT =================

st.set_page_config(page_title="GL Converter Pro", page_icon="📊", layout="wide")

st.title("📊 General Ledger Data Extractor (Pro)")
st.markdown("""
Aplikasi ini sudah mendukung **Auto-Detect Kolom**. Anda bisa mengunggah file `.txt`, `.csv`, atau `.xlsx` mentah dan sistem akan otomatis mencari posisi data yang tepat.
""")

uploaded_file = st.file_uploader("Pilih file GL Anda (.txt, .csv, .xlsx, .xls)", type=['csv', 'txt', 'xlsx', 'xls'])

if uploaded_file is not None:
    try:
        file_extension = uploaded_file.name.split('.')[-1].lower()
        data_rows = []

        # ── TAHAP 1: MEMBACA FILE ──────────────────────────────────────
        with st.status("📂 Membaca berkas...", expanded=True) as status:
            st.write(f"🔍 Mendeteksi format file: **{file_extension.upper()}**")
            time.sleep(0.4)

            if file_extension in ['xlsx', 'xls']:
                st.write("📋 Memuat lembar kerja Excel...")
                df_raw = pd.read_excel(uploaded_file, header=None)
                df_raw = df_raw.astype(str).replace('nan', '')
                data_rows = df_raw.values.tolist()
            else:
                st.write("📄 Membaca isi file teks/CSV...")
                file_content = uploaded_file.getvalue().decode("utf-8", errors="replace")
                reader = csv.reader(file_content.splitlines())
                data_rows = list(reader)

            st.write(f"✅ Berhasil membaca **{len(data_rows)}** baris mentah.")
            time.sleep(0.3)
            status.update(label="✅ Berkas berhasil dimuat!", state="complete", expanded=False)

        # ── TAHAP 2: CLEANING & PARSING ───────────────────────────────
        with st.status("⚙️ Memproses dan membersihkan data...", expanded=True) as status:
            st.write("🧹 Menjalankan auto-detect kolom...")
            time.sleep(0.3)
            st.write("💱 Membersihkan format nominal mata uang...")
            time.sleep(0.3)
            st.write("📅 Menormalisasi format tanggal...")
            time.sleep(0.3)
            st.write("🗂️ Memetakan COA dan nama akun...")
            time.sleep(0.2)

            df = process_gl_data(data_rows)

            time.sleep(0.2)
            status.update(label="✅ Proses cleaning selesai!", state="complete", expanded=False)

        # ── TAHAP 3: TAMPILKAN HASIL ───────────────────────────────────
        if df.empty:
            st.warning("⚠️ Tidak ada data yang berhasil diekstrak. Pastikan strukturnya sesuai dengan format General Ledger.")
        else:
            st.success(f"🎉 Berhasil mengekstrak **{len(df)}** baris data!")
            st.dataframe(df, use_container_width=True)

            # ── TAHAP 4: EXPORT ────────────────────────────────────────
            with st.spinner("📦 Menyiapkan file ekspor Excel..."):
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df.to_excel(writer, index=False, sheet_name='GL_Detail')
                    worksheet = writer.sheets['GL_Detail']
                    for i, col in enumerate(df.columns):
                        column_len = max(df[col].astype(str).map(len).max(), len(col)) + 2
                        worksheet.set_column(i, i, min(column_len, 50))
                processed_data = output.getvalue()

            st.download_button(
                label="📥 Export Hasil ke Excel (.xlsx)",
                data=processed_data,
                file_name=f"Converted_{uploaded_file.name.split('.')[0]}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    except Exception as e:
        st.error(f"❌ Terjadi kesalahan: {e}")