import streamlit as st
import pandas as pd
import re
import io

# --- 1. Konfigurasi Halaman (UI/UX) ---
st.set_page_config(
    page_title="MYOB Data Cleaner",
    page_icon="🧹",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS Sederhana (Hanya padding, tanpa warna background hardcoded agar aman di Dark Mode)
st.markdown("""
<style>
    div.block-container {padding-top: 2rem;}
</style>
""", unsafe_allow_html=True)

# --- 2. Fungsi Logika (Core Logic) ---

def clean_currency_to_float(val):
    """Konversi string kotor ke float dengan cerdas."""
    if pd.isna(val) or val == '' or str(val).strip() == '':
        return 0.0
    
    val_str = str(val).strip()
    is_negative = False
    if '(' in val_str and ')' in val_str:
        is_negative = True
        val_str = val_str.replace('(', '').replace(')', '')
    
    val_str = re.sub(r'Rp|cr|dr|\s', '', val_str, flags=re.IGNORECASE)
    
    # Logika Separator
    if ',' in val_str and '.' in val_str:
        if val_str.rfind(',') > val_str.rfind('.'): 
            val_str = val_str.replace('.', '').replace(',', '.')
        else:
            val_str = val_str.replace(',', '')
    elif ',' in val_str:
        parts = val_str.split(',')
        if len(parts[-1]) == 2: 
            val_str = val_str.replace(',', '.')
        else: 
            val_str = val_str.replace(',', '')
    elif '.' in val_str:
         parts = val_str.split('.')
         if len(parts) > 1 and len(parts[-1]) == 3:
             val_str = val_str.replace('.', '')
    
    try:
        f_val = float(val_str)
        return -f_val if is_negative else f_val
    except ValueError:
        return 0.0

def format_indo(x):
    """Format tampilan Indonesia (1.000,00)."""
    try:
        us_fmt = "{:,.2f}".format(x)
        return us_fmt.replace(",", "X").replace(".", ",").replace("X", ".")
    except:
        return str(x)

def process_myob_file(uploaded_file):
    if uploaded_file.name.endswith('.csv'):
        try:
            df = pd.read_csv(uploaded_file, header=None, encoding='utf-8')
        except:
            df = pd.read_csv(uploaded_file, header=None, encoding='latin1')
    else:
        df = pd.read_excel(uploaded_file, header=None)

    # Cari Header
    header_idx = -1
    for i, row in df.iterrows():
        row_str = row.astype(str).str.cat(sep=' ')
        if 'ID#' in row_str and 'Date' in row_str:
            header_idx = i
            break
    
    if header_idx == -1:
        return None, "Header kolom (ID#, Date) tidak ditemukan dalam file."

    df.columns = df.iloc[header_idx]
    df_data = df.iloc[header_idx+1:].reset_index(drop=True)
    df_data.columns = [str(c).strip() for c in df_data.columns]
    
    # Mapping Kolom
    try:
        col_id = 'ID#'
        col_date = 'Date'
        col_memo = 'Memo'
        col_debit = 'Debit'
        col_credit = 'Credit'
        col_end_bal = 'Ending Balance'
        col_src = 'Src' if 'Src' in df_data.columns else df_data.columns[2]
    except KeyError as e:
        return None, f"Kolom {e} tidak ditemukan."

    cleaned_rows = []
    current_account_name = None
    
    # Proses Iterasi
    for index, row in df_data.iterrows():
        id_val = str(row[col_id]).strip()
        date_val = str(row[col_date]).strip()
        memo_val = str(row[col_memo]).strip()
        
        # Header Akun
        is_header_account = (
            re.match(r'^\d-\d{4}', id_val) and 
            (date_val == 'nan' or date_val == '')
        )

        if is_header_account:
            possible_name = str(row.get(col_src, '')).strip()
            if possible_name == 'nan' or possible_name == '':
                possible_name = str(df_data.iloc[index, 2]).strip()
            current_account_name = possible_name
            continue 

        # Beginning Balance
        if "Beginning Balance" in id_val:
            val_src = row.get(col_src)
            saldo_awal = clean_currency_to_float(val_src)
            
            if saldo_awal == 0:
                 val_end = clean_currency_to_float(row[col_end_bal])
                 if val_end != 0: saldo_awal = val_end

            cleaned_rows.append({
                'ID': '-',
                'Date': '01/01/2024',
                'Memo': 'Beginning Balance',
                'Debit': 0.0,
                'Credit': 0.0,
                'Ending Balance': saldo_awal,
                'Nama Akun': current_account_name
            })
            continue

        # Transaksi
        if len(date_val) > 5 and (('/' in date_val) or ('-' in date_val)):
            cleaned_rows.append({
                'ID': id_val,
                'Date': date_val,
                'Memo': memo_val,
                'Debit': clean_currency_to_float(row[col_debit]),
                'Credit': clean_currency_to_float(row[col_credit]),
                'Ending Balance': clean_currency_to_float(row[col_end_bal]),
                'Nama Akun': current_account_name
            })

    if not cleaned_rows:
        return None, "Tidak ada data transaksi."

    result_df = pd.DataFrame(cleaned_rows)
    result_df.index = result_df.index + 1 # Start index from 1
    return result_df, None

# --- 3. Tampilan UI Utama ---

# SIDEBAR: Upload & Bantuan
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2920/2920349.png", width=60)
    st.title("MYOB Cleaner")
    
    st.markdown("---")
    uploaded_file = st.file_uploader("📂 Upload File (Excel/CSV)", type=['xlsx', 'csv'])
    
    st.info("💡 **Tips:** Pastikan file adalah export 'General Ledger [Detail]' dari MYOB.")

    with st.expander("❓ Bantuan & Format File"):
        st.markdown("""
        **Cara Penggunaan:**
        1. Export laporan GL Detail dari MYOB ke Excel/CSV.
        2. Upload file di sini.
        3. Download hasil yang sudah rapi.
        
        **Fitur:**
        - Auto-remove header kotor.
        - Deteksi Saldo Awal (Beginning Balance).
        - Format Angka Indonesia.
        - Download per Akun.
        """)

# AREA UTAMA
st.title("🧹 General Ledger Cleaner")
st.markdown("Transformasi data MYOB yang berantakan menjadi tabel analisis siap pakai.")

if uploaded_file:
    # Menggunakan status container
    with st.status("🔍 Menganalisis dan membersihkan data...", expanded=True) as status:
        st.write("Membaca file...")
        df_result, error = process_myob_file(uploaded_file)
        
        if error:
            status.update(label="Terjadi Kesalahan!", state="error", expanded=True)
            st.error(error)
        else:
            status.update(label="✅ Data berhasil diproses!", state="complete", expanded=False)

    if not error:
        # Layout Tabs
        tab1, tab2, tab3 = st.tabs(["📋 Data Cleaned", "📊 Dashboard Ringkasan", "🔍 Filter & Download Akun"])
        cols_to_format = ['Debit', 'Credit', 'Ending Balance']

        # --- TAB 1: Data Utama ---
        with tab1:
            st.markdown("### 📋 Preview Data Keseluruhan")
            
            # Display
            df_display = df_result.copy()
            for col in cols_to_format:
                df_display[col] = df_display[col].apply(format_indo)
            st.dataframe(df_display, use_container_width=True, height=400)
            
            st.divider()
            st.subheader("📥 Download Semua Data")
            
            # Persiapan Data Export
            df_export = df_result.copy()
            for col in cols_to_format:
                df_export[col] = df_export[col].apply(format_indo)

            c1, c2 = st.columns(2)
            with c1:
                csv = df_export.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📄 Download CSV",
                    data=csv,
                    file_name='Cleaned_GL_All.csv',
                    mime='text/csv',
                    use_container_width=True,
                    type='primary'
                )
            with c2:
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                    df_export.to_excel(writer, index=False, sheet_name='All Data')
                st.download_button(
                    label="📊 Download Excel",
                    data=buffer.getvalue(),
                    file_name='Cleaned_GL_All.xlsx',
                    mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    use_container_width=True
                )

        # --- TAB 2: Ringkasan ---
        with tab2:
            st.markdown("### 📊 Ringkasan Laporan")
            
            # Metrics Row (Hanya 2 kolom, hapus Total Debit)
            m1, m2 = st.columns(2)
            with m1:
                st.metric("Total Baris Data", f"{len(df_result):,}")
            with m2:
                st.metric("Jumlah Akun", f"{df_result['Nama Akun'].nunique()}")
            
            st.divider()
            
            # --- Chart Interaktif ---
            st.subheader("Grafik Frekuensi Transaksi per Akun")
            
            # Persiapkan Data Grafik
            chart_data = df_result['Nama Akun'].value_counts().reset_index()
            chart_data.columns = ['Nama Akun', 'Jumlah Transaksi']
            
            # Kontrol Chart (Filter & Sort)
            c_filter1, c_filter2 = st.columns([2, 1])
            
            with c_filter2:
                sort_option = st.radio("Urutkan Berdasarkan:", 
                                       ["Jumlah Transaksi (Tertinggi)", "Nama Akun (A-Z)"])
            
            with c_filter1:
                all_accounts = chart_data['Nama Akun'].tolist()
                selected_accounts_chart = st.multiselect(
                    "Pilih Akun untuk Ditampilkan (Kosongkan untuk memilih semua):",
                    options=all_accounts,
                    default=all_accounts # Default semua
                )
            
            # Logika Filter
            if selected_accounts_chart:
                chart_df = chart_data[chart_data['Nama Akun'].isin(selected_accounts_chart)]
            else:
                chart_df = chart_data # Jika user hapus semua seleksi, tampilkan semua (fallback)
            
            # Logika Sorting
            if sort_option == "Jumlah Transaksi (Tertinggi)":
                chart_df = chart_df.sort_values(by='Jumlah Transaksi', ascending=False)
            else:
                chart_df = chart_df.sort_values(by='Nama Akun', ascending=True)
            
            # Tampilkan Grafik
            st.bar_chart(chart_df.set_index('Nama Akun'), color="#4CAF50")
            st.caption(f"Menampilkan {len(chart_df)} akun.")

        # --- TAB 3: Filter & Detail ---
        with tab3:
            st.markdown("### 🔍 Analisa Per Akun")
            
            col_sel, col_empty = st.columns([1, 1])
            with col_sel:
                account_list = sorted(df_result['Nama Akun'].dropna().unique().astype(str))
                selected_account = st.selectbox("Pilih Akun untuk Dianalisis:", account_list)
            
            if selected_account:
                # Filter Data
                sub_df = df_result[df_result['Nama Akun'] == selected_account].reset_index(drop=True)
                sub_df.index = sub_df.index + 1 # Index start 1
                
                # Kalkulasi
                beg_bal_row = sub_df[sub_df['Memo'] == 'Beginning Balance']
                beg_bal_val = beg_bal_row.iloc[0]['Ending Balance'] if not beg_bal_row.empty else 0.0
                end_bal_val = sub_df.iloc[-1]['Ending Balance'] if not sub_df.empty else 0.0
                total_rows_account = len(sub_df) # Termasuk saldo awal

                # Tampilan Metrics Akun
                st.markdown(f"**Ringkasan: {selected_account}**")
                k1, k2, k3 = st.columns(3)
                k1.metric("Saldo Awal", f"Rp {format_indo(beg_bal_val)}")
                k2.metric("Saldo Akhir", f"Rp {format_indo(end_bal_val)}", 
                          delta=f"{format_indo(end_bal_val - beg_bal_val)} (Perubahan)")
                k3.metric("Jml Baris", total_rows_account)
                
                # Download Per Akun
                st.markdown("---")
                col_title, col_btn = st.columns([3, 1])
                with col_title:
                    st.write(f"**Detail Transaksi**")
                with col_btn:
                    # Logic Download Per Akun
                    sub_df_export = sub_df.copy()
                    for col in cols_to_format:
                        sub_df_export[col] = sub_df_export[col].apply(format_indo)
                    
                    buffer_acc = io.BytesIO()
                    with pd.ExcelWriter(buffer_acc, engine='openpyxl') as writer:
                        safe_sheet_name = (selected_account[:28] + '..') if len(selected_account) > 30 else selected_account
                        sub_df_export.to_excel(writer, index=False, sheet_name=safe_sheet_name)
                    
                    st.download_button(
                        label="📥 Download Akun Ini (.xlsx)",
                        data=buffer_acc.getvalue(),
                        file_name=f'GL_{selected_account}.xlsx',
                        mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                        type='primary',
                        use_container_width=True
                    )

                # Tampilkan Tabel
                sub_df_disp = sub_df.copy()
                for col in cols_to_format:
                    sub_df_disp[col] = sub_df_disp[col].apply(format_indo)
                st.dataframe(sub_df_disp, use_container_width=True)

else:
    # Tampilan awal jika belum upload
    st.container()
    st.info("👈 Silakan upload file GL (General Ledger) Anda melalui panel di sebelah kiri untuk memulai.")