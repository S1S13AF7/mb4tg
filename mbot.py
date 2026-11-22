# -*- coding: utf-8 -*-

import asyncio
import hashlib
import json
import locale
import os
import random
import re
import socket
import sqlite3
import string
import subprocess
import sys
import time
from datetime import datetime, timedelta

from aiogram import Bot, types
from aiogram.dispatcher import Dispatcher
from aiogram.utils import executor

from const import BIND_OK, DB_NAME, IRISES, REG_OK

################################################################################

_lock_dir = os.path.dirname(os.path.abspath(__file__)).lower()
_lock_port = 20000 + (
	int(hashlib.md5(_lock_dir.encode('utf-8')).hexdigest()[:8], 16)
	% 40000
)
_instance_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
	_instance_sock.bind(('127.0.0.1', _lock_port))
except OSError:
	print(f'⚠️ Копія з {_lock_dir} вже запущена! Вихід...')
	time.sleep(2)
	sys.exit(0)

################################################################################
sys_lang = ''
try:
	loc = (locale.getlocale()[0] or '').split('_')[0].lower()
	if re.match(r'^[a-z]{2,3}$', loc):
		sys_lang = loc
except Exception:
	pass

CONFIG_PATH = "conf.json"
uapi_file = "uapi.json"
u_api_url = "http://localhost/tg/cb.php"

config = {}


def save_config():
	mysqlD = {
		'host': 'localhost',
		'user': 'root',
		'password': 'V3rY$tR0NgPaS$Sw0Rd',
		'db': 'db'
	}
	ordered_config = {
		'token': str(config.get('token', 'YOUR_BOT_TOKEN')),
		'u_api_url': str(config.get('u_api_url') or u_api_url).strip(),
		'db_sqlite3': bool(config.get('db_sqlite3', False)),
		'db_pymysql': bool(config.get('db_pymysql', True)),
		'mysql': (
			config.get('mysql')
			if isinstance(config.get('mysql'), dict)
			else mysqlD
		)
	}
	
	for k, v in config.items():
		if k not in ordered_config:
			ordered_config[k] = v
	with open(CONFIG_PATH, "w", encoding="utf-8") as wf:
		json.dump(ordered_config, wf, ensure_ascii=False, indent='\t')

if os.path.exists("config.py"):
	try:
		import config as old_cfg
		if os.path.exists(CONFIG_PATH):
			with open(CONFIG_PATH, "r", encoding="utf-8-sig") as cf:
				loaded = json.load(cf)
				if isinstance(loaded, dict):
					config.update(loaded)
		old_tok = str(
			getattr(old_cfg, "TOKEN", "") or getattr(old_cfg, "token", "")
		).strip()
		if old_tok and old_tok != "YOUR_BOT_TOKEN":
			config["token"] = old_tok
		save_config()
		try:
			del sys.modules["config"]
		except Exception:
			pass
		os.remove("config.py")
		print(
			f'♻️ Токен перенесено зі старого config.py у {CONFIG_PATH}, '
			f'файл видалено.'
		)
	except Exception as e:
		print(f'⚠️ Не вдалося імпортувати config.py: {e}')

if not os.path.exists(CONFIG_PATH):
	with open(CONFIG_PATH, "w", encoding="utf-8") as wf:
		json.dump({
			"token": "YOUR_BOT_TOKEN",
			"u_api_url": u_api_url,
			"db_sqlite3": False,
			"db_pymysql": True,
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
db_sqlite3 = bool(config.get('db_sqlite3', False))
db_pymysql = bool(config.get('db_pymysql', True))
mysql_conf = config.get('mysql') if isinstance(config.get('mysql'), dict) else {
	'host': 'localhost',
	'user': 'root',
	'password': 'V3rY$tR0NgPaS$Sw0Rd',
	'db': 'db'
}
config['mysql'] = mysql_conf
save_config()

################################################################################


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

################################################################################

def sync_tg_user(
	user_id: int,
	reg_int: int,
	f_name: str,
	lng_code: str = '',
	with_secret: bool = False,
	force_trusted: bool = False
) -> dict:
	if not db_pymysql or not con or not d:
		return {}
	try:
		con.ping(reconnect=True)
		sec_val = gen_uapi_secret(10, 10) if with_secret else ''
		tr_val = '1' if force_trusted else '0'
		
		d.execute(
			'''INSERT INTO `tg_bot_users`
			(`user_id`, `reg_int`, `f_name`, `lng_code`, `secret`, `trusted`)
			VALUES (%s, %s, %s, %s, %s, %s)
			ON DUPLICATE KEY UPDATE
				`f_name` = VALUES(`f_name`),
				`lng_code` = IF(
					VALUES(`lng_code`) != '',
					VALUES(`lng_code`),
					`lng_code`
				),
				`trusted` = IF(
					VALUES(`trusted`) = '1',
					'1',
					`trusted`
				),
				`secret` = IF(
					VALUES(`secret`) != '' AND CHAR_LENGTH(`secret`) < 8,
					VALUES(`secret`),
					`secret`
				);''',
			(
				int(user_id),
				int(reg_int),
				str(f_name),
				str(lng_code),
				sec_val,
				tr_val
			)
		)
		con.commit()
		
		d.execute(
			"SELECT `reg_int`, `lng_code`, `secret`, `trusted` "
			"FROM `tg_bot_users` WHERE `user_id` = %s LIMIT 1",
			(int(user_id),)
		)
		return d.fetchone() or {}
	except Exception as Err:
		print(f"sync_tg_user err: {Err}")
		return {}

################################################################################

if db_sqlite3:
	print('🙅 підтримку sqlite викинуто')

ldb = None
dbc = None
con = None
d = None

if db_pymysql:
	try:
		import pymysql
		import pymysql.cursors
		con = pymysql.connect(
			host=str(mysql_conf.get('host', 'localhost')),
			user=str(mysql_conf.get('user', 'root')),
			password=str(mysql_conf.get('password', '')),
			db=str(mysql_conf.get('db', 'db')),
			charset='utf8mb4',
			autocommit=False,
			cursorclass=pymysql.cursors.DictCursor
		)
		d = con.cursor()
		print('✅ Підключено до MySQL')
	except Exception as e:
		print(f'❌ MySQL недоступний ({e}) — скидаю у False')
		db_pymysql = False
		config['db_pymysql'] = False
		save_config()

if db_pymysql:
	d.execute('''CREATE TABLE IF NOT EXISTS `tg_bot_users` (
		`user_id` bigint(20) UNSIGNED NOT NULL DEFAULT '0',
		`reg_int` int(11) UNSIGNED NOT NULL DEFAULT '0',
		`f_name` text CHARACTER SET utf8mb4 NOT NULL DEFAULT '',
		`lng_code` varchar(8) NOT NULL DEFAULT '',
		`f_time` int(11) UNSIGNED NOT NULL DEFAULT '0',
		`m_time` int(11) UNSIGNED NOT NULL DEFAULT '0',
		`secret` varchar(50) NOT NULL DEFAULT '',
		`trusted` enum('0','1') NOT NULL DEFAULT '0',
		PRIMARY KEY (`user_id`)
	);''')
	con.commit()

################################################################################

bot = Bot(token=TOKEN, parse_mode=types.ParseMode.HTML)
dp = Dispatcher(bot)

async def on_startup(dispatcher: Dispatcher):
	global my_secret
	me = await bot.get_me()
	bot_id = int(me.id)
	bot_name = str(me.first_name or '')
	title_str = f'@{me.username} [{bot_id}]'
	print(f'🤖 Bot started: {title_str}')
	if os.name == 'nt':
		try:
			import ctypes
			ctypes.windll.kernel32.SetConsoleTitleW(str(bot_id))
		except Exception:
			pass
	elif os.name == 'posix':
		print(f'\33]0;{bot_id}\a', end='', flush=True)
	
	row = sync_tg_user(
		bot_id, int(time.time()), bot_name, sys_lang,
		with_secret=True, force_trusted=True
	)
	db_sec = str(row.get('secret', ''))
	if re.match(r"^[a-zA-Z0-9]{8,30}$", db_sec) and db_sec != my_secret:
		my_secret = db_sec
		uapi_conf['secret'] = db_sec
		save_uapi_conf(uapi_conf)
		print(f'🔑 Секрет оновлено з MySQL у {uapi_file}')
	
	asyncio.create_task(auto_pull())

################################################################################


async def reg_user(message: types.Message) -> int:
	user_id = int(message.from_user.id)
	user_fn = message.from_user.first_name or ''
	lng_code = message.from_user.language_code or ''
	when_int = int(datetime.timestamp(message.date))
	reg_date = when_int
	
	row = sync_tg_user(user_id, when_int, user_fn, lng_code)
	if row and int(row.get('reg_int') or 0) > 0:
		reg_date = int(row['reg_int'])
	
	if reg_date == when_int:
		print(REG_OK.get(lng_code, REG_OK['default']).format(user_fn=user_fn))
	
	return reg_date


async def has_user_lang(user_id: int) -> bool:
	if db_pymysql and con and d:
		try:
			con.ping(reconnect=True)
			d.execute(
				"SELECT `lng_code` FROM `tg_bot_users` "
				"WHERE `user_id` = %s LIMIT 1",
				(int(user_id),)
			)
			row = d.fetchone()
			if row and str(row.get('lng_code') or '').strip():
				return True
		except Exception:
			pass
	return False


async def get_cb_secret(
	user_id: int,
	when_int: int,
	user_fn: str,
	lng_code: str
) -> str:
	row = sync_tg_user(
		user_id, when_int, user_fn, lng_code,
		with_secret=True
	)
	return str(row.get('secret') or '')


@dp.message_handler(commands=['start', 'reg', 'cb', 'cb4ub', 'cb4tg'])
async def cmd_user_entry(message: types.Message):
	cmd = (message.get_command() or '').lstrip('/').split('@')[0].lower()
	user_id = int(message.from_user.id)
	user_fn = message.from_user.first_name or ''
	lng_code = message.from_user.language_code or ''
	when_int = int(datetime.timestamp(message.date))
	is_pm = (message.chat.type == types.ChatType.PRIVATE)
	
	if cmd in ('cb', 'cb4ub', 'cb4tg'):
		if not db_pymysql:
			await message.reply("⚠️ Серверна БД зараз недоступна.")
			return
		
		if not is_pm and not await has_user_lang(user_id):
			me_bot = await bot.get_me()
			await message.reply(
				f"🔒 Спершу напиши мені в <a href=\"https://t.me/"
				f"{me_bot.username}?start=cb\">ЛС</a> (<code>/start</code> "
				f"або <code>/cb</code>), щоб я міг надіслати секрет."
			)
			return
		
		await reg_user(message)
		sec = await get_cb_secret(user_id, when_int, user_fn, lng_code)
		if not sec:
			await message.reply("❌ Не вдалося отримати секрет.")
			return
		
		sec_text = (
			f"🔑 Твій API-секрет (<code>uapi.json</code>):\n"
			f"<code>{sec}</code>"
		)
		if is_pm:
			await message.answer(sec_text)
		else:
			try:
				await bot.send_message(user_id, sec_text)
				await message.reply("🔑 Надіслав секрет тобі в ЛС.")
			except Exception:
				me_bot = await bot.get_me()
				await message.reply(
					f"⚠️ Не можу написати тобі в ЛС. Відкрий "
					f"<a href=\"https://t.me/{me_bot.username}?start=cb\">"
					f"діалог зі мною</a> і надішли туди <code>/cb</code>."
				)
		return
	
	rd = int(await reg_user(message))
	if rd == when_int:
		
		tpl = REG_OK.get(lng_code, REG_OK['default'])
		snd_msg = tpl.format(user_fn=user_fn)
	
	elif cmd == 'reg' and rd > 0:
		snd_msg = time.strftime('%d.%m.%Y', time.localtime(rd))
	else:
		snd_msg = "🖖"
	
	await message.answer(snd_msg)

@dp.message_handler(
	lambda m: m.chat.type != 'private'
	and m.from_user
	and int(m.from_user.id) in IRISES
	and bool(re.search(
		r'🗓\s*Код\s+(?:беседы|чата|чату)\s*:\s*([0-9a-f]{8})',
		m.text or m.caption or '',
		re.IGNORECASE
	)),
	content_types=types.ContentTypes.TEXT
)
async def iris_bind_chat_bot(message: types.Message):
	raw_txt = message.text or message.caption or ''
	code_m = re.search(
		r'🗓\s*Код\s+(?:беседы|чата|чату)\s*:\s*([0-9a-f]{8})',
		raw_txt,
		re.IGNORECASE
	)
	if not code_m or not db_pymysql or not con or not d:
		return
	
	code = code_m.group(1).lower()
	chat_abs = abs(int(message.chat.id))
	chat_title = str(message.chat.title or '').strip()
	msg_ts = int(datetime.timestamp(message.date))
	me = await bot.get_me()
	bot_id = int(me.id)
	
	print(f'🔗 [mbot bind] {bot_id} -> {code} : -{chat_abs} ({chat_title})')
	
	try:
		con.ping(reconnect=True)
		d.execute(
			'''INSERT INTO `userbot_bind`
			(`platform`, `id_user`, `code`, `date`, `id_chat`, `title`)
			VALUES ('tg', %s, %s, %s, %s, %s)
			ON DUPLICATE KEY UPDATE
				`date` = VALUES(`date`),
				`id_chat` = VALUES(`id_chat`),
				`title` = IF(
					VALUES(`title`) != '',
					VALUES(`title`),
					`title`
				);''',
			(bot_id, code, msg_ts, chat_abs, chat_title)
		)
		affected = int(d.rowcount or 0)
		con.commit()
		
		if affected > 0:
			lang_code = ''
			if message.reply_to_message and message.reply_to_message.from_user:
				caller = message.reply_to_message.from_user
				lang_code = str(caller.language_code or '').strip().lower()
				d.execute(
					"SELECT `lng_code` FROM `tg_bot_users` "
					"WHERE `user_id` = %s LIMIT 1",
					(int(caller.id),)
				)
				u_row = d.fetchone()
				if u_row and str(u_row.get('lng_code') or '').strip():
					lang_code = str(u_row['lng_code']).strip().lower()
			
			short_lang = lang_code[:2] if lang_code else 'default'
			reply_txt = BIND_OK.get(short_lang, BIND_OK['default'])
			await message.answer(reply_txt)
	except Exception as Err:
		print(f'⚠️ [mbot bind] MySQL err: {Err}')

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
<code>https://github.com/S1S13AF7/cb4tg</code> – CallBack для ботів у телеграмі
<code>https://github.com/S1S13AF7/mb4tg</code> – код бота @misc_beta_bot
<code>https://github.com/S1S13AF7/ub4tg</code> – юб. 
	'''
	await message.answer(text,parse_mode=types.ParseMode.HTML)

@dp.message_handler(commands=['termux','термукс'])
async def cmd_termux(message: types.Message):
	text='''
<a href="https://f-droid.org/packages/com.termux/">Termux</a> / <a 
	href="https://f-droid.org/packages/com.termux.api/">Termux API</a>

<code>pkg install openssl openssl-tool python3 git termux-api</code>

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

################################################################################

async def auto_pull():
	repo_dir = os.path.dirname(os.path.abspath(__file__))
	if not os.path.isdir(os.path.join(repo_dir, '.git')):
		return
	
	await asyncio.sleep(random.uniform(60, 180))
	err_notified = False
	loop = asyncio.get_running_loop()
	
	while True:
		try:
			proc = await loop.run_in_executor(
				None,
				lambda: subprocess.run(
					['git', 'pull'],
					cwd=repo_dir,
					capture_output=True,
					text=True,
					timeout=30
				)
			)
			out_s = (proc.stdout or '').strip()
			err_s = (proc.stderr or '').strip()
			msg = out_s or err_s
			
			if proc.returncode != 0:
				if not err_notified:
					err_notified = True
					print(f'⚠️ [auto_pull] Помилка git pull:\n{msg[:300]}')
			else:
				err_notified = False
				if (
					msg
					and 'Already up to date' not in msg
					and 'Уже актуально' not in msg
				):
					print(f'📥 [auto_pull] Оновлено:\n{msg[:300]}')
		except Exception as e:
			print(f'⚠️ [auto_pull] Виняток: {e}')
		
		await asyncio.sleep(random.uniform(1800, 2700))

if __name__ == '__main__':
	executor.start_polling(dp, on_startup=on_startup)
