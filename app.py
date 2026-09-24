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
    page_title="BANG KILL PDF",
    page_icon="📄",
    layout="centered"
)


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
        "UNDANG-UNDANG MALAYSIA",
        "KANUN TANAH NEGARA",
        "SUSUNAN PERENGGAN",
        "SUSUNAN PERATURAN",
        "SENARAI PINDAAN",
        "PERINTAH",
        "PERATURAN",
        "AKTA",
        "PADA MENJALANKAN KUASA",
        "JADUAL",
        "PERIZABAN TANAH",
        "DIAMBIL PERHATIAN",
        "PEMBATALAN",
        "PENGECUALIAN",
        "MENTERI ",
        "DIBUAT ",
        "BERTARIKH",
        "LESEN",
        "TANAN",
        "PENUMPANG",
        "KARGO",
        "KAPAL",
        " DENGAN ",
        " OLEH ",
    ]

    en_keywords = [
        "LAWS OF MALAYSIA",
        "NATIONAL LAND CODE",
        "ARRANGEMENT OF PARAGRAPHS",
        "ARRANGEMENT OF REGULATIONS",
        "LIST OF AMENDMENTS",
        "ORDER",
        "REGULATION",
        "ACT",
        "IN EXERCISE OF",
        "SCHEDULE",
        "RESERVATION OF LAND",
        "TAKE NOTICE",
        "REVOCATION",
        "EXEMPTION",
        "MINISTER OF",
        "MADE ",
        "DATED",
        "LICENCE",
        "LICENSE",
        "TONNAGE",
        "PASSENGER",
        "CARGO",
        "VESSEL",
        "SHIP",
        " WITH ",
        " BY ",
    ]

    bm_score = sum(
        1 for k in bm_keywords
        if k in text_upper
    )

    en_score = sum(
        1 for k in en_keywords
        if k in text_upper
    )

    if bm_score > en_score:
        return "BM"

    elif en_score > bm_score:
        return "EN"

    return "UNKNOWN"


# ============================================================
# PROCESS PDF
# ============================================================

def process_gazette_pdf(file_bytes, original_filename):

    with tempfile.NamedTemporaryFile(
        delete=False,
        suffix=".pdf"
    ) as temp_file:

        temp_file.write(file_bytes)
        input_path = temp_file.name

    reader = PdfReader(input_path)

    total_pages = len(reader.pages)

    if total_pages == 0:
        os.remove(input_path)
        raise ValueError("PDF tidak mempunyai muka surat.")

    # --------------------------------------------------------
    # READ FULL TEXT
    # --------------------------------------------------------

    full_text = ""

    for page in reader.pages:
        full_text += page.extract_text() or ""

    base_filename = extract_gazette_metadata(
        full_text,
        original_filename
    )

    # --------------------------------------------------------
    # CHECK COVER PAGE
    # --------------------------------------------------------

    first_page_text = (
        reader.pages[0].extract_text() or ""
    ).upper()

    is_cover_page = (
        "WARTA KERAJAAN" in first_page_text
        or
        "GAZETTE" in first_page_text
    )

    cover_page = None
    start_index = 0

    if is_cover_page and total_pages > 1:

        cover_page = reader.pages[0]
        start_index = 1

    # --------------------------------------------------------
    # PAGE COLLECTION
    # --------------------------------------------------------

    my_pages = []
    en_pages = []

    current_detected_lang = None

    for i in range(start_index, total_pages):

        page = reader.pages[i]

        text = page.extract_text() or ""

        lang = detect_page_language(text)

        # Fallback to previous language
        if lang == "UNKNOWN" and current_detected_lang:

            lang = current_detected_lang

        elif lang != "UNKNOWN":

            current_detected_lang = lang

        if lang == "BM":

            my_pages.append(page)

        elif lang == "EN":

            en_pages.append(page)

    # --------------------------------------------------------
    # CREATE OUTPUT DIRECTORY
    # --------------------------------------------------------

    output_dir = tempfile.mkdtemp()

    output_files = []

    # --------------------------------------------------------
    # MALAY PDF
    # --------------------------------------------------------

    if my_pages:

        writer_my = PdfWriter()

        if cover_page:
            writer_my.add_page(cover_page)

        for page in my_pages:
            writer_my.add_page(page)

        output_my = os.path.join(
            output_dir,
            f"{base_filename}_MY.pdf"
        )

        with open(output_my, "wb") as f:
            writer_my.write(f)

        output_files.append(output_my)

    # --------------------------------------------------------
    # ENGLISH PDF
    # --------------------------------------------------------

    if en_pages:

        writer_en = PdfWriter()

        if cover_page:
            writer_en.add_page(cover_page)

        for page in en_pages:
            writer_en.add_page(page)

        output_en = os.path.join(
            output_dir,
            f"{base_filename}_EN.pdf"
        )

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

st.title("📄 BANG KILL PDF")

st.write(
    "Upload PDF Warta Kerajaan untuk mengasingkan "
    "muka surat Bahasa Melayu dan Bahasa Inggeris."
)

st.divider()

uploaded_file = st.file_uploader(
    "📁 Pilih PDF Warta",
    type=["pdf"]
)

if uploaded_file:

    st.success(
        f"File dipilih: **{uploaded_file.name}**"
    )

    if st.button(
        "🚀 SPLIT PDF",
        use_container_width=True
    ):

        with st.spinner(
            "Sedang membaca dan mengasingkan PDF..."
        ):

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

                st.success(
                    "✅ PDF berjaya diproses!"
                )

                st.write(
                    f"**Gazette:** `{base_filename}`"
                )

                if cover_found:

                    st.info(
                        "Cover page dikesan dan dimasukkan "
                        "ke dalam kedua-dua PDF."
                    )

                st.write(
                    f"🇲🇾 Bahasa Melayu: **{my_count} muka surat**"
                )

                st.write(
                    f"🇬🇧 English: **{en_count} muka surat**"
                )

                st.divider()

                # ------------------------------------------------
                # 1-KLIK ZIP DOWNLOAD BUTTON
                # ------------------------------------------------

                zip_buffer = io.BytesIO()

                with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                    for output_file in output_files:
                        filename = os.path.basename(output_file)
                        zip_file.write(output_file, arcname=filename)

                zip_buffer.seek(0)

                st.download_button(
                    "📦 Download Semua Fail (.ZIP 1-Klik)",
                    data=zip_buffer,
                    file_name=f"{base_filename}_SPLIT.zip",
                    mime="application/zip",
                    use_container_width=True,
                    type="primary"
                )

                # Option berasingan jika masih perlukan muat turun individu
                with st.expander("📄 Download Fail PDF Berasingan"):
                    for output_file in output_files:
                        with open(output_file, "rb") as f:
                            file_data = f.read()

                        filename = os.path.basename(output_file)

                        if filename.endswith("_MY.pdf"):
                            st.download_button(
                                "🇲🇾 Download Bahasa Melayu sahaja",
                                data=file_data,
                                file_name=filename,
                                mime="application/pdf",
                                use_container_width=True
                            )
                        elif filename.endswith("_EN.pdf"):
                            st.download_button(
                                "🇬🇧 Download English sahaja",
                                data=file_data,
                                file_name=filename,
                                mime="application/pdf",
                                use_container_width=True
                            )

            except Exception as e:

                st.error(
                    f"❌ Gagal memproses PDF: {e}"
                )
