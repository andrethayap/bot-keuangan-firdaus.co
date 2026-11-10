import os
import sqlite3
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

TOKEN = os.environ.get("TELEGRAM_TOKEN")

# Inisialisasi Database
conn = sqlite3.connect('pengeluaran.db', check_same_thread=False)
conn.row_factory = sqlite3.Row 

# Tabel Keluarga
conn.execute('''CREATE TABLE IF NOT EXISTS keluarga
    (user_id INTEGER PRIMARY KEY, family_id INTEGER)''')

# Tabel Transaksi (Sekarang ada kolom 'tipe' untuk Pengeluaran/Pemasukan)
conn.execute('''CREATE TABLE IF NOT EXISTS transaksi
    (id INTEGER PRIMARY KEY AUTOINCREMENT, family_id INTEGER, tanggal TEXT,
     tipe TEXT, kategori TEXT, jumlah INTEGER, keterangan TEXT)''')
conn.commit()

user_state = {}

def get_family_id(user_id):
    cur = conn.execute("SELECT family_id FROM keluarga WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    if row:
        return row['family_id']
    conn.execute("INSERT INTO keluarga VALUES (?, ?)", (user_id, user_id))
    conn.commit()
    return user_id

# ================= FITUR START & LINK =================
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    get_family_id(update.effective_user.id)
    await update.message.reply_text(
        "👋 Hai! Aku bot keuangan keluarga.\n\n"
        "📝 *Catat Transaksi:*\n"
        "/catat - Catat Pengeluaran\n"
        "/masuk - Catat Pemasukan\n\n"
        "📊 *Laporan:*\n"
        "/harian - Laporan hari ini\n"
        "/mingguan - Laporan minggu ini (Mulai Senin)\n"
        "/bulanan - Laporan bulan ini\n\n"
        "🗑 /hapus - Hapus catatan terakhir\n"
        "💑 /link - Gabungkan laporan suami & istri",
        parse_mode='Markdown'
    )

async def link_keluarga(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    args = ctx.args
    if len(args) != 2:
        await update.message.reply_text("Format: /link <ID_Kamu> <ID_Pasangan>")
        return
    try:
        id1, id2 = int(args[0]), int(args[1])
        fam_id = min(id1, id2)
        conn.execute("INSERT OR REPLACE INTO keluarga VALUES (?, ?)", (id1, fam_id))
        conn.execute("INSERT OR REPLACE INTO keluarga VALUES (?, ?)", (id2, fam_id))
        conn.commit()
        await update.message.reply_text("✅ Berhasil! Laporan kalian berdua sekarang tergabung.")
    except ValueError:
        await update.message.reply_text("❌ ID harus berupa angka.")

# ================= FITUR CATAT (PENGELUARAN & PEMASUKAN) =================
async def catat_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE, tipe="pengeluaran"):
    if tipe == "pengeluaran":
        keyboard = [
            [InlineKeyboardButton("🍔 Makan", callback_data='kat_makan'), 
             InlineKeyboardButton("🚗 Transport", callback_data='kat_transport')],
            [InlineKeyboardButton("🛒 Belanja", callback_data='kat_belanja'), 
             InlineKeyboardButton("🧾 Tagihan", callback_data='kat_tagihan')],
            [InlineKeyboardButton("🎉 Hiburan", callback_data='kat_hiburan'),
             InlineKeyboardButton("📦 Lainnya", callback_data='kat_lainnya')]
        ]
        await update.message.reply_text("Pilih kategori *Pengeluaran*:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    else:
        keyboard = [
            [InlineKeyboardButton("💰 Gaji", callback_data='kat_gaji'),
             InlineKeyboardButton("🎁 Bonus", callback_data='kat_bonus')],
            [InlineKeyboardButton("📈 Usaha", callback_data='kat_usaha'),
             InlineKeyboardButton("💸 Lainnya", callback_data='kat_lainnya')]
        ]
        await update.message.reply_text("Pilih kategori *Pemasukan*:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def masuk_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await catat_start(update, ctx, tipe="pemasukan")

async def button_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith('kat_'):
        kategori = query.data.replace('kat_', '').capitalize()
        user_id = query.from_user.id
        
        # Cek apakah ini dari menu pemasukan atau pengeluaran
        # (Gaji, Bonus, Usaha dianggap pemasukan. Sisanya pengeluaran)
        tipe = "pemasukan" if kategori in ["Gaji", "Bonus", "Usaha"] else "pengeluaran"
        
        user_state[user_id] = {'kategori': kategori, 'tipe': tipe}
        
        await query.edit_message_text(
            text=f"Kategori: *{kategori}* ({tipe.capitalize()})\n\nSekarang ketik nominal dan keterangannya.\nContoh: `25000 Bakso Pak Kumis`",
            parse_mode='Markdown'
        )

async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    
    if user_id in user_state and 'kategori' in user_state[user_id]:
        parts = text.split(" ", 1)
        try:
            jumlah = int(parts[0])
            ket = parts[1] if len(parts) > 1 else "-"
            kategori = user_state[user_id]['kategori']
            tipe = user_state[user_id]['tipe']
            fam_id = get_family_id(user_id)
            
            conn.execute("INSERT INTO transaksi (family_id, tanggal, tipe, kategori, jumlah, keterangan) VALUES (?,?,?,?,?,?)",
                (fam_id, datetime.now().isoformat(), tipe, kategori, jumlah, ket))
            conn.commit()
            
            del user_state[user_id]
            emoji = "✅" if tipe == "pemasukan" else "💸"
            await update.message.reply_text(f"{emoji} Tercatat {tipe}: Rp{jumlah:,} - {kategori} ({ket})")
        except (ValueError, IndexError):
            await update.message.reply_text("❌ Format salah. Ketik angka dulu, lalu keterangan.\nContoh: `25000 Bakso`", parse_mode='Markdown')
    else:
        await update.message.reply_text("Ketik /catat atau /masuk untuk mulai mencatat.")

# ================= FITUR HAPUS =================
async def hapus_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    fam_id = get_family_id(update.effective_user.id)
    cur = conn.execute("SELECT id, tipe, kategori, jumlah, keterangan FROM transaksi WHERE family_id=? ORDER BY id DESC LIMIT 5", (fam_id,))
    rows = cur.fetchall()
    
    if not rows:
        await update.message.reply_text("Belum ada data untuk dihapus.")
        return

    keyboard = []
    for row in rows:
        tipe_emoji = "💰" if row['tipe'] == "pemasukan" else "💸"
        btn_text = f"❌ {tipe_emoji} {row['kategori']}: Rp{row['jumlah']:,}"
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"del_{row['id']}")])
    
    await update.message.reply_text("Pilih catatan yang ingin dihapus:", reply_markup=InlineKeyboardMarkup(keyboard))

async def hapus_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith('del_'):
        row_id = int(query.data.replace('del_', ''))
        conn.execute("DELETE FROM transaksi WHERE id=?", (row_id,))
        conn.commit()
        await query.edit_message_text("✅ Catatan berhasil dihapus.")

# ================= FITUR LAPORAN (HARIAN, MINGGUAN, BULANAN) =================
def generate_laporan(fam_id, periode, judul):
    # Query untuk pengeluaran
    query_keluar = """SELECT kategori, SUM(jumlah) as total FROM transaksi 
                      WHERE family_id=? AND tipe='pengeluaran' AND {cond} GROUP BY kategori"""
    # Query untuk pemasukan
    query_masuk = """SELECT kategori, SUM(jumlah) as total FROM transaksi 
                     WHERE family_id=? AND tipe='pemasukan' AND {cond} GROUP BY kategori"""

    if periode == "harian":
        cond = "date(tanggal) = date('now', 'localtime')"
    elif periode == "mingguan":
        # 'weekday 0' akan mundur ke hari Minggu terakhir, lalu -6 hari = Senin
        # 'localtime' memastikan menggunakan waktu Indonesia, bukan UTC
        cond = "date(tanggal) >= date('now', 'localtime', 'weekday 0', '-6 days')"
    else: # bulanan
        cond = "strftime('%Y-%m', tanggal) = strftime('%Y-%m', 'now', 'localtime')"

    cur_masuk = conn.execute(query_masuk.format(cond=cond), (fam_id,))
    rows_masuk = cur_masuk.fetchall()
    
    cur_keluar = conn.execute(query_keluar.format(cond=cond), (fam_id,))
    rows_keluar = cur_keluar.fetchall()

    if not rows_masuk and not rows_keluar:
        return f"Belum ada catatan untuk {judul.lower()}."

    total_masuk = sum(r['total'] for r in rows_masuk) if rows_masuk else 0
    total_keluar = sum(r['total'] for r in rows_keluar) if rows_keluar else 0
    saldo = total_masuk - total_keluar

    msg = f"📊 *Laporan {judul}*\n\n"
    
    if rows_masuk:
        msg += "💰 *Pemasukan:*\n"
        for r in rows_masuk:
            msg += f"  + {r['kategori']}: Rp{r['total']:,}\n"
        msg += f"  *Total Masuk: Rp{total_masuk:,}*\n\n"

    if rows_keluar:
        msg += "💸 *Pengeluaran:*\n"
        for r in rows_keluar:
            msg += f"  - {r['kategori']}: Rp{r['total']:,}\n"
        msg += f"  *Total Keluar: Rp{total_keluar:,}*\n\n"

    msg += f"⚖️ *Saldo Bersih: Rp{saldo:,}*"
    return msg

async def laporan_harian(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    fam_id = get_family_id(update.effective_user.id)
    msg = generate_laporan(fam_id, "harian", "Hari Ini")
    await update.message.reply_text(msg, parse_mode='Markdown')

async def laporan_mingguan(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    fam_id = get_family_id(update.effective_user.id)
    msg = generate_laporan(fam_id, "mingguan", "Minggu Ini")
    await update.message.reply_text(msg, parse_mode='Markdown')

async def laporan_bulanan(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    fam_id = get_family_id(update.effective_user.id)
    msg = generate_laporan(fam_id, "bulanan", "Bulan Ini")
    await update.message.reply_text(msg, parse_mode='Markdown')

# ================= MAIN =================
def main():
    if not TOKEN:
        raise ValueError("TELEGRAM_TOKEN belum diset!")
    
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("link", link_keluarga))
    app.add_handler(CommandHandler("catat", catat_start))
    app.add_handler(CommandHandler("masuk", masuk_start))
    app.add_handler(CommandHandler("hapus", hapus_start))
    
    # Laporan
    app.add_handler(CommandHandler("harian", laporan_harian))
    app.add_handler(CommandHandler("mingguan", laporan_mingguan))
    app.add_handler(CommandHandler("bulanan", laporan_bulanan))
    
    app.add_handler(CallbackQueryHandler(button_handler, pattern="^kat_"))
    app.add_handler(CallbackQueryHandler(hapus_handler, pattern="^del_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    # Menu otomatis
    async def post_init(application: Application) -> None:
        await application.bot.set_my_commands([
            BotCommand("start", "Buka menu utama"),
            BotCommand("catat", "Catat pengeluaran"),
            BotCommand("masuk", "Catat pemasukan"),
            BotCommand("harian", "Laporan hari ini"),
            BotCommand("mingguan", "Laporan minggu ini (Senin)"),
            BotCommand("bulanan", "Laporan bulan ini"),
            BotCommand("hapus", "Hapus catatan terakhir"),
            BotCommand("link", "Gabungkan laporan keluarga")
        ])
    
    app.post_init = post_init

    print("Bot starting...")
    app.run_polling()

if __name__ == "__main__":
    main()
