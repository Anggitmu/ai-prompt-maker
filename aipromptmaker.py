import streamlit as st
import tempfile
import os
import time
import json
from google import genai
from google.genai import types
from pydantic import BaseModel
from supabase import create_client, Client

# --- KONFIGURASI HALAMAN & API ---
st.set_page_config(page_title="AI Media to Prompt Pro", page_icon="🎬", layout="centered")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

ai_client = genai.Client(api_key=GEMINI_API_KEY)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

class PromptStructure(BaseModel):
    subject: str
    action_or_motion: str
    environment: str
    camera_and_composition: str
    lighting_and_color: str
    art_style_and_technical: str
    final_prompt_en: str

def cek_lisensi(kode):
    response = supabase.table("licenses").select("*").eq("code", kode.strip()).execute()
    if len(response.data) > 0:
        return response.data[0]
    return None

def kurangi_kredit(kode, sisa_sekarang):
    kredit_baru = max(0, sisa_sekarang - 1)
    supabase.table("licenses").update({"credits": kredit_baru}).eq("code", kode.strip()).execute()
    return kredit_baru

st.title("🎬 AI Video & Image to Prompt Pro")

with st.container(border=True):
    st.subheader("🔑 Akses Member")
    kode_input = st.text_input("Masukkan Kode Lisensi Anda:", placeholder="Contoh: VIP-2026-01")
    
    if not kode_input:
        st.info("Silakan masukkan kode akses yang Anda dapatkan setelah pembelian.")
        st.stop()

    data_user = cek_lisensi(kode_input)

    if data_user is None:
        st.error("❌ Kode lisensi tidak ditemukan atau salah.")
        st.stop()
    
    sisa_kredit = data_user["credits"]
    nama_pembeli = data_user.get("buyer_name", "Member")

    if sisa_kredit <= 0:
        st.warning(f"⚠️ Halo {nama_pembeli}, kuota generate Anda sudah habis (0 kredit).")
        st.stop()

    st.success(f"✅ Selamat datang, **{nama_pembeli}**! Sisa Kuota: **{sisa_kredit} Generate**")

col1, col2 = st.columns(2)
with col1:
    target_ai = st.selectbox(
        "Target AI Generator",
        ["Midjourney v6 (Foto)", "FLUX.1 (Foto)", "Kling AI (Video)", "Google Veo (Video)", "Runway Gen-3 (Video)"]
    )
with col2:
    preset_gaya = st.selectbox(
        "Preset Khusus",
        ["Standar / Akurat", "Iklan Produk Komersial", "Konten Affiliate TikTok", "Sinematik Film 35mm", "Animasi 3D Pixar Style"]
    )

uploaded_file = st.file_uploader("Unggah Foto (JPG/PNG) atau Video (MP4/MOV)", type=["jpg", "jpeg", "png", "webp", "mp4", "mov"])

if uploaded_file is not None:
    file_ext = uploaded_file.name.split(".")[-1].lower()
    if file_ext in ["mp4", "mov"]:
        st.video(uploaded_file)
    else:
        st.image(uploaded_file, use_container_width=True)

    if st.button("✨ Generate Prompt Sekarang (1 Kredit)", type="primary", use_container_width=True):
        with st.spinner("Sedang menganalisis media dan menyusun prompt..."):
            tmp_path = None
            gemini_file = None
            try:
                instruksi = f"""
                Anda adalah AI Prompt Engineer tingkat lanjut. Analisis media ini secara mendalam.
                Optimalkan hasil prompt untuk platform: {target_ai}.
                Terapkan nuansa/preset: {preset_gaya}.
                Isi setiap bagian struktur dengan detail tajam, dan gabungkan semuanya menjadi satu paragraf 
                bahasa Inggris yang padat dan deskriptif pada bagian 'final_prompt_en'.
                """

                # Jika FOTO, kirim langsung (Super Cepat 3-5 detik)
                if file_ext in ["jpg", "jpeg", "png", "webp"]:
                    media_input = types.Part.from_bytes(
                        data=uploaded_file.getvalue(),
                        mime_type=uploaded_file.type,
                    )
                # Jika VIDEO, unggah via File API
                else:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=f".{file_ext}") as tmp_file:
                        tmp_file.write(uploaded_file.getvalue())
                        tmp_path = tmp_file.name

                    gemini_file = ai_client.files.upload(file=tmp_path)
                    while gemini_file.state.name == "PROCESSING":
                        time.sleep(2)
                        gemini_file = ai_client.files.get(name=gemini_file.name)
                    media_input = gemini_file

                # Daftar model berurutan (Jika model 1 sibuk, otomatis pindah ke model cadangan)
                daftar_model = ["gemini-3.8-flash", "gemini-3.8-flash-lite", "gemini-3.8-flash"]
                response = None
                error_terakhir = None

                for nama_model in daftar_model:
                    try:
                        response = ai_client.models.generate_content(
                            model=nama_model,
                            contents=[media_input, instruksi],
                            config=types.GenerateContentConfig(
                                response_mime_type="application/json",
                                response_schema=PromptStructure,
                                temperature=0.4,
                            ),
                        )
                        break # Berhasil, langsung keluar
                    except Exception as err:
                        error_terakhir = err
                        continue # Coba model berikutnya

                if response is None:
                    raise error_terakhir

                # Bersihkan file sementara jika tadi mengunggah video
                if gemini_file:
                    ai_client.files.delete(name=gemini_file.name)
                if tmp_path and os.path.exists(tmp_path):
                    os.remove(tmp_path)

                sisa_terbaru = kurangi_kredit(kode_input, sisa_kredit)
                hasil = json.loads(response.text)

                st.success(f"Berhasil! Sisa kuota Anda sekarang: {sisa_terbaru} Generate.")
                st.subheader("📋 Final Prompt (Siap Copy-Paste)")
                st.code(hasil["final_prompt_en"], language="text")

                st.subheader("🔍 Rincian Struktur")
                st.markdown(f"**1. Subjek Utama:** {hasil['subject']}")
                st.markdown(f"**2. Aksi & Gerakan:** {hasil['action_or_motion']}")
                st.markdown(f"**3. Latar & Suasana:** {hasil['environment']}")
                st.markdown(f"**4. Kamera & Komposisi:** {hasil['camera_and_composition']}")
                st.markdown(f"**5. Pencahayaan & Warna:** {hasil['lighting_and_color']}")
                st.markdown(f"**6. Gaya Visual & Teknis:** {hasil['art_style_and_technical']}")

            except Exception as e:
                st.error(f"Terjadi kesalahan: {e}")
                if tmp_path and os.path.exists(tmp_path):
                    os.remove(tmp_path)