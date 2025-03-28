import flet as ft
import sqlite3
import smtplib
from email.mime.text import MIMEText
import secrets
import string
import datetime
import hashlib
import webbrowser
from typing import Dict, List, Optional
from urllib.parse import parse_qs
import requests

def get_usd_rate():
    try:
        response = requests.get("https://api.exchangerate-api.com/v4/latest/USD")
        return response.json()["rates"]["RUB"]
    except:
        return 90.0  # Значение по умолчанию при ошибке

# ====================== НАСТРОЙКИ ======================
DB_NAME = "minios.db"
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
EMAIL_FROM = "r4677777@gmail.com"  # Замените на ваш Gmail
EMAIL_PASSWORD = "bmom vkro lehw etew"  # Пароль приложения Gmail
BASE_URL = "http://localhost:8501"  # Для разработки
COOKIE_NAME = "minios_auth"
SESSION_DURATION = 30  # Дней хранения сессии
USD_TO_RUB = get_usd_rate()

# ====================== ИНИЦИАЛИЗАЦИЯ БД ======================
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # Таблица пользователей
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                 username TEXT UNIQUE,
                 password TEXT,
                 email TEXT UNIQUE,
                 email_verified BOOLEAN DEFAULT 0,
                 verification_token TEXT,
                 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                 is_admin BOOLEAN DEFAULT 0)''')
    
    # Таблица ключей продукта
    c.execute('''CREATE TABLE IF NOT EXISTS product_keys
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                 key TEXT UNIQUE,
                 is_used BOOLEAN DEFAULT 0,
                 user_id INTEGER,
                 purchase_date TIMESTAMP,
                 FOREIGN KEY(user_id) REFERENCES users(id))''')
    
    # Таблица покупок
    c.execute('''CREATE TABLE IF NOT EXISTS purchases
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                 user_id INTEGER,
                 key_id INTEGER,
                 amount REAL,
                 currency TEXT,
                 payment_date TIMESTAMP,
                 FOREIGN KEY(user_id) REFERENCES users(id),
                 FOREIGN KEY(key_id) REFERENCES product_keys(id))''')
    
    # Таблица версий
    c.execute('''CREATE TABLE IF NOT EXISTS versions
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                 version TEXT UNIQUE,
                 release_date TIMESTAMP,
                 changelog TEXT,
                 download_url TEXT,
                 is_stable BOOLEAN DEFAULT 1,
                 file_size TEXT)''')
    
    # Создаем администратора по умолчанию
    c.execute("SELECT * FROM users WHERE username='admin'")
    if not c.fetchone():
        hashed_pass = hashlib.sha256("admin123".encode()).hexdigest()
        c.execute('''INSERT INTO users 
                    (username, password, email, email_verified, is_admin) 
                    VALUES (?, ?, ?, 1, 1)''',
                 ("admin", hashed_pass, "admin@minios.com"))
    
    # Добавляем тестовые версии, если их нет
    c.execute("SELECT COUNT(*) FROM versions")
    if c.fetchone()[0] == 0:
        versions = [
            ("1.0.0", "2023-01-15", "Первая стабильная версия", "http://example.com/minios_1.0.0.iso", 1, "256MB"),
            ("1.1.0", "2023-03-20", "Исправление ошибок, новые драйверы", "http://example.com/minios_1.1.0.iso", 1, "264MB"),
            ("2.0.0-beta", "2023-05-10", "Бета-версия с новым интерфейсом", "http://example.com/minios_2.0.0_beta.iso", 0, "300MB")
        ]
        c.executemany('''INSERT INTO versions 
                        (version, release_date, changelog, download_url, is_stable, file_size)
                        VALUES (?, ?, ?, ?, ?, ?)''', versions)
    
    conn.commit()
    conn.close()

# ====================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ======================
def generate_token(length=32):
    """Генерация криптографически безопасного токена"""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def hash_password(password: str) -> str:
    """Хеширование пароля"""
    return hashlib.sha256(password.encode()).hexdigest()

def send_verification_email(email: str, token: str) -> bool:
    """Отправка письма с подтверждением"""
    verify_url = f"{BASE_URL}/verify?email={email}&token={token}"
    
    subject = "Подтверждение email для MiniOS"
    body = f"""Здравствуйте,

Для завершения регистрации подтвердите ваш email, перейдя по ссылке:
{verify_url}

Ссылка действительна 24 часа.

Если вы не регистрировались на нашем сайте, проигнорируйте это письмо.

С уважением,
Команда MiniOS
"""
    return send_email(email, subject, body)

def send_email(to_email: str, subject: str, body: str) -> bool:
    """Отправка email через SMTP"""
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = EMAIL_FROM
    msg['To'] = to_email
    
    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_FROM, EMAIL_PASSWORD)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"Ошибка отправки email: {e}")
        return False

def create_product_key(username: str) -> str:
    """Генерация ключа продукта"""
    seed = f"{username}{datetime.datetime.now().timestamp()}"
    return hashlib.sha256(seed.encode()).hexdigest()[:20].upper()

# ====================== ОСНОВНОЕ ПРИЛОЖЕНИЕ ======================
def main(page: ft.Page):
    # Инициализация БД
    init_db()
    
    # Настройки страницы
    page.title = "MiniOS - Официальный сайт"
    page.theme = ft.Theme(
        color_scheme=ft.ColorScheme(
            primary=ft.colors.BLUE,
            secondary=ft.colors.GREEN,
        ),
    )
    page.theme_mode = ft.ThemeMode.DARK
    page.window_width = 1200
    page.window_height = 800
    page.padding = 20
    
    # Состояние приложения
    class AppState:
        def __init__(self):
            self.current_user = None
            self.load_from_cookies()
        
        def load_from_cookies(self):
            """Загрузка пользователя из cookies"""
            if page.client_storage.contains_key(COOKIE_NAME):
                auth_data = page.client_storage.get(COOKIE_NAME)
                if auth_data and datetime.datetime.now().timestamp() - auth_data["timestamp"] < SESSION_DURATION * 86400:
                    conn = sqlite3.connect(DB_NAME)
                    c = conn.cursor()
                    c.execute('''SELECT id, username, email, email_verified, is_admin 
                               FROM users WHERE id=?''', (auth_data["user_id"],))
                    user = c.fetchone()
                    conn.close()
                    
                    if user:
                        self.current_user = {
                            "id": user[0],
                            "username": user[1],
                            "email": user[2],
                            "email_verified": bool(user[3]),
                            "is_admin": bool(user[4])
                        }
        
        def update_user_data(self):
            """Обновление данных пользователя из БД"""
            if self.current_user:
                conn = sqlite3.connect(DB_NAME)
                c = conn.cursor()
                c.execute('''SELECT id, username, email, email_verified, is_admin 
                           FROM users WHERE id=?''', (self.current_user["id"],))
                user = c.fetchone()
                conn.close()
                
                if user:
                    self.current_user = {
                        "id": user[0],
                        "username": user[1],
                        "email": user[2],
                        "email_verified": bool(user[3]),
                        "is_admin": bool(user[4])
                    }
        
        def login(self, user_id: int):
            """Сохранение сессии"""
            self.current_user = {"id": user_id}
            self.update_user_data()
            page.client_storage.set(COOKIE_NAME, {
                "user_id": user_id,
                "timestamp": datetime.datetime.now().timestamp()
            })
        
        def logout(self):
            """Завершение сессии"""
            self.current_user = None
            page.client_storage.remove(COOKIE_NAME)
    
    state = AppState()
    
    # ====================== КОМПОНЕНТЫ ИНТЕРФЕЙСА ======================
    def show_dialog(title: str, message: str, on_confirm=None):
        """Показать диалоговое окно"""
        def close_dlg(e):
            dlg.open = False
            page.update()
            if on_confirm:
                on_confirm()
        
        dlg = ft.AlertDialog(
            title=ft.Text(title),
            content=ft.Text(message),
            actions=[ft.TextButton("OK", on_click=close_dlg)],
        )
        page.dialog = dlg
        dlg.open = True
        page.update()
    
    def show_snackbar(message: str, color=ft.colors.GREEN):
        """Показать уведомление"""
        page.snack_bar = ft.SnackBar(ft.Text(message), bgcolor=color)
        page.snack_bar.open = True
        page.update()
    
    def create_navbar():
        """Создание навигационной панели"""
        admin_items = []
        if state.current_user and state.current_user.get("is_admin"):
            admin_items.append(
                ft.PopupMenuItem(
                    icon=ft.icons.ADMIN_PANEL_SETTINGS, 
                    text="Админ-панель", 
                    on_click=lambda _: page.go("/admin")
                )
            )
        
        account_items = [
            ft.PopupMenuItem(
                icon=ft.icons.ACCOUNT_CIRCLE, 
                text="Мой аккаунт", 
                on_click=lambda _: page.go("/account")
            )
        ]
        
        if state.current_user:
            account_items.append(
                ft.PopupMenuItem(
                    icon=ft.icons.LOGOUT, 
                    text="Выйти", 
                    on_click=lambda _: logout()
                )
            )
        
        return ft.AppBar(
            title=ft.Text("MiniOS", style=ft.TextThemeStyle.HEADLINE_MEDIUM),
            center_title=True,
            actions=[
                ft.PopupMenuButton(
                    items=[
                        ft.PopupMenuItem(icon=ft.icons.HOME, text="Главная", on_click=lambda _: page.go("/")),
                        ft.PopupMenuItem(icon=ft.icons.VERIFIED, text="Проверить ключ", on_click=lambda _: page.go("/validate")),
                        ft.PopupMenuItem(icon=ft.icons.SHOP, text="Купить MiniOS Pro", on_click=lambda _: page.go("/purchase")),
                        ft.PopupMenuItem(icon=ft.icons.CODE, text="Версии", on_click=lambda _: page.go("/versions")),
                        *admin_items,
                        ft.PopupMenuItem(),  # Разделитель
                        *account_items
                    ]
                )
            ]
        )
    
    # ====================== ПРЕДСТАВЛЕНИЯ СТРАНИЦ ======================
    def home_view():
        """Главная страница"""
        page.clean()
        page.add(create_navbar())
        
        welcome_text = ft.Text(
            "Добро пожаловать в MiniOS!",
            size=36,
            weight=ft.FontWeight.BOLD,
            text_align=ft.TextAlign.CENTER
        )
        
        description = ft.Markdown(
            """
**MiniOS** - это легкая, быстрая и безопасная операционная система, разработанная для:
- Старых компьютеров
- Разработчиков
- Энтузиастов open-source

Основные преимущества:
- 🚀 Мгновенная загрузка
- 🔒 Встроенная безопасность
- 🛠️ Полный контроль над системой
            """,
            extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
            on_tap_link=lambda e: webbrowser.open(e.data)
        )
        
        buttons = ft.ResponsiveRow(
            [
                ft.ElevatedButton(
                    "Скачать бесплатно",
                    icon=ft.icons.DOWNLOAD,
                    on_click=lambda _: page.go("/versions"),
                    col={"sm": 6},
                    style=ft.ButtonStyle(padding=20)
                ),
                ft.ElevatedButton(
                    "Купить Pro версию",
                    icon=ft.icons.SHOP,
                    on_click=lambda _: page.go("/purchase"),
                    col={"sm": 6},
                    style=ft.ButtonStyle(padding=20, bgcolor=ft.colors.AMBER)
                )
            ],
            spacing=20
        )
        
        page.add(
            ft.Column(
                [
                    ft.Image(src="https://via.placeholder.com/300x150?text=MiniOS+Logo", width=300),
                    welcome_text,
                    ft.Divider(),
                    description,
                    ft.Divider(),
                    buttons
                ],
                spacing=30,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                scroll=ft.ScrollMode.AUTO,
                expand=True
            )
        )
    
    def validate_view():
        """Страница проверки ключа"""
        page.clean()
        page.add(create_navbar())
        
        key_field = ft.TextField(
            label="Введите ключ продукта",
            width=400,
            autofocus=True,
            border_color=ft.colors.BLUE
        )
        
        result_text = ft.Text("", size=18)
        
        def validate_click(e):
            key = key_field.value.strip()
            if not key:
                result_text.value = "Пожалуйста, введите ключ"
                result_text.color = ft.colors.RED
                result_text.update()
                return
            
            conn = sqlite3.connect(DB_NAME)
            c = conn.cursor()
            c.execute('''SELECT product_keys.key, users.username, product_keys.purchase_date 
                        FROM product_keys 
                        JOIN users ON product_keys.user_id = users.id
                        WHERE product_keys.key=? AND product_keys.is_used=0''', (key,))
            key_data = c.fetchone()
            conn.close()
            
            if key_data:
                result_text.value = f"✅ Ключ действителен\nВладелец: {key_data[1]}\nДата покупки: {key_data[2]}"
                result_text.color = ft.colors.GREEN
            else:
                result_text.value = "❌ Ключ недействителен или уже был использован"
                result_text.color = ft.colors.RED
            result_text.update()
        
        page.add(
            ft.Column(
                [
                    ft.Text("Проверка ключа продукта", size=28, weight=ft.FontWeight.BOLD),
                    ft.Divider(),
                    key_field,
                    ft.ElevatedButton("Проверить", on_click=validate_click, icon=ft.icons.VERIFIED),
                    result_text
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=20
            )
        )
    
    def purchase_view():
        """Страница покупки с прокруткой и ценами в рублях"""
        page.clean()
        page.add(create_navbar())
        
        if not state.current_user:
            page.add(
                ft.Column(
                    [
                        ft.Text("Для покупки необходимо войти в систему", size=20),
                        ft.ElevatedButton("Войти", on_click=lambda _: page.go("/account"))
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    expand=True
                )
            )
            return
        
        if not state.current_user["email_verified"]:
            page.add(
                ft.Column(
                    [
                        ft.Text("Для покупки необходимо подтвердить email", size=20),
                        ft.ElevatedButton(
                            "Отправить подтверждение повторно", 
                            on_click=lambda _: send_verification_email(
                                state.current_user["email"],
                                generate_token()
                            )
                        ),
                        ft.ElevatedButton("Перейти в аккаунт", on_click=lambda _: page.go("/account"))
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    expand=True
                )
            )
            return
        
        # Курс доллара (можно заменить на актуальный или API)
        USD_TO_RUB = 90.0
        
        plans = [
            {
                "name": "Basic",
                "price_usd": 9.99,
                "price_rub": 9.99 * USD_TO_RUB,
                "features": [
                    "1 ключ продукта", 
                    "Базовая поддержка", 
                    "Доступ к стабильным версиям"
                ],
                "color": ft.colors.BLUE
            },
            {
                "name": "Pro",
                "price_usd": 19.99,
                "price_rub": 19.99 * USD_TO_RUB,
                "features": [
                    "2 ключа продукта", 
                    "Приоритетная поддержка", 
                    "Ранний доступ к бета-версиям"
                ],
                "color": ft.colors.GREEN
            },
            {
                "name": "Enterprise",
                "price_usd": 49.99,
                "price_rub": 49.99 * USD_TO_RUB,
                "features": [
                    "5 ключей продукта", 
                    "24/7 поддержка", 
                    "Персональный менеджер"
                ],
                "color": ft.colors.PURPLE
            }
        ]
        
        def create_plan_card(plan):
            price_text = ft.Column([
                ft.Text(f"${plan['price_usd']:.2f}", size=18),
                ft.Text(f"≈{plan['price_rub']:.2f}₽", size=16, color=ft.colors.GREY)
            ], spacing=0)
            
            features = ft.Column(
                [ft.Text(f"• {feature}") for feature in plan["features"]],
                spacing=5
            )
            
            return ft.Card(
                content=ft.Container(
                    content=ft.Column(
                        [
                            ft.Text(plan["name"], size=24, weight=ft.FontWeight.BOLD, color=plan["color"]),
                            price_text,
                            ft.Divider(),
                            features,
                            ft.ElevatedButton(
                                "Купить",
                                on_click=lambda e, p=plan: process_purchase(p),
                                style=ft.ButtonStyle(bgcolor=plan["color"]),
                                width=200
                            )
                        ],
                        spacing=15,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER
                    ),
                    padding=20,
                    width=350,
                    alignment=ft.alignment.center
                ),
                elevation=10,
                height=450
            )
        
        def process_purchase(plan):
            """Обработка покупки (имитация)"""
            conn = sqlite3.connect(DB_NAME)
            c = conn.cursor()
            
            try:
                # Генерируем ключи
                keys = [create_product_key(state.current_user["username"]) 
                    for _ in range(1 if plan["name"] == "Basic" else 2 if plan["name"] == "Pro" else 5)]
                
                # Сохраняем ключи
                for key in keys:
                    c.execute('''INSERT INTO product_keys 
                                (key, user_id, purchase_date) 
                                VALUES (?, ?, ?)''', 
                            (key, state.current_user["id"], datetime.datetime.now()))
                
                # Сохраняем информацию о покупке
                c.execute('''INSERT INTO purchases 
                            (user_id, amount, currency, payment_date) 
                            VALUES (?, ?, ?, ?)''',
                        (state.current_user["id"], plan["price_usd"], "USD", datetime.datetime.now()))
                
                conn.commit()
                
                # Показываем ключи пользователю
                show_keys(keys)
            except Exception as e:
                conn.rollback()
                show_dialog("Ошибка", f"Произошла ошибка: {str(e)}")
            finally:
                conn.close()
        
        def show_keys(keys):
            """Отображение купленных ключей с прокруткой"""
            key_list = ft.Column(
                [
                    ft.Text("Ваши ключи продукта:", size=24, weight=ft.FontWeight.BOLD),
                    ft.Text("Сохраните их в безопасном месте!", color=ft.colors.AMBER),
                    ft.Divider(),
                    *[ft.Text(key, selectable=True, font_family="Courier", size=16) for key in keys],
                    ft.ElevatedButton(
                        "Вернуться в магазин", 
                        on_click=lambda _: page.go("/purchase"),
                        width=200
                    )
                ],
                spacing=15,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                scroll=ft.ScrollMode.AUTO,
                expand=True
            )
            
            page.clean()
            page.add(create_navbar())
            page.add(key_list)
        
        # Основной контент с прокруткой
        plans_row = ft.ResponsiveRow(
            [create_plan_card(plan) for plan in plans],
            spacing=20,
            alignment=ft.MainAxisAlignment.CENTER,
            vertical_alignment=ft.CrossAxisAlignment.START
        )
        
        page.add(
            ft.Column(
                [
                    ft.Text("Выберите тарифный план", size=28, weight=ft.FontWeight.BOLD),
                    ft.Divider(),
                    ft.Container(
                        content=plans_row,
                        expand=True,
                        padding=ft.padding.only(bottom=50)
                    )
                ],
                spacing=30,
                scroll=ft.ScrollMode.AUTO,
                expand=True
            )
        )
    
    def versions_view():
        """Страница с версиями"""
        page.clean()
        page.add(create_navbar())
        
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute('''SELECT version, release_date, changelog, download_url, is_stable, file_size 
                    FROM versions ORDER BY release_date DESC''')
        versions = c.fetchall()
        conn.close()
        
        def create_version_card(version):
            return ft.Card(
                content=ft.Container(
                    content=ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Text(f"MiniOS {version[0]}", size=20, weight=ft.FontWeight.BOLD),
                                    ft.Icon(ft.icons.CHECK_CIRCLE, color=ft.colors.GREEN) if version[4] else 
                                    ft.Icon(ft.icons.BUG_REPORT, color=ft.colors.ORANGE),
                                    ft.Text(version[5], color=ft.colors.GREY)
                                ],
                                spacing=10
                            ),
                            ft.Text(f"Дата выпуска: {version[1]}"),
                            ft.ExpansionTile(
                                title=ft.Text("Список изменений"),
                                controls=[ft.Text(version[2])]
                            ),
                            ft.Row(
                                [
                                    ft.ElevatedButton(
                                        "Скачать",
                                        icon=ft.icons.DOWNLOAD,
                                        on_click=lambda e, url=version[3]: page.launch_url(url))
                                ],
                                alignment=ft.MainAxisAlignment.END
                            )
                        ],
                        spacing=10
                    ),
                    padding=20,
                    width=600
                )
            )
        
        stable_versions = [v for v in versions if v[4]]
        beta_versions = [v for v in versions if not v[4]]
        
        page.add(
            ft.Column(
                [
                    ft.Text("Доступные версии MiniOS", size=28, weight=ft.FontWeight.BOLD),
                    ft.Divider(),
                    ft.Text("Стабильные версии", size=22, weight=ft.FontWeight.BOLD),
                    ft.Column([create_version_card(v) for v in stable_versions], spacing=15),
                    ft.Divider(),
                    ft.Text("Бета-версии", size=22, weight=ft.FontWeight.BOLD),
                    ft.Text("Экспериментальные сборки, могут содержать ошибки", color=ft.colors.ORANGE),
                    ft.Column([create_version_card(v) for v in beta_versions], spacing=15)
                ],
                spacing=20,
                scroll=ft.ScrollMode.AUTO,
                expand=True
            )
        )
    
    def account_view():
        """Личный кабинет"""
        page.clean()
        page.add(create_navbar())
        
        if not state.current_user:
            login_register_view()
            return
        
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        
        # Получаем ключи пользователя
        c.execute('''SELECT key, purchase_date FROM product_keys 
                    WHERE user_id=? ORDER BY purchase_date DESC''', (state.current_user["id"],))
        keys = c.fetchall()
        
        # Получаем покупки
        c.execute('''SELECT amount, currency, payment_date FROM purchases 
                    WHERE user_id=? ORDER BY payment_date DESC''', (state.current_user["id"],))
        purchases = c.fetchall()
        
        conn.close()
        
        # Секция информации о пользователе
        user_info = ft.Column(
            [
                ft.Text(f"Имя пользователя: {state.current_user['username']}"),
                ft.Text(f"Email: {state.current_user['email']}"),
                ft.Row(
                    [
                        ft.Icon(ft.icons.VERIFIED, color=ft.colors.GREEN) if state.current_user["email_verified"] 
                        else ft.Icon(ft.icons.WARNING, color=ft.colors.ORANGE),
                        ft.Text("Email подтвержден" if state.current_user["email_verified"] else "Email не подтвержден")
                    ],
                    spacing=5
                ),
                ft.ElevatedButton(
                    "Отправить подтверждение повторно",
                    on_click=lambda _: send_verification_email(
                        state.current_user["email"],
                        generate_token()
                    ),
                    visible=not state.current_user["email_verified"]
                )
            ],
            spacing=10
        )
        
        # Секция ключей
        keys_section = ft.Column(
            [
                ft.Text("Ваши ключи продукта:", size=20, weight=ft.FontWeight.BOLD),
                ft.ListView(
                    [ft.ListTile(
                        title=ft.Text(key[0], font_family="Courier"),
                        subtitle=ft.Text(f"Приобретен: {key[1]}"),
                    ) for key in keys],
                    height=200
                ) if keys else ft.Text("У вас пока нет ключей продукта")
            ],
            spacing=10
        )
        
        # Секция покупок
        purchases_section = ft.Column(
            [
                ft.Text("История покупок:", size=20, weight=ft.FontWeight.BOLD),
                ft.ListView(
                    [ft.ListTile(
                        title=ft.Text(f"{purchase[0]} {purchase[1]}"),
                        subtitle=ft.Text(f"Дата: {purchase[2]}"),
                    ) for purchase in purchases],
                    height=200
                ) if purchases else ft.Text("У вас пока нет покупок")
            ],
            spacing=10
        )
        
        page.add(
            ft.Column(
                [
                    ft.Text("Мой аккаунт", size=28, weight=ft.FontWeight.BOLD),
                    ft.Divider(),
                    user_info,
                    ft.Divider(),
                    keys_section,
                    ft.Divider(),
                    purchases_section,
                    ft.Divider(),
                    ft.ElevatedButton(
                        "Выйти", 
                        on_click=lambda _: logout(),
                        icon=ft.icons.LOGOUT
                    )
                ],
                spacing=20,
                scroll=ft.ScrollMode.AUTO,
                expand=True
            )
        )
    
    def login_register_view():
        """Форма входа/регистрации"""
        tab_content = ft.Tabs(
            selected_index=0,
            tabs=[
                ft.Tab(text="Вход", content=login_form()),
                ft.Tab(text="Регистрация", content=register_form())
            ]
        )
        
        page.add(
            ft.Column(
                [
                    ft.Text("Вход / Регистрация", size=28, weight=ft.FontWeight.BOLD),
                    ft.Divider(),
                    tab_content
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                width=500
            )
        )
    
    def login_form():
        """Форма входа"""
        username_field = ft.TextField(label="Имя пользователя или email", autofocus=True)
        password_field = ft.TextField(label="Пароль", password=True)
        
        def login(e):
            if not username_field.value or not password_field.value:
                show_snackbar("Заполните все поля", ft.colors.RED)
                return
            
            conn = sqlite3.connect(DB_NAME)
            c = conn.cursor()
            c.execute('''SELECT id, username, email, email_verified, is_admin 
                        FROM users WHERE (username=? OR email=?) AND password=?''',
                     (username_field.value, username_field.value, hash_password(password_field.value)))
            user = c.fetchone()
            conn.close()
            
            if user:
                state.login(user[0])
                show_snackbar(f"Добро пожаловать, {user[1]}!")
                page.go("/account")
            else:
                show_snackbar("Неверное имя пользователя или пароль", ft.colors.RED)
        
        return ft.Column(
            [
                username_field,
                password_field,
                ft.ElevatedButton("Войти", on_click=login, icon=ft.icons.LOGIN)
            ],
            spacing=20
        )
    
    def register_form():
        """Форма регистрации"""
        username_field = ft.TextField(label="Имя пользователя")
        email_field = ft.TextField(label="Email")
        password_field = ft.TextField(label="Пароль", password=True)
        confirm_field = ft.TextField(label="Подтвердите пароль", password=True)
        
        def register(e):
            if not all([username_field.value, email_field.value, password_field.value, confirm_field.value]):
                show_snackbar("Заполните все поля", ft.colors.RED)
                return
            
            if password_field.value != confirm_field.value:
                show_snackbar("Пароли не совпадают", ft.colors.RED)
                return
            
            token = generate_token()
            conn = sqlite3.connect(DB_NAME)
            c = conn.cursor()
            
            try:
                c.execute('''INSERT INTO users 
                            (username, password, email, verification_token) 
                            VALUES (?, ?, ?, ?)''',
                         (username_field.value, hash_password(password_field.value), email_field.value, token))
                user_id = c.lastrowid
                conn.commit()
                
                # Отправляем письмо с подтверждением
                if send_verification_email(email_field.value, token):
                    state.login(user_id)
                    show_dialog(
                        "Регистрация успешна",
                        "На ваш email отправлено письмо с подтверждением. Пожалуйста, проверьте вашу почту.",
                        lambda: page.go("/account")
                    )
                else:
                    show_snackbar("Ошибка отправки письма подтверждения", ft.colors.RED)
            except sqlite3.IntegrityError as e:
                conn.rollback()
                if "username" in str(e):
                    show_snackbar("Имя пользователя уже занято", ft.colors.RED)
                elif "email" in str(e):
                    show_snackbar("Email уже используется", ft.colors.RED)
            finally:
                conn.close()
        
        return ft.Column(
            [
                username_field,
                email_field,
                password_field,
                confirm_field,
                ft.ElevatedButton("Зарегистрироваться", on_click=register, icon=ft.icons.PERSON_ADD)
            ],
            spacing=20
        )
    
    def verify_view(email: str, token: str):
        """Подтверждение email"""
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        
        # Проверяем токен
        c.execute('''SELECT id FROM users 
                    WHERE email=? AND verification_token=?''', (email, token))
        user = c.fetchone()
        
        if user:
            # Подтверждаем email
            c.execute('''UPDATE users 
                        SET email_verified=1, verification_token=NULL 
                        WHERE email=?''', (email,))
            conn.commit()
            
            # Обновляем текущую сессию, если пользователь авторизован
            if state.current_user and state.current_user["email"] == email:
                state.update_user_data()
            
            conn.close()
            
            page.clean()
            page.add(
                ft.Column(
                    [
                        ft.Icon(ft.icons.VERIFIED, size=100, color=ft.colors.GREEN),
                        ft.Text("Email подтвержден!", size=36, weight=ft.FontWeight.BOLD),
                        ft.Text("Ваш email успешно подтвержден. Теперь вы можете совершать покупки."),
                        ft.ElevatedButton(
                            "Перейти в аккаунт", 
                            on_click=lambda _: page.go("/account"),
                            icon=ft.icons.ACCOUNT_CIRCLE
                        )
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=30
                )
            )
        else:
            conn.close()
            page.clean()
            page.add(
                ft.Column(
                    [
                        ft.Icon(ft.icons.ERROR, size=100, color=ft.colors.RED),
                        ft.Text("Ошибка подтверждения", size=36, weight=ft.FontWeight.BOLD),
                        ft.Text("Неверная ссылка подтверждения или email уже был подтвержден."),
                        ft.ElevatedButton(
                            "На главную", 
                            on_click=lambda _: page.go("/"),
                            icon=ft.icons.HOME
                        )
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=30
                )
            )
    def get_all_users():
        """Получение списка всех пользователей"""
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute('''SELECT id, username, email, email_verified, created_at 
                    FROM users ORDER BY created_at DESC''')
        users = c.fetchall()
        conn.close()
        return users

    def get_all_versions():
        """Получение списка всех версий"""
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute('''SELECT id, version, release_date, is_stable 
                    FROM versions ORDER BY release_date DESC''')
        versions = c.fetchall()
        conn.close()
        return versions

    def admin_panel_view():
        """Админ-панель с вкладками управления версиями и пользователями"""
        if not state.current_user or not state.current_user.get("is_admin"):
            page.go("/")
            return

        # Функция удаления пользователя
        def delete_user(user_id):
            if user_id == state.current_user["id"]:
                show_snackbar("Нельзя удалить себя!", ft.colors.RED)
                return
                
            conn = sqlite3.connect(DB_NAME)
            try:
                # Удаляем связанные данные пользователя
                conn.execute("DELETE FROM product_keys WHERE user_id=?", (user_id,))
                conn.execute("DELETE FROM purchases WHERE user_id=?", (user_id,))
                conn.execute("DELETE FROM users WHERE id=?", (user_id,))
                conn.commit()
                show_snackbar("Пользователь удален", ft.colors.GREEN)
                admin_panel_view()
            except Exception as e:
                conn.rollback()
                show_snackbar(f"Ошибка: {str(e)}", ft.colors.RED)
            finally:
                conn.close()

        # Функция удаления версии
        def delete_version(version_id):
            conn = sqlite3.connect(DB_NAME)
            try:
                conn.execute("DELETE FROM versions WHERE id=?", (version_id,))
                conn.commit()
                show_snackbar("Версия удалена", ft.colors.GREEN)
                admin_panel_view()
            except Exception as e:
                conn.rollback()
                show_snackbar(f"Ошибка: {str(e)}", ft.colors.RED)
            finally:
                conn.close()

        # Вкладка пользователей
        def users_tab_content():
            conn = sqlite3.connect(DB_NAME)
            c = conn.cursor()
            c.execute("SELECT id, username, email, email_verified, created_at FROM users")
            users = c.fetchall()
            conn.close()

            users_list = ft.Column(scroll=ft.ScrollMode.AUTO)
            for user in users:
                users_list.controls.append(
                    ft.Card(
                        ft.Container(
                            ft.Column([
                                ft.Text(f"ID: {user[0]}", weight=ft.FontWeight.BOLD),
                                ft.Text(f"Логин: {user[1]}"),
                                ft.Text(f"Email: {user[2]}"),
                                ft.Row([
                                    ft.Icon(ft.icons.CHECK if user[3] else ft.icons.CLOSE),
                                    ft.Text("Подтвержден" if user[3] else "Не подтвержден")
                                ]),
                                ft.Text(f"Регистрация: {user[4]}"),
                                ft.ElevatedButton(
                                    "Удалить",
                                    on_click=lambda e, uid=user[0]: delete_user(uid),
                                    icon=ft.icons.DELETE,
                                    color=ft.colors.RED
                                )
                            ], spacing=5),
                            padding=10
                        )
                    )
                )
            
            return ft.Column([
                ft.Text("Управление пользователями", size=24),
                ft.Divider(),
                users_list
            ], expand=True)

        # Вкладка версий
        def versions_tab_content():
            conn = sqlite3.connect(DB_NAME)
            c = conn.cursor()
            c.execute("SELECT id, version, release_date, is_stable, download_url FROM versions")
            versions = c.fetchall()
            conn.close()

            versions_list = ft.Column(scroll=ft.ScrollMode.AUTO)
            for version in versions:
                versions_list.controls.append(
                    ft.Card(
                        ft.Container(
                            ft.Column([
                                ft.Text(f"ID: {version[0]}", weight=ft.FontWeight.BOLD),
                                ft.Text(f"Версия: {version[1]}"),
                                ft.Text(f"Дата: {version[2]}"),
                                ft.Row([
                                    ft.Icon(ft.icons.CHECK if version[3] else ft.icons.WARNING),
                                    ft.Text("Стабильная" if version[3] else "Бета")
                                ]),
                                ft.Text(f"Ссылка: {version[4][:30]}..."),
                                ft.ElevatedButton(
                                    "Удалить",
                                    on_click=lambda e, vid=version[0]: delete_version(vid),
                                    icon=ft.icons.DELETE,
                                    color=ft.colors.RED
                                )
                            ], spacing=5),
                            padding=10
                        )
                    )
                )

            # Форма добавления версии
            version_field = ft.TextField(label="Версия")
            date_field = ft.TextField(label="Дата выпуска", value=datetime.date.today().isoformat())
            changelog_field = ft.TextField(label="Список изменений", multiline=True)
            url_field = ft.TextField(label="Ссылка для скачивания")
            stable_field = ft.Checkbox(label="Стабильная версия", value=True)

            def add_version(e):
                if not all([version_field.value, date_field.value, url_field.value]):
                    show_snackbar("Заполните обязательные поля", ft.colors.RED)
                    return
                
                conn = sqlite3.connect(DB_NAME)
                try:
                    c = conn.cursor()
                    c.execute('''INSERT INTO versions 
                                (version, release_date, changelog, download_url, is_stable) 
                                VALUES (?, ?, ?, ?, ?)''',
                            (version_field.value, date_field.value, 
                            changelog_field.value, url_field.value, stable_field.value))
                    conn.commit()
                    show_snackbar("Версия добавлена", ft.colors.GREEN)
                    versions_tab_content()  # Обновляем список
                except sqlite3.IntegrityError:
                    show_snackbar("Версия уже существует", ft.colors.RED)
                finally:
                    conn.close()

            return ft.Column([
                ft.Text("Управление версиями", size=24),
                ft.Divider(),
                versions_list,
                ft.Divider(),
                ft.Text("Добавить новую версию", size=20),
                version_field,
                date_field,
                changelog_field,
                url_field,
                stable_field,
                ft.ElevatedButton("Добавить", on_click=add_version, icon=ft.icons.ADD)
            ], expand=True)

        # Создаем вкладки
        tabs = ft.Tabs(
            tabs=[
                ft.Tab(text="Пользователи", icon=ft.icons.PEOPLE, content=users_tab_content()),
                ft.Tab(text="Версии", icon=ft.icons.CODE, content=versions_tab_content())
            ],
            expand=True
        )

        page.clean()
        page.add(create_navbar())
        page.add(tabs)
    
    def logout():
        """Выход из системы"""
        state.logout()
        show_snackbar("Вы успешно вышли из системы")
        page.go("/")
    
    # ====================== МАРШРУТИЗАЦИЯ ======================
    def route_change(e):
        """Обработчик изменения маршрута"""
        if page.route.startswith("/verify?"):
            params = parse_qs(page.route[8:])  # Пропускаем "/verify?"
            email = params.get("email", [""])[0]
            token = params.get("token", [""])[0]
            verify_view(email, token)
        elif page.route == "/":
            home_view()
        elif page.route == "/validate":
            validate_view()
        elif page.route == "/purchase":
            purchase_view()
        elif page.route == "/account":
            account_view()
        elif page.route == "/versions":
            versions_view()
        elif page.route == "/admin":
            admin_panel_view()
        else:
            page.go("/")
    
    page.on_route_change = route_change
    page.go(page.route)

# Запуск приложения
if __name__ == "__main__":
    ft.app(target=main, view=ft.WEB_BROWSER, port=8501)