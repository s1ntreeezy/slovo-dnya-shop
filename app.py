from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from models import db, User, Product, Promocode, WordOfTheDay
from datetime import datetime, timedelta
import os
import random
import string

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///shop.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Функция для очистки истёкших промокодов
def cleanup_expired_promocodes():
    """Удаляет все истёкшие промокоды из базы данных"""
    try:
        expired_promocodes = Promocode.query.filter(
            Promocode.valid_until < datetime.utcnow()
        ).all()
        
        for promocode in expired_promocodes:
            db.session.delete(promocode)
        
        if expired_promocodes:
            db.session.commit()
            print(f"Удалено {len(expired_promocodes)} истёкших промокодов")
        
        return len(expired_promocodes)
    except Exception as e:
        print(f"Ошибка при очистке промокодов: {e}")
        db.session.rollback()
        return 0

# Функция для очистки истёкших слов дня
def cleanup_expired_words():
    """Удаляет все истёкшие слова дня из базы данных"""
    try:
        expired_words = WordOfTheDay.query.filter(
            WordOfTheDay.valid_until < datetime.utcnow()
        ).all()
        
        for word in expired_words:
            db.session.delete(word)
        
        if expired_words:
            db.session.commit()
            print(f"Удалено {len(expired_words)} истёкших слов дня")
        
        return len(expired_words)
    except Exception as e:
        print(f"Ошибка при очистке слов дня: {e}")
        db.session.rollback()
        return 0

# Функция для очистки всех истёкших данных
def cleanup_expired_data():
    """Очищает все истёкшие данные (промокоды и слова дня)"""
    promocodes_cleaned = cleanup_expired_promocodes()
    words_cleaned = cleanup_expired_words()
    return promocodes_cleaned, words_cleaned

# Создание базы данных и админа при первом запуске
def init_db():
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(is_admin=True).first():
            admin = User(username='admin', email='admin@example.com', is_admin=True)
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()

# Маршруты для аутентификации
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        
        if User.query.filter_by(username=username).first():
            flash('Пользователь с таким именем уже существует')
            return redirect(url_for('register'))
        
        if User.query.filter_by(email=email).first():
            flash('Пользователь с таким email уже существует')
            return redirect(url_for('register'))
        
        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        
        flash('Регистрация успешна! Теперь вы можете войти.')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('index'))
        
        flash('Неверное имя пользователя или пароль')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

# Главная страница
@app.route('/')
def index():
    # Автоматическая очистка истёкших данных при каждом запросе к главной странице
    cleanup_expired_data()
    products = Product.query.all()
    return render_template('index.html', products=products)

# Мини-игра
@app.route('/game')
@login_required
def game():
    # Очистка истёкших данных перед игрой
    cleanup_expired_data()
    word_of_day = WordOfTheDay.query.order_by(WordOfTheDay.created_at.desc()).first()
    if not word_of_day or word_of_day.valid_until < datetime.utcnow():
        flash('Слово дня еще не установлено или срок его действия истек')
        return redirect(url_for('index'))
    
    # Проверяем, выигрывал ли пользователь уже промокод за это слово дня
    has_won_today = Promocode.query.filter_by(
        user_id=current_user.id,
        valid_until=word_of_day.valid_until
    ).first() is not None

    return render_template('game.html', word=word_of_day.word, has_won_today=has_won_today)

# API для проверки слова
@app.route('/check_word', methods=['POST'])
@login_required
def check_word():
    # Очистка истёкших данных перед проверкой
    cleanup_expired_data()
    data = request.get_json()
    user_word = data.get('word', '')
    word_of_day = WordOfTheDay.query.order_by(WordOfTheDay.created_at.desc()).first()
    
    if not word_of_day or word_of_day.valid_until < datetime.utcnow():
        return jsonify({'success': False, 'message': 'Слово дня недействительно'})
    
    if user_word.lower() == word_of_day.word.lower():
        # Проверяем, есть ли у пользователя уже промокод, связанный с текущим словом дня (по сроку действия)
        existing_promocode = Promocode.query.filter_by(
            user_id=current_user.id,
            valid_until=word_of_day.valid_until
        ).first()

        if existing_promocode:
            return jsonify({
                'success': False,
                'message': 'Вы уже получили промокод за это слово дня. Используйте его!'
            })

        # Если промокода нет, генерируем новый
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        promocode = Promocode(
            code=code,
            discount_percent=word_of_day.discount_percent,
            valid_until=word_of_day.valid_until,
            user_id=current_user.id
        )
        db.session.add(promocode)
        db.session.commit()
        return jsonify({
            'success': True,
            'message': 'Поздравляем! Вы получили промокод!',
            'promocode': code
        })
    
    return jsonify({'success': False, 'message': 'Неверное слово'})

# Административные маршруты
@app.route('/admin')
@login_required
def admin():
    if not current_user.is_admin:
        flash('У вас нет доступа к этой странице')
        return redirect(url_for('index'))
    return render_template('admin.html')

@app.route('/admin/set_word', methods=['POST'])
@login_required
def set_word():
    if not current_user.is_admin:
        return jsonify({'success': False, 'message': 'Доступ запрещен'})
    
    data = request.get_json()
    word = data.get('word')
    discount = data.get('discount')
    valid_hours = data.get('valid_hours', 24)
    
    if not all([word, discount]):
        return jsonify({'success': False, 'message': 'Не все поля заполнены'})
    
    word_of_day = WordOfTheDay(
        word=word,
        discount_percent=discount,
        valid_until=datetime.utcnow() + timedelta(hours=valid_hours)
    )
    db.session.add(word_of_day)
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Слово дня установлено'})

@app.route('/admin/add_product', methods=['POST'])
@login_required
def add_product():
    if not current_user.is_admin:
        return jsonify({'success': False, 'message': 'Доступ запрещен'})
    
    data = request.get_json()
    product = Product(
        name=data.get('name'),
        description=data.get('description'),
        price=data.get('price'),
        stock=data.get('stock'),
        image_url=data.get('image_url')
    )
    
    try:
        db.session.add(product)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Товар успешно добавлен'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)})

@app.route('/profile')
@login_required
def profile():
    # Очистка истёкших данных перед показом профиля
    cleanup_expired_data()
    promocodes = Promocode.query.filter_by(user_id=current_user.id).order_by(Promocode.created_at.desc()).all()
    now = datetime.utcnow()
    # Переводим все даты в московское время (UTC+3)
    for promo in promocodes:
        promo.local_valid_until = promo.valid_until + timedelta(hours=3)
    local_now = now + timedelta(hours=3)
    return render_template('profile.html', promocodes=promocodes, now=local_now)

def get_cart():
    return session.get('cart', {})

def save_cart(cart):
    session['cart'] = cart

@app.route('/cart')
@login_required
def cart():
    # Очистка истёкших данных перед показом корзины
    cleanup_expired_data()
    cart = get_cart()
    products = []
    total = 0
    for product_id, quantity in cart.items():
        product = Product.query.get(int(product_id))
        if product:
            products.append({'product': product, 'quantity': quantity})
            total += product.price * quantity
    # Промокоды пользователя
    promocodes = Promocode.query.filter_by(user_id=current_user.id, is_used=False).all()
    applied_code = session.get('applied_promocode')
    discount = 0
    discount_code = None
    # Проверяем, не истёк ли или не использован ли промокод, и очищаем из сессии если нужно
    if applied_code:
        promo = Promocode.query.filter_by(code=applied_code, user_id=current_user.id).first()
        if not promo or promo.is_used or promo.valid_until <= datetime.utcnow():
            session.pop('applied_promocode', None)
        else:
            discount = promo.discount_percent
            discount_code = promo.code
    total_with_discount = total * (1 - discount / 100)
    return render_template('cart.html', products=products, total=total, promocodes=promocodes, discount=discount, discount_code=discount_code, total_with_discount=total_with_discount)

@app.route('/add_to_cart/<int:product_id>')
@login_required
def add_to_cart(product_id):
    cart = get_cart()
    cart[str(product_id)] = cart.get(str(product_id), 0) + 1
    save_cart(cart)
    flash('Товар добавлен в корзину')
    return redirect(url_for('index'))

@app.route('/remove_from_cart/<int:product_id>')
@login_required
def remove_from_cart(product_id):
    cart = get_cart()
    if str(product_id) in cart:
        del cart[str(product_id)]
        save_cart(cart)
        flash('Товар удалён из корзины')
    return redirect(url_for('cart'))

@app.route('/apply_promocode', methods=['POST'])
@login_required
def apply_promocode():
    # Очистка истёкших данных перед применением промокода
    cleanup_expired_data()
    code = request.form.get('promocode')
    promo = Promocode.query.filter_by(code=code, user_id=current_user.id, is_used=False).first()
    if promo and promo.valid_until > datetime.utcnow():
        session['applied_promocode'] = code
        promo.is_used = True
        db.session.commit()
        flash(f'Промокод {code} применён и больше не может быть использован!')
    else:
        flash('Промокод недействителен, истёк или уже использован')
    return redirect(url_for('cart'))

@app.route('/admin/products')
@login_required
def admin_products():
    if not current_user.is_admin:
        flash('У вас нет доступа к этой странице')
        return redirect(url_for('index'))
    # Очистка истёкших данных перед показом товаров
    cleanup_expired_data()
    products = Product.query.order_by(Product.id.desc()).all()
    return render_template('admin_products.html', products=products)

@app.route('/admin/edit_product/<int:product_id>', methods=['GET', 'POST'])
@login_required
def edit_product(product_id):
    if not current_user.is_admin:
        flash('У вас нет доступа к этой странице')
        return redirect(url_for('index'))
    product = Product.query.get_or_404(product_id)
    if request.method == 'POST':
        product.name = request.form.get('name')
        product.description = request.form.get('description')
        product.price = float(request.form.get('price'))
        product.stock = int(request.form.get('stock'))
        product.image_url = request.form.get('image_url')
        db.session.commit()
        flash('Товар успешно обновлён')
        return redirect(url_for('admin_products'))
    return render_template('edit_product.html', product=product)

@app.route('/admin/delete_product/<int:product_id>', methods=['POST'])
@login_required
def delete_product(product_id):
    if not current_user.is_admin:
        flash('У вас нет доступа к этой странице')
        return redirect(url_for('index'))
    product = Product.query.get_or_404(product_id)
    db.session.delete(product)
    db.session.commit()
    flash('Товар удалён')
    return redirect(url_for('admin_products'))

if __name__ == '__main__':
    init_db()
    app.run(debug=True) 