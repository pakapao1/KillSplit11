import io
import os
import re
import tempfile
import zipfile
from pathlib import Path

import streamlit as st
from pypdf import PdfReader, PdfWriter


# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="BANG KILL PDF ",
    page_icon="⚡",
    layout="centered",
    initial_sidebar_state="collapsed"
)


# ============================================================
# CUSTOM CSS STYLING
# ============================================================

st.markdown("""
<style>
    /* Global Container */
    .main .block-container {
        padding-top: 2rem;
        padding-bottom: 3rem;
        max-width: 800px;
    }

    /* Hero Header Banner */
    .hero-banner {
        background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
        color: #ffffff;
        padding: 2rem 2.2rem;
        border-radius: 20px;
        margin-bottom: 1.8rem;
        box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.2);
        border: 1px solid rgba(255, 255, 255, 0.08);
    }

    .hero-header-title {
        font-size: 2.2rem;
        font-weight: 800;
        letter-spacing: -0.5px;
        margin: 0;
        color: #ffffff;
        display: flex;
        align-items: center;
        gap: 12px;
    }

    .hero-badge {
        background: rgba(59, 130, 246, 0.25);
        color: #60a5fa;
        font-size: 0.75rem;
        font-weight: 600;
        padding: 4px 10px;
        border-radius: 20px;
        border: 1px solid rgba(96, 165, 250, 0.3);
        margin-left: auto;
    }

    .hero-subtitle {
        color: #94a3b8;
        font-size: 0.95rem;
        margin-top: 8px;
        margin-bottom: 0;
    }

    /* Metric Box Cards */
    .stat-card {
        background: #ffffff;
        border-radius: 16px;
        padding: 1.25rem 1rem;
        border: 1px solid #e2e8f0;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.04);
        text-align: center;
        transition: all 0.2s ease-in-out;
    }

    .stat-card:hover {
        transform: translateY(-3px);
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.08);
        border-color: #cbd5e1;
    }

    .stat-label {
        color: #64748b;
        font-size: 0.8rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-bottom: 6px;
    }

    .stat-value {
        color: #0f172a;
        font-size: 2rem;
        font-weight: 800;
        line-height: 1.2;
    }

    .stat-desc {
        color: #10b981;
        font-size: 0.8rem;
        font-weight: 600;
        margin-top: 4px;
    }

    /* Gazette Tag Badge */
    .gazette-tag {
        background-color: #eff6ff;
        color: #1d4ed8;
        padding: 6px 14px;
        border-radius: 8px;
        font-family: monospace;
        font-weight: 700;
        font-size: 1rem;
        border: 1px solid #bfdbfe;
        display: inline-block;
    }
</style>
""", unsafe_allow_html=True)


# ============================================================
# GAZETTE METADATA
# ============================================================

def extract_gazette_metadata(full_text, original_filename):
    pu_match = re.search(
        r"P\.U\.\s*\(([AB])\)\s*(\d+)",
        full_text,
        re.IGNORECASE
    )

    year_match = re.search(
        r"\b(20\d{2})\b",
        full_text
    )

    if pu_match:
        pu_type = (
            "PUBS"
            if pu_match.group(1).upper() == "B"
            else "PUAS"
        )
        pu_no = pu_match.group(2)
        year = (
            year_match.group(1)
            if year_match
            else "2026"
        )
        return f"MY_{pu_type}_{year}_{pu_no}"
    else:
        clean_name = os.path.splitext(original_filename)[0]
        return clean_name


# ============================================================
# LANGUAGE DETECTION
# ============================================================

def detect_page_language(text):
    text_upper = text.upper()

    bm_keywords = [
        "UNDANG-UNDANG MALAYSIA", "KANUN TANAH NEGARA", "SUSUNAN PERENGGAN",
        "SUSUNAN PERATURAN", "SENARAI PINDAAN", "PERINTAH", "PERATURAN",
        "AKTA", "PADA MENJALANKAN KUASA", "JADUAL", "PERIZABAN TANAH",
        "DIAMBIL PERHATIAN", "PEMBATALAN", "PENGECUALIAN", "MENTERI ",
        "DIBUAT ", "BERTARIKH", "LESEN", "TANAN", "PENUMPANG", "KARGO",
        "KAPAL", " DENGAN ", " OLEH ",
    ]

    en_keywords = [
        "LAWS OF MALAYSIA", "NATIONAL LAND CODE", "ARRANGEMENT OF PARAGRAPHS",
        "ARRANGEMENT OF REGULATIONS", "LIST OF AMENDMENTS", "ORDER",
        "REGULATION", "ACT", "IN EXERCISE OF", "SCHEDULE", "RESERVATION OF LAND",
        "TAKE NOTICE", "REVOCATION", "EXEMPTION", "MINISTER OF", "MADE ",
        "DATED", "LICENCE", "LICENSE", "TONNAGE", "PASSENGER", "CARGO",
        "VESSEL", "SHIP", " WITH ", " BY ",
    ]

    bm_score = sum(1 for k in bm_keywords if k in text_upper)
    en_score = sum(1 for k in en_keywords if k in text_upper)

    if bm_score > en_score:
        return "BM"
    elif en_score > bm_score:
        return "EN"

    return "UNKNOWN"


# ============================================================
# PROCESS PDF
# ============================================================

def process_gazette_pdf(file_bytes, original_filename):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
        temp_file.write(file_bytes)
        input_path = temp_file.name

    reader = PdfReader(input_path)
    total_pages = len(reader.pages)

    if total_pages == 0:
        os.remove(input_path)
        raise ValueError("PDF tidak mempunyai muka surat.")

    full_text = ""
    for page in reader.pages:
        full_text += page.extract_text() or ""

    base_filename = extract_gazette_metadata(full_text, original_filename)

    first_page_text = (reader.pages[0].extract_text() or "").upper()
    is_cover_page = ("WARTA KERAJAAN" in first_page_text or "GAZETTE" in first_page_text)

    cover_page = None
    start_index = 0

    if is_cover_page and total_pages > 1:
        cover_page = reader.pages[0]
        start_index = 1

    my_pages = []
    en_pages = []
    current_detected_lang = None

    for i in range(start_index, total_pages):
        page = reader.pages[i]
        text = page.extract_text() or ""
        lang = detect_page_language(text)

        if lang == "UNKNOWN" and current_detected_lang:
            lang = current_detected_lang
        elif lang != "UNKNOWN":
            current_detected_lang = lang

        if lang == "BM":
            my_pages.append(page)
        elif lang == "EN":
            en_pages.append(page)

    output_dir = tempfile.mkdtemp()
    output_files = []

    if my_pages:
        writer_my = PdfWriter()
        if cover_page:
            writer_my.add_page(cover_page)
        for page in my_pages:
            writer_my.add_page(page)

        output_my = os.path.join(output_dir, f"{base_filename}_MY.pdf")
        with open(output_my, "wb") as f:
            writer_my.write(f)
        output_files.append(output_my)

    if en_pages:
        writer_en = PdfWriter()
        if cover_page:
            writer_en.add_page(cover_page)
        for page in en_pages:
            writer_en.add_page(page)

        output_en = os.path.join(output_dir, f"{base_filename}_EN.pdf")
        with open(output_en, "wb") as f:
            writer_en.write(f)
        output_files.append(output_en)

    os.remove(input_path)

    return (
        base_filename,
        output_files,
        len(my_pages),
        len(en_pages),
        is_cover_page
    )


# ============================================================
# USER INTERFACE
# ============================================================

# Hero Banner Header
st.markdown("""
<div class="hero-banner">
    <div style="display: flex; align-items: center; justify-content: space-between;">
        <div class="hero-header-title">⚡ BANG KILL PDF</div>
        <span class="hero-badge">v1.0 Pro</span>
    </div>
    <p class="hero-subtitle">Splitter Untuk BI Dan BM</p>
</div>
""", unsafe_allow_html=True)

# Upload Section Box
with st.container(border=True):
    st.subheader("📁 Muat Naik Fail Warta")
    uploaded_file = st.file_uploader(
        "Pilih fail PDF",
        type=["pdf"],
        label_visibility="collapsed"
    )

    if uploaded_file:
        st.info(f"📄 Fail sedia diproses: **{uploaded_file.name}**")
        
        split_btn = st.button(
            "🚀 ASINGKAN PDF SEKARANG",
            use_container_width=True,
            type="primary"
        )
    else:
        split_btn = False

# Processing Results
if uploaded_file and split_btn:
    with st.spinner("⚡ Sedang menganalisis & mengasingkan muka surat..."):
        try:
            (
                base_filename,
                output_files,
                my_count,
                en_count,
                cover_found
            ) = process_gazette_pdf(
                uploaded_file.getvalue(),
                uploaded_file.name
            )

            st.success("✅ **Proses pengasingan selesai dengan jaya!**")

            st.markdown("### 📊 Ringkasan Hasil Process")

            # Metadata ID Display
            st.markdown(
                f"**ID Gazette Dikesan:** <span class='gazette-tag'>{base_filename}</span>",
                unsafe_allow_html=True
            )
            st.write("")

            # Grid Dashboard Cards for Stats
            col1, col2, col3 = st.columns(3)

            with col1:
                st.markdown(f"""
                <div class="stat-card">
                    <div class="stat-label">🇲🇾 Bahasa Melayu</div>
                    <div class="stat-value">{my_count}</div>
                    <div class="stat-desc">Muka Surat</div>
                </div>
                """, unsafe_allow_html=True)

            with col2:
                st.markdown(f"""
                <div class="stat-card">
                    <div class="stat-label">🇬🇧 English</div>
                    <div class="stat-value">{en_count}</div>
                    <div class="stat-desc">Muka Surat</div>
                </div>
                """, unsafe_allow_html=True)

            with col3:
                cover_text = "Dikesan" if cover_found else "Tiada"
                cover_sub = "Disertakan" if cover_found else "Abaikan"
                st.markdown(f"""
                <div class="stat-card">
                    <div class="stat-label">📑 Cover Page</div>
                    <div class="stat-value" style="font-size: 1.4rem; padding-top: 6px;">{cover_text}</div>
                    <div class="stat-desc" style="color: #64748b;">{cover_sub}</div>
                </div>
                """, unsafe_allow_html=True)

            st.write("")
            st.divider()

            # Action Area - Single ZIP Download Button with Internal Subfolder
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                for output_file in output_files:
                    filename = os.path.basename(output_file)
                    # Masukkan fail ke dalam subfolder mengikut nama base_filename
                    zip_file.write(output_file, arcname=f"{base_filename}/{filename}")

            zip_buffer.seek(0)

            st.download_button(
                "📦 DOWNLOAD SEMUA FAIL (.ZIP 1-KLIK)",
                data=zip_buffer,
                file_name=f"{base_filename}.zip",
                mime="application/zip",
                use_container_width=True,
                type="primary"
            )

            # Individual Download Expander
            with st.expander("📂 Muat turun fail PDF secara berasingan"):
                for output_file in output_files:
                    with open(output_file, "rb") as f:
                        file_data = f.read()

                    filename = os.path.basename(output_file)

                    if filename.endswith("_MY.pdf"):
                        st.download_button(
                            "🇲🇾 Muat turun Bahasa Melayu (.PDF)",
                            data=file_data,
                            file_name=filename,
                            mime="application/pdf",
                            use_container_width=True
                        )
                    elif filename.endswith("_EN.pdf"):
                        st.download_button(
                            "🇬🇧 Muat turun English (.PDF)",
                            data=file_data,
                            file_name=filename,
                            mime="application/pdf",
                            use_container_width=True
                        )

        except Exception as e:
            st.error(f"❌ Gagal memproses PDF: {e}")
