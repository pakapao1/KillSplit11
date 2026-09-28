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
        padding: 4px 10px;
        border-radius: 6px;
        font-family: monospace;
        font-weight: 700;
        font-size: 0.9rem;
        border: 1px solid #bfdbfe;
        display: inline-block;
    }
</style>
""", unsafe_allow_html=True)

# ============================================================
# KEYWORDS
# ============================================================

BM_KEYWORDS = [
    "UNDANG-UNDANG MALAYSIA", "KANUN TANAH NEGARA", "SUSUNAN PERENGGAN",
    "SUSUNAN PERATURAN", "SENARAI PINDAAN", "PERINTAH", "PERATURAN",
    "AKTA", "PADA MENJALANKAN KUASA", "JADUAL", "PERIZABAN TANAH",
    "DIAMBIL PERHATIAN", "PEMBATALAN", "PENGECUALIAN", "MENTERI ",
    "DIBUAT ", "BERTARIKH", "LESEN", "TANAH", "PENUMPANG", "KARGO",
    "KAPAL", " DENGAN ", " OLEH ", "MENURUT", "DISIARKAN OLEH",
    "PENETAPAN", "YANG DIBERI KUASA", "PEGAWAI AWAM",
]

EN_KEYWORDS = [
    "LAWS OF MALAYSIA", "NATIONAL LAND CODE", "ARRANGEMENT OF PARAGRAPHS",
    "ARRANGEMENT OF REGULATIONS", "LIST OF AMENDMENTS", "ORDER",
    "REGULATION", "ACT", "IN EXERCISE OF", "SCHEDULE", "RESERVATION OF LAND",
    "TAKE NOTICE", "REVOCATION", "EXEMPTION", "MINISTER OF", "MADE ",
    "DATED", "LICENCE", "LICENSE", "TONNAGE", "PASSENGER", "CARGO",
    "VESSEL", "SHIP", " WITH ", " BY ", "PURSUANT", "PUBLISHED BY",
    "DESIGNATION", "AUTHORIZED OFFICERS", "PUBLIC OFFICERS",
]


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
#
# Every content page is scored against BM and EN keyword lists.
# A page is labelled:
#   BM      -> mostly Bahasa Melayu
#   EN      -> mostly English
#   BOTH    -> both languages present on the same page (bilingual layout)
#   UNKNOWN -> no keyword matched
#
# When a page contains BOTH languages side-by-side, the old logic could
# not split it cleanly (it would pick one language or drop the page on a
# tie). We now detect that case and treat the WHOLE document as bilingual,
# then simply output the full PDF twice, renamed _BM and _BI.

BILINGUAL_RATIO = 0.5  # min(score)/max(score) at/above this = page has both langs
BILINGUAL_DOC_RATIO = 0.5  # fraction of BOTH pages needed to call the doc bilingual


def classify_page_language(text):
    """Return (label, bm_score, en_score)."""
    text_upper = text.upper()

    bm_score = sum(1 for k in BM_KEYWORDS if k in text_upper)
    en_score = sum(1 for k in EN_KEYWORDS if k in text_upper)

    if bm_score == 0 and en_score == 0:
        return "UNKNOWN", 0, 0

    if bm_score > 0 and en_score > 0:
        hi = max(bm_score, en_score)
        lo = min(bm_score, en_score)
        if lo / hi >= BILINGUAL_RATIO:
            return "BOTH", bm_score, en_score

    if bm_score > en_score:
        return "BM", bm_score, en_score
    if en_score > bm_score:
        return "EN", bm_score, en_score

    return "BOTH", bm_score, en_score

# ============================================================
# PROCESS PDF
# ============================================================

def _write_pdf(pages, output_dir, base_filename, suffix):
    writer = PdfWriter()
    for page in pages:
        writer.add_page(page)
    out_path = os.path.join(output_dir, f"{base_filename}_{suffix}.pdf")
    with open(out_path, "wb") as f:
        writer.write(f)
    return out_path


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

    # A pure cover page is only skipped when it is clearly a stand-alone
    # cover. In many bilingual gazettes the first page already holds real
    # content (BM + EN), so we keep it if it does.
    if is_cover_page and total_pages > 1:
        first_label, _, _ = classify_page_language(
            reader.pages[0].extract_text() or ""
        )
        if first_label != "BOTH":
            cover_page = reader.pages[0]
            start_index = 1

    # Classify every content page.
    page_labels = []
    both_count = 0
    current_lang = None

    for i in range(start_index, total_pages):
        page = reader.pages[i]
        text = page.extract_text() or ""
        label, _, _ = classify_page_language(text)

        if label == "BOTH":
            both_count += 1
        elif label == "UNKNOWN" and current_lang:
            label = current_lang
        elif label in ("BM", "EN"):
            current_lang = label

        page_labels.append((page, label))

    content_pages = [p for p, _ in page_labels]
    n_content = len(content_pages)

    # Decide document mode.
    is_bilingual = (
        n_content > 0
        and (both_count / n_content) >= BILINGUAL_DOC_RATIO
    )

    output_dir = tempfile.mkdtemp()
    output_files = []

    if is_bilingual:
        # Cannot split BM/EN because both languages share the same pages.
        # Just output the full document twice, renamed _BM and _BI.
        mode = "BILINGUAL"
        all_pages = ([cover_page] if cover_page else []) + content_pages

        output_files.append(
            _write_pdf(all_pages, output_dir, base_filename, "BM")
        )
        output_files.append(
            _write_pdf(all_pages, output_dir, base_filename, "BI")
        )

        my_count = len(all_pages)
        en_count = len(all_pages)
    else:
        # Clean split into separate BM and BI PDFs.
        mode = "SPLIT"
        bm_pages = [p for p, lbl in page_labels if lbl == "BM"]
        en_pages = [p for p, lbl in page_labels if lbl == "EN"]

        if bm_pages:
            pages = ([cover_page] if cover_page else []) + bm_pages
            output_files.append(
                _write_pdf(pages, output_dir, base_filename, "BM")
            )

        if en_pages:
            pages = ([cover_page] if cover_page else []) + en_pages
            output_files.append(
                _write_pdf(pages, output_dir, base_filename, "BI")
            )

        my_count = len(bm_pages)
        en_count = len(en_pages)

    os.remove(input_path)

    return (
        base_filename,
        output_files,
        my_count,
        en_count,
        is_cover_page,
        mode
    )

# ============================================================
# USER INTERFACE
# ============================================================

# Hero Banner Header
st.markdown("""
<div class="hero-banner">
    <div style="display: flex; align-items: center; justify-content: space-between;">
        <div class="hero-header-title">⚡ BANG KILL PDF</div>
        <span class="hero-badge">Multi-File Batch</span>
    </div>
    <p class="hero-subtitle">Splitter PDF BM & BI</p>
</div>
""", unsafe_allow_html=True)

# Upload Section Box
with st.container(border=True):
    st.subheader("📁 Muat Naik PDF ")
    uploaded_files = st.file_uploader(
        "Pilih satu atau beberapa fail PDF Warta Kerajaan",
        type=["pdf"],
        accept_multiple_files=True,
        label_visibility="collapsed"
    )

    if uploaded_files:
        st.info(f"📄 **{len(uploaded_files)} fail** sedia diproses.")

        split_btn = st.button(
            f"🚀 ASINGKAN {len(uploaded_files)} FAIL SEKARANG",
            use_container_width=True,
            type="primary"
        )
    else:
        split_btn = False

# Processing Results
if uploaded_files and split_btn:
    with st.spinner(f"⚡ Sedang memproses {len(uploaded_files)} fail PDF..."):
        all_results = []
        zip_buffer = io.BytesIO()

        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            total_bm_pages = 0
            total_en_pages = 0

            for uploaded_file in uploaded_files:
                try:
                    (
                        base_filename,
                        output_files,
                        my_count,
                        en_count,
                        cover_found,
                        mode
                    ) = process_gazette_pdf(
                        uploaded_file.getvalue(),
                        uploaded_file.name
                    )

                    total_bm_pages += my_count
                    total_en_pages += en_count

                    for output_file in output_files:
                        filename = os.path.basename(output_file)
                        zip_file.write(
                            output_file,
                            arcname=f"{base_filename}/{filename}"
                        )

                    all_results.append({
                        "status": "success",
                        "filename": uploaded_file.name,
                        "gazette_id": base_filename,
                        "my_count": my_count,
                        "en_count": en_count,
                        "cover_found": cover_found,
                        "mode": mode,
                        "output_files": output_files
                    })
                except Exception as e:
                    all_results.append({
                        "status": "error",
                        "filename": uploaded_file.name,
                        "error": str(e)
                    })

        zip_buffer.seek(0)

        st.success(f"✅ **Berjaya memproses {len(all_results)} fail!**")

        st.markdown("### 📊 Ringkasan Keseluruhan")

        col1, col2, col3 = st.columns(3)

        with col1:
            st.markdown(f"""
            <div class="stat-card">
                <div class="stat-label">📁 Jumlah Fail</div>
                <div class="stat-value">{len(uploaded_files)}</div>
                <div class="stat-desc">Diproses</div>
            </div>
            """, unsafe_allow_html=True)

        with col2:
            st.markdown(f"""
            <div class="stat-card">
                <div class="stat-label">🇲🇾 Total BM</div>
                <div class="stat-value">{total_bm_pages}</div>
                <div class="stat-desc">Muka Surat</div>
            </div>
            """, unsafe_allow_html=True)

        with col3:
            st.markdown(f"""
            <div class="stat-card">
                <div class="stat-label">🇬🇧 Total BI</div>
                <div class="stat-value">{total_en_pages}</div>
                <div class="stat-desc">Muka Surat</div>
            </div>
            """, unsafe_allow_html=True)

        st.write("")
        st.divider()

        zip_filename = (
            f"{all_results[0]['gazette_id']}.zip"
            if len(all_results) == 1 and all_results[0]['status'] == 'success'
            else "BANG_KILL_PDF_BATCH.zip"
        )

        st.download_button(
            "📦 DOWNLOAD SEMUA FAIL (.ZIP 1-KLIK)",
            data=zip_buffer,
            file_name=zip_filename,
            mime="application/zip",
            use_container_width=True,
            type="primary"
        )

        with st.expander("📂 Lihat butiran setiap fail yang diproses"):
            for res in all_results:
                if res["status"] == "success":
                    st.markdown(
                        f"🔹 **{res['filename']}** $\\rightarrow$ ID Gazette: "
                        f"<span class='gazette-tag'>{res['gazette_id']}</span>",
                        unsafe_allow_html=True
                    )
                    if res.get("mode") == "BILINGUAL":
                        st.caption(
                            f"🔀 Dwibahasa (BM & BI dalam satu muka surat) → "
                            f"fail penuh disalin sebagai _BM & _BI "
                            f"({res['my_count']} muka surat setiap satu)"
                        )
                    else:
                        st.caption(
                            f"🇲🇾 BM: {res['my_count']} muka surat | "
                            f"🇬🇧 BI: {res['en_count']} muka surat | "
                            f"Cover: {'Dikesan' if res['cover_found'] else 'Tiada'}"
                        )
                else:
                    st.error(f"❌ **{res['filename']}**: {res['error']}")
                st.divider()
