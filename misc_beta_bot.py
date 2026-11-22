# -*- coding: utf-8 -*-

import json
import os
import random
import re
import sqlite3
import string
import sys
import time
from datetime import datetime, timedelta

from aiogram import Bot, types
from aiogram.dispatcher import Dispatcher
from aiogram.utils import executor

from const import REG_OK

########################################################################

CONFIG_PATH = "conf.json"
uapi_file = "uapi.json"
u_api_url = "http://localhost/tg/cb.php"

config = {}


def save_config():
	ordered_config = {
		'token': str(config.get('token', 'YOUR_BOT_TOKEN')),
		'u_api_url': str(config.get('u_api_url') or u_api_url).strip(),
		'db_sqlite3': bool(config.get('db_sqlite3', True)),
		'db_pymysql': bool(config.get('db_pymysql', False)),
		'mysql': config.get('mysql') if isinstance(config.get('mysql'), dict) else {
			'host': 'localhost',
			'user': 'root',
			'password': 'V3rY$tR0NgPaS$Sw0Rd',
			'db': 'db'
		}
	}
	for k, v in config.items():
		if k not in ordered_config:
			ordered_config[k] = v
	with open(CONFIG_PATH, "w", encoding="utf-8") as wf:
		json.dump(ordered_config, wf, ensure_ascii=False, indent='\t')


if not os.path.exists(CONFIG_PATH):
	with open(CONFIG_PATH, "w", encoding="utf-8") as wf:
		json.dump({
			"token": "YOUR_BOT_TOKEN",
			"u_api_url": u_api_url,
			"db_sqlite3": True,
			"db_pymysql": False,
			"mysql": {
				"host": "localhost",
				"user": "root",
				"password": "V3rY$tR0NgPaS$Sw0Rd",
				"db": "db"
			}
		}, wf, ensure_ascii=False, indent='\t')
	print(f'⚠️ Створено {CONFIG_PATH}. Впиши туди токен бота і перезапусти!')
	sys.exit(0)

with open(CONFIG_PATH, "r", encoding="utf-8-sig") as cf:
	config = json.load(cf)
	print('✅ config loaded')

TOKEN = str(config.get('token', '')).strip()
if not TOKEN or TOKEN == 'YOUR_BOT_TOKEN':
	print(f'❌ Не вказано token у {CONFIG_PATH}!')
	sys.exit(1)

u_api_url = str(config.get('u_api_url') or u_api_url).strip()
db_sqlite3 = bool(config.get('db_sqlite3', True))
db_pymysql = bool(config.get('db_pymysql', False))
mysql_conf = config.get('mysql') if isinstance(config.get('mysql'), dict) else {
	'host': 'localhost',
	'user': 'root',
	'password': 'V3rY$tR0NgPaS$Sw0Rd',
	'db': 'db'
}
config['mysql'] = mysql_conf
save_config()

########################################################################


def gen_uapi_secret(min_len: int = 10, max_len: int = 15) -> str:
	chars = string.ascii_letters + string.digits
	length = random.randint(min_len, max_len)
	return ''.join(random.choice(chars) for _ in range(length))


def load_uapi_conf(filepath: str = uapi_file) -> dict:
	base_dir = os.path.dirname(os.path.abspath(__file__))
	full_path = os.path.join(base_dir, filepath)
	data = {}
	need_save = False
	
	if os.path.isfile(full_path):
		try:
			with open(full_path, "r", encoding="utf-8-sig") as f:
				raw = json.load(f)
				if isinstance(raw, dict):
					data = raw
		except Exception:
			data = {}
			need_save = True
	else:
		need_save = True
	
	secret = str(data.get("secret", ""))
	if not re.match(r"^[a-zA-Z0-9]{8,30}$", secret):
		data["secret"] = gen_uapi_secret()
		need_save = True
	
	if need_save:
		save_uapi_conf(data, full_path)
	
	return data


def save_uapi_conf(data: dict, full_path: str = None):
	if not full_path:
		base_dir = os.path.dirname(os.path.abspath(__file__))
		full_path = os.path.join(base_dir, uapi_file)
	with open(full_path, "w", encoding="utf-8") as f:
		json.dump(data, f, ensure_ascii=False, indent='\t')


uapi_conf = load_uapi_conf()
my_secret = str(uapi_conf.get('secret', ''))

########################################################################

if db_sqlite3:
	con = sqlite3.connect("db4tg.sqlite")
	cur = con.cursor()
	cur.execute('''CREATE TABLE IF NOT EXISTS users (
		user_id		INTEGER NOT NULL DEFAULT 0 UNIQUE,
		reg_int		INTEGER NOT NULL DEFAULT 0,
		f_name		VARCHAR NOT NULL DEFAULT '',
		lng_code	VARCHAR NOT NULL DEFAULT ''
	);''')
	con.commit()

ldb = None
dbc = None

if db_pymysql:
	try:
		import pymysql
		import pymysql.cursors
		ldb = pymysql.connect(
			host=str(mysql_conf.get('host', 'localhost')),
			user=str(mysql_conf.get('user', 'root')),
			password=str(mysql_conf.get('password', '')),
			db=str(mysql_conf.get('db', 'db')),
			charset='utf8mb4',
			autocommit=True,
			cursorclass=pymysql.cursors.DictCursor
		)
		dbc = ldb.cursor()
		dbc.execute('''CREATE TABLE IF NOT EXISTS `tg_bot_users` (
			`user_id` bigint(20) unsigned NOT NULL DEFAULT '0',
			`reg_int` int(11) unsigned NOT NULL DEFAULT '0',
			`f_name` text CHARACTER SET utf8mb4 NOT NULL,
			`lng_code` varchar(8) NOT NULL DEFAULT '',
			`f_time` int(11) unsigned NOT NULL DEFAULT '0',
			`m_time` int(11) unsigned NOT NULL DEFAULT '0',
			`secret` varchar(50) NOT NULL DEFAULT '',
			`trusted` enum('0','1') NOT NULL DEFAULT '0',
			PRIMARY KEY (`user_id`)
		);''')
		for alter_sql in (
			"ALTER TABLE `tg_bot_users` "
			"ADD COLUMN `lng_code` varchar(8) NOT NULL DEFAULT '';",
			"ALTER TABLE `tg_bot_users` "
			"ADD COLUMN `secret` varchar(50) NOT NULL DEFAULT '';",
			"ALTER TABLE `tg_bot_users` "
			"ADD COLUMN `trusted` enum('0','1') NOT NULL DEFAULT '0';"
		):
			try:
				dbc.execute(alter_sql)
			except Exception:
				pass
		print('✅ Підключено до MySQL')
	except Exception as e:
		print(f'❌ MySQL недоступний ({e}) — скидаю у False')
		db_pymysql = False
		config['db_pymysql'] = False
		save_config()

########################################################################

bot = Bot(token=TOKEN, parse_mode=types.ParseMode.HTML)
dp = Dispatcher(bot)


async def on_startup(dispatcher: Dispatcher):
	global my_secret
	me = await bot.get_me()
	bot_id = int(me.id)
	bot_name = str(me.first_name or '')
	print(f'Bot started: @{me.username} ({bot_id})')
	
	if db_pymysql and ldb and dbc:
		try:
			ldb.ping(reconnect=True)
			dbc.execute(
				'''INSERT INTO `tg_bot_users`
				(`user_id`, `reg_int`, `f_name`, `secret`, `trusted`)
				VALUES (%s, %s, %s, %s, '1')
				ON DUPLICATE KEY UPDATE
					`f_name` = VALUES(`f_name`),
					`trusted` = '1',
					`secret` = IF(
						CHAR_LENGTH(`secret`) >= 8,
						`secret`,
						VALUES(`secret`)
					);''',
				(bot_id, int(time.time()), bot_name, my_secret)
			)
			dbc.execute(
				"SELECT `secret` FROM `tg_bot_users` WHERE `user_id` = %s",
				(bot_id,)
			)
			row_sec = dbc.fetchone()
			if row_sec:
				db_sec = str(row_sec.get('secret', ''))
				if (
					re.match(r"^[a-zA-Z0-9]{8,30}$", db_sec)
					and db_sec != my_secret
				):
					my_secret = db_sec
					uapi_conf['secret'] = db_sec
					save_uapi_conf(uapi_conf)
					print(f'🔑 Секрет оновлено з MySQL у {uapi_file}')
		except Exception as e:
			print(f'⚠️ Помилка самореєстрації бота в MySQL: {e}')

	if db_sqlite3 and db_pymysql:
		#якщо юзаємо обидві бази,то
		reg_date=int(min(sqlite_rd,pymysql_rd))
		
		if sqlite_rd < pymysql_rd:
			#UPDATE `tg_bot_users` SET `reg_int`=? WHERE `user_id`=?;
			try:
				dbc.execute(f"UPDATE `tg_bot_users` SET `reg_int` ='{reg_date}' WHERE user_id = %d" % int(user_id)); ldb.commit()#як я хотів воно нехотіло, тому буде пока так.
			except Exception as Err:
				print(f"localhost UPDATE:{Err}")
		
		if sqlite_rd > pymysql_rd:
			try:
				cur.execute("UPDATE users SET reg_int =? WHERE user_id=?", (int(reg_date),int(user_id))); con.commit()
			except Exception as Err:
				print(f"sqlite UPDATE:{Err}")
	
	if reg_date==when_int:
		print(REG_OK.get(lng_code, REG_OK['default']).format(user_fn=user_fn))
	
	return reg_date

bot = Bot(token=TOKEN, parse_mode=types.ParseMode.HTML) #see: https://mastergroosha.github.io/aiogram-2-guide/messages/
dp = Dispatcher(bot)   

print('Bot started') 

########################################################################


async def get_cb_secret(
	user_id: int,
	when_int: int,
	user_fn: str,
	lng_code: str
) -> str:
	if not db_pymysql or not ldb or not dbc:
		return ''
	try:
		ldb.ping(reconnect=True)
		new_sec = gen_uapi_secret(10, 10)
		dbc.execute(
			'''INSERT INTO `tg_bot_users`
			(`user_id`, `reg_int`, `f_name`, `lng_code`, `secret`, `trusted`)
			VALUES (%s, %s, %s, %s, %s, '0')
			ON DUPLICATE KEY UPDATE
				`f_name` = VALUES(`f_name`),
				`lng_code` = VALUES(`lng_code`),
				`secret` = IF(
					CHAR_LENGTH(`secret`) >= 8,
					`secret`,
					VALUES(`secret`)
				);''',
			(int(user_id), int(when_int), str(user_fn), str(lng_code), new_sec)
		)
		dbc.execute(
			"SELECT `secret` FROM `tg_bot_users` WHERE `user_id` = %s LIMIT 1",
			(int(user_id),)
		)
		row = dbc.fetchone()
		if row and row.get('secret'):
			return str(row['secret'])
	except Exception as Err:
		print(f"localhost get_cb_secret err: {Err}")
	return ''


@dp.message_handler(commands=['start', 'reg', 'cb', 'cb4ub', 'cb4tg'])
async def cmd_user_entry(message: types.Message):
	cmd = (message.get_command() or '').lstrip('/').split('@')[0].lower()
	user_id = int(message.from_user.id)
	user_fn = message.from_user.first_name or ''
	lng_code = message.from_user.language_code or ''
	when_int = int(datetime.timestamp(message.date))
	
	if cmd in ('cb', 'cb4ub', 'cb4tg'):
		if message.chat.type != types.ChatType.PRIVATE:
			await message.reply("🔒 Команда доступна тільки в ЛС бота.")
			return
		if not db_pymysql:
			await message.reply("⚠️ Серверна БД зараз недоступна.")
			return
		await reg_user(message)
		sec = await get_cb_secret(user_id, when_int, user_fn, lng_code)
		if sec:
			await message.answer(
				f"🔑 Твій API-секрет (<code>uapi.json</code>):\n"
				f"<code>{sec}</code>"
			)
		else:
			await message.answer("❌ Не вдалося отримати секрет.")
		return
	
	rd = int(await reg_user(message))
	if rd == when_int:
		snd_msg = REG_OK.get(lng_code, REG_OK['default']).format(user_fn=user_fn)
	elif cmd == 'reg' and rd > 0:
		snd_msg = time.strftime('%d.%m.%Y', time.localtime(rd))
	else:
		snd_msg = "🖖"
	
	await message.answer(snd_msg)
	
	rd = int(await reg_user(message))
	if rd == when_int:
		snd_msg = REG_OK.get(lng_code, REG_OK['default']).format(user_fn=user_fn)
	elif cmd == 'reg' and rd > 0:
		snd_msg = time.strftime('%d.%m.%Y', time.localtime(rd))
	else:
		snd_msg = "🖖"
	
	await message.answer(snd_msg)


@dp.message_handler(commands=['help'])
async def process_help_command(message: types.Message):
	await message.answer('''
•	🔑 /cb4ub
•	💬 /chats
•	📃 /code
•	🎲 /dice
''')

@dp.message_handler(commands=['ping'])
async def process_ping_command(message: types.Message):
	await message.reply("𝐏𝐎𝐍𝐆!")

@dp.message_handler(commands=['dice','кубик'])
async def cmd_dice(message: types.Message):
	await message.answer_dice(emoji="🎲")

@dp.message_handler(commands=['code','код'])
async def cmd_code(message: types.Message):
	text='''
<code>https://github.com/S1S13AF7/misc_beta_bot</code> – код бота @misc_beta_bot
<code>https://github.com/S1S13AF7/ub4tg</code> – юб. 
	'''
	await message.answer(text,parse_mode=types.ParseMode.HTML)

@dp.message_handler(commands=['termux','термукс'])
async def cmd_termux(message: types.Message):
	text='''
<a href="https://f-droid.org/packages/com.termux/">Termux</a> / <a 
	href="https://f-droid.org/packages/com.termux.api/">Termux API</a>

<code>pkg install openssl python3 git termux-api</code>

далі клонуємо 
<code>git clone https://github.com/S1S13AF7/ub4tg</code>

<code>cd ub4tg && pip3 install -r requirements.txt</code>

запуск: <code>python3 ubot.py</code>

	'''
	await message.answer(text,parse_mode=types.ParseMode.HTML)

@dp.message_handler(commands=['st','startrek'])
async def cmd_startrek(message: types.Message):
	text='''
Як дивитись «Star Trek»?! Легко і просто береш і дивишся. 
Або якщо цікавить правильний порядок то 
<a href = "https://thestartrekchronologyproject.blogspot.com/2009/09/and-now-conclusion.html">список всіх серій</a>:
<code>https://thestartrekchronologyproject.blogspot.com/2009/09/and-now-conclusion.html</code>

	'''
	await message.answer(text,parse_mode=types.ParseMode.HTML)

@dp.message_handler(commands=['chats','чати','чаты','чаті'])
async def cmd_chats(message: types.Message):
	await message.answer('''
•	☕ @misc_chat
•	🐸 @misc_games
•	🗃 @misc_files_v2
''')

if __name__ == '__main__':
	executor.start_polling(dp)
