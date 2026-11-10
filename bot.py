import os
import sqlite3
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

TOKEN = os.environ.get("TELEGRAM_TOKEN")  # Dibaca dari Railway Variables

# Init database
conn = sqlite3.connect('pengeluaran.db', check_same_thread=False)
conn.execute('''CREATE TABLE IF NOT EXISTS pengeluaran
    (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, tanggal TEXT,
     kategori TEXT, jumlah INTEGER, keterangan TEXT)''')
conn.commit()

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Hai! Aku bot pencatat pengeluaran.\n\n"
        "Perintah:\n"
        "/keluar <jumlah> <kategori> <keterangan>\n"
        "Contoh: /keluar 50000 makan nasi goreng\n\n"
        "/laporan - lihat rekap bulan ini"
    )

async def catat(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    args = ctx.args
    if len(args) < 2:
        await update.message.reply_text("Format: /keluar <jumlah> <kategori> <keterangan>\nContoh: /keluar 50000 makan nasi goreng")
        return
    try:
        jumlah = int(args[0])
    except ValueError:
        await update.message.reply_text("❌ Jumlah harus angka. Contoh: /keluar 50000 makan nasi goreng")
        return
    kategori = args[1]
    ket = " ".join(args[2:]) if len(args) > 2 else "-"
    conn.execute("INSERT INTO pengeluaran (user_id, tanggal, kategori, jumlah, keterangan) VALUES (?,?,?,?,?)",
        (update.effective_user.id, datetime.now().isoformat(), kategori, jumlah, ket))
    conn.commit()
    await update.message.reply_text(f"✅ Tercatat: Rp{jumlah:,} - {kategori} ({ket})")

async def laporan(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cur = conn.execute("""SELECT kategori, SUM(jumlah) FROM pengeluaran
        WHERE user_id=? AND strftime('%Y-%m', tanggal)=strftime('%Y-%m','now')
        GROUP BY kategori""", (update.effective_user.id,))
    rows = cur.fetchall()
    if not rows:
        await update.message.reply_text("Belum ada pengeluaran bulan ini.")
        return
    total = sum(r[1] for r in rows)
    msg = "📊 *Laporan Bulan Ini*\n\n"
    for kat, jml in rows:
        msg += f"• {kat}: Rp{jml:,}\n"
    msg += f"\n*Total: Rp{total:,}*"
    await update.message.reply_text(msg, parse_mode='Markdown')

def main():
    if not TOKEN:
        raise ValueError("TELEGRAM_TOKEN belum diset!")
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("keluar", catat))
    app.add_handler(CommandHandler("laporan", laporan))
    print("Bot starting...")
    app.run_polling()

if __name__ == "__main__":
    main()