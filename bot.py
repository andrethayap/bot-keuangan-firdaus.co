import os
import sqlite3
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

TOKEN = os.environ.get("TELEGRAM_TOKEN")

# Inisialisasi Database
conn = sqlite3.connect('pengeluaran.db', check_same_thread=False)
conn.row_factory = sqlite3.Row 

# Tabel Keluarga untuk menyatukan ID suami-istri
conn.execute('''CREATE TABLE IF NOT EXISTS keluarga
    (user_id INTEGER PRIMARY KEY, family_id INTEGER)''')

# Tabel Pengeluaran
conn.execute('''CREATE TABLE IF NOT EXISTS pengeluaran
    (id INTEGER PRIMARY KEY AUTOINCREMENT, family_id INTEGER, tanggal TEXT,
     kategori TEXT, jumlah INTEGER, keterangan TEXT)''')
conn.commit()

# State sementara untuk menyimpan input sebelum disave
user_state = {}

def get_family_id(user_id):
    cur = conn.execute("SELECT family_id FROM keluarga WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    if row:
        return row['family_id']
    # Kalau belum terdaftar, jadikan dia ID keluarga utama
    conn.execute("INSERT INTO keluarga VALUES (?, ?)", (user_id, user_id))
    conn.commit()
    return user_id

# ================= FITUR START & LINK =================
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    get_family_id(update.effective_user.id)
    await update.message.reply_text(
        "👋 Hai! Aku bot pencatat pengeluaran keluarga.\n\n"
        "Perintah:\n"
        "📝 /catat - Catat pengeluaran (via tombol)\n"
        "📊 /laporan - Lihat rekap bulan ini\n"
        "🗑 /hapus - Hapus catatan terakhir\n\n"
        "💑 *Fitur Pasangan:*\n"
        "Kirim `/link <ID> <ID>` untuk menggabungkan laporan.\n"
        "Contoh: `/link 123456 789012`\n"
        "*(ID bisa dilihat di profil Telegram masing-masing)*",
        parse_mode='Markdown'
    )

async def link_keluarga(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    args = ctx.args
    if len(args) != 2:
        await update.message.reply_text("Format: /link <ID_Kamu> <ID_Pasangan>\nContoh: /link 123456789 987654321")
        return
    try:
        id1, id2 = int(args[0]), int(args[1])
        # Set keduanya ke family_id yang sama (pakai ID yang lebih kecil)
        fam_id = min(id1, id2)
        conn.execute("INSERT OR REPLACE INTO keluarga VALUES (?, ?)", (id1, fam_id))
        conn.execute("INSERT OR REPLACE INTO keluarga VALUES (?, ?)", (id2, fam_id))
        conn.commit()
        await update.message.reply_text("✅ Berhasil! Sekarang laporan pengeluaran kalian berdua akan tergabung.")
    except ValueError:
        await update.message.reply_text("❌ ID harus berupa angka.")

# ================= FITUR CATAT (TOMBOL) =================
async def catat_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🍔 Makan", callback_data='kat_makan'), 
         InlineKeyboardButton("🚗 Transport", callback_data='kat_transport')],
        [InlineKeyboardButton("🛒 Belanja", callback_data='kat_belanja'), 
         InlineKeyboardButton("🧾 Tagihan", callback_data='kat_tagihan')],
        [InlineKeyboardButton("🎉 Hiburan", callback_data='kat_hiburan'),
         InlineKeyboardButton("📦 Lainnya", callback_data='kat_lainnya')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Pilih kategori pengeluaran:", reply_markup=reply_markup)

async def button_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith('kat_'):
        kategori = query.data.replace('kat_', '').capitalize()
        user_id = query.from_user.id
        
        # Simpan state
        user_state[user_id] = {'kategori': kategori}
        
        # Hapus pesan tombol lama, ganti dengan instruksi
        await query.edit_message_text(
            text=f"Kategori dipilih: *{kategori}*\n\nSekarang ketik nominal dan keterangannya.\nContoh: `25000 Bakso Pak Kumis`",
            parse_mode='Markdown'
        )

# Menangkap input teks setelah user klik tombol
async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    
    # Kalau user sedang dalam proses input nominal
    if user_id in user_state and 'kategori' in user_state[user_id]:
        parts = text.split(" ", 1)
        try:
            jumlah = int(parts[0])
            ket = parts[1] if len(parts) > 1 else "-"
            kategori = user_state[user_id]['kategori']
            fam_id = get_family_id(user_id)
            
            conn.execute("INSERT INTO pengeluaran (family_id, tanggal, kategori, jumlah, keterangan) VALUES (?,?,?,?,?)",
                (fam_id, datetime.now().isoformat(), kategori, jumlah, ket))
            conn.commit()
            
            # Bersihkan state
            del user_state[user_id]
            
            await update.message.reply_text(f"✅ Tercatat: Rp{jumlah:,} - {kategori} ({ket})")
        except (ValueError, IndexError):
            await update.message.reply_text("❌ Format salah. Ketik angka dulu, lalu keterangan.\nContoh: `25000 Bakso`", parse_mode='Markdown')
    else:
        await update.message.reply_text("Ketik /catat untuk mulai mencatat, atau /laporan untuk melihat rekap.")

# ================= FITUR HAPUS =================
async def hapus_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    fam_id = get_family_id(update.effective_user.id)
    cur = conn.execute("SELECT id, kategori, jumlah, keterangan FROM pengeluaran WHERE family_id=? ORDER BY id DESC LIMIT 5", (fam_id,))
    rows = cur.fetchall()
    
    if not rows:
        await update.message.reply_text("Belum ada data pengeluaran untuk dihapus.")
        return

    keyboard = []
    for row in rows:
        btn_text = f"❌ {row['kategori']}: Rp{row['jumlah']:,} ({row['keterangan']})"
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"del_{row['id']}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Pilih catatan yang ingin dihapus:", reply_markup=reply_markup)

async def hapus_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith('del_'):
        row_id = int(query.data.replace('del_', ''))
        conn.execute("DELETE FROM pengeluaran WHERE id=?", (row_id,))
        conn.commit()
        await query.edit_message_text("✅ Catatan berhasil dihapus.")

# ================= FITUR LAPORAN =================
async def laporan(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    fam_id = get_family_id(update.effective_user.id)
    
    cur = conn.execute("""SELECT kategori, SUM(jumlah) as total FROM pengeluaran
        WHERE family_id=? AND strftime('%Y-%m', tanggal)=strftime('%Y-%m','now')
        GROUP BY kategori""", (fam_id,))
    rows = cur.fetchall()
    
    if not rows:
        await update.message.reply_text("Belum ada pengeluaran bulan ini.")
        return
        
    total_all = sum(r['total'] for r in rows)
    msg = "📊 *Laporan Bulan Ini (Keluarga)*\n\n"
    for r in rows:
        msg += f"• {r['kategori']}: Rp{r['total']:,}\n"
    msg += f"\n*Total: Rp{total_all:,}*"
    await update.message.reply_text(msg, parse_mode='Markdown')

# ================= MAIN =================
def main():
    if not TOKEN:
        raise ValueError("TELEGRAM_TOKEN belum diset!")
    
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("link", link_keluarga))
    app.add_handler(CommandHandler("catat", catat_start))
    app.add_handler(CommandHandler("keluar", catat_start)) # alias
    app.add_handler(CommandHandler("hapus", hapus_start))
    app.add_handler(CommandHandler("laporan", laporan))
    
    # Handler untuk tombol
    app.add_handler(CallbackQueryHandler(button_handler, pattern="^kat_"))
    app.add_handler(CallbackQueryHandler(hapus_handler, pattern="^del_"))
    
    # Handler untuk teks biasa (input nominal)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    print("Bot starting...")
    app.run_polling()

if __name__ == "__main__":
    main()
