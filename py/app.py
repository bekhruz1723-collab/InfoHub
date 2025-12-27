import os
import re
import json
import requests
from flask import Flask, render_template, redirect, url_for, flash, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.utils import secure_filename
from models import db, User, Task, TaskStep
import plotly
import plotly.graph_objs as go
from datetime import datetime, timezone

app = Flask(__name__)
# Берем секретный ключ из настроек сервера или используем дефолтный
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', '17236458Bb')

# --- НАСТРОЙКА БАЗЫ ДАННЫХ ---
# Render выдает адрес базы, начинающийся на postgres://, но SQLAlchemy требует postgresql://
database_url = os.environ.get('DATABASE_URL')
if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

# Если есть переменная DATABASE_URL (на Render), используем её, иначе локальный файл
app.config['SQLALCHEMY_DATABASE_URI'] = database_url or 'sqlite:///site.db'
app.config['UPLOAD_FOLDER'] = 'static/uploads'

db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

OPENWEATHER_KEY = "1a080bf136d2a532b90934361f5318e0"

# Создаем таблицы при первом запуске
with app.app_context():
    db.create_all()

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

def validate_nickname(nickname):
    return bool(re.match(r'^[a-zA-Z0-9_]+$', nickname))

def calculate_productivity(user_id):
    tasks = Task.query.filter_by(user_id=user_id).all()
    if not tasks:
        return None

    score_overdue = 0.0
    score_in_progress = 0.0
    score_completed = 0.0

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    for task in tasks:
        ratio = 0.0
        if task.steps:
            total_steps = len(task.steps)
            done_steps = len([s for s in task.steps if s.completed])
            if total_steps > 0:
                ratio = done_steps / total_steps
        else:
            ratio = 1.0 if task.completed else 0.0

        if task.completed and ratio < 1.0:
            ratio = 1.0

        score_completed += ratio

        remainder = 1.0 - ratio
        if remainder > 0:
            if task.deadline and task.deadline < now:
                score_overdue += remainder
            else:
                score_in_progress += remainder

    labels = ["Выполнено", "В процессе", "Просрочено"]
    values = [score_completed, score_in_progress, score_overdue]
    colors = ["#10b981", "#facc15", "#ef4444"]

    if sum(values) == 0:
        return None

    fig = go.Figure(data=[go.Pie(
        labels=labels,
        values=values,
        hole=0.6,
        marker=dict(colors=colors),
        textinfo='percent',
        hoverinfo='label+value',
        sort=False
    )])

    fig.update_layout(
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font_color="var(--text-color)",
        margin=dict(t=10, b=10, l=10, r=10),
        height=220,
        showlegend=False
    )
    fig.update_layout(font_color="#888")

    return json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        nickname = request.form.get('nickname')
        password = request.form.get('password')
        username = request.form.get('username')

        if not validate_nickname(nickname):
            flash('Никнейм должен содержать только латиницу и цифры!', 'danger')
            return redirect(url_for('register'))
        if len(password) < 8:
            flash('Пароль должен быть минимум 8 символов!', 'danger')
            return redirect(url_for('register'))
        if User.query.filter_by(nickname=nickname).first():
            flash('Этот никнейм уже занят.', 'danger')
            return redirect(url_for('register'))

        hashed_pw = generate_password_hash(password)
        new_user = User(nickname=nickname, username=username, password_hash=hashed_pw)
        db.session.add(new_user)
        db.session.commit()
        login_user(new_user)
        return redirect(url_for('dashboard'))
    return render_template('auth.html', mode='register')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        nickname = request.form.get('nickname')
        password = request.form.get('password')
        user = User.query.filter_by(nickname=nickname).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('dashboard'))
        else:
            flash('Неверный ник или пароль', 'danger')
    return render_template('auth.html', mode='login')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/delete_account', methods=['POST'])
@login_required
def delete_account():
    user = db.session.get(User, current_user.id)
    if user:
        logout_user()
        db.session.delete(user)
        db.session.commit()
        flash('Аккаунт удален.', 'success')
    return redirect(url_for('register'))

def get_tasks_list_data(user_id):
    tasks = Task.query.filter_by(user_id=user_id).order_by(Task.created_at.desc()).all()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for task in tasks:
        total = len(task.steps)
        if total > 0:
            done = len([s for s in task.steps if s.completed])
            task.progress = int((done / total) * 100)
        else:
            task.progress = 100 if task.completed else 0
    return tasks, now

@app.route('/')
@app.route('/dashboard')
@login_required
def dashboard():
    tasks, now = get_tasks_list_data(current_user.id)
    graphJSON = calculate_productivity(current_user.id)
    return render_template('dashboard.html', tasks=tasks, graphJSON=graphJSON, now=now)

@app.route('/dashboard/tasks_partial')
@login_required
def dashboard_tasks_partial():
    tasks, now = get_tasks_list_data(current_user.id)
    graphJSON = calculate_productivity(current_user.id)
    return jsonify({
        'html': render_template('task_list.html', tasks=tasks, now=now),
        'graphJSON': graphJSON
    })

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        current_user.username = request.form.get('username')
        current_user.bio = request.form.get('bio')
        age = request.form.get('age')
        if age: current_user.age = int(age)
        current_user.gender = request.form.get('gender')
        current_user.goals = request.form.get('goals')
        if 'avatar' in request.files:
            file = request.files['avatar']
            if file.filename != '':
                filename = secure_filename(f"{current_user.id}_{file.filename}")
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                current_user.avatar = filename
        db.session.commit()
        flash('Профиль обновлен!', 'success')
        return redirect(url_for('profile'))
    return render_template('profile.html', user=current_user)

@app.route('/search')
@login_required
def search():
    return render_template('search.html')

@app.route('/api/search')
@login_required
def api_search():
    query = request.args.get('q', '')
    if not query:
        return jsonify([])
    users = User.query.filter(User.nickname.contains(query) | User.username.contains(query)).limit(10).all()
    results = [{
        'username': u.username,
        'nickname': u.nickname,
        'avatar': u.avatar,
        'bio': u.bio[:100] + '...' if u.bio else 'Нет описания'
    } for u in users]
    return jsonify(results)

@app.route('/u/<nickname>')
@login_required
def public_profile(nickname):
    user = User.query.filter_by(nickname=nickname).first_or_404()
    if user.id == current_user.id:
        return redirect(url_for('profile'))

    tasks = Task.query.filter_by(user_id=user.id, is_public=True).order_by(Task.created_at.desc()).all()
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    for task in tasks:
        total = len(task.steps)
        if total > 0:
            done = len([s for s in task.steps if s.completed])
            task.progress = int((done / total) * 100)
        else:
            task.progress = 100 if task.completed else 0

    graphJSON = calculate_productivity(user.id)
    return render_template('public_profile.html', user=user, tasks=tasks, graphJSON=graphJSON, now=now)

@app.route('/api/add_task', methods=['POST'])
@login_required
def add_task():
    data = request.json
    deadline_obj = None
    if data.get('deadline'):
        deadline_obj = datetime.strptime(data.get('deadline'), '%Y-%m-%d')

    new_task = Task(
        title=data['title'],
        deadline=deadline_obj,
        user_id=current_user.id,
        is_public=data.get('is_public', False)
    )
    db.session.add(new_task)
    db.session.commit()

    steps = data.get('steps', [])
    for step_data in steps:
        if step_data.get('text', '').strip():
            step = TaskStep(
                content=step_data['text'],
                completed=step_data.get('checked', False),
                task_id=new_task.id
            )
            db.session.add(step)

    db.session.commit()
    return jsonify({'status': 'success'})

@app.route('/api/toggle_step/<int:step_id>', methods=['POST'])
@login_required
def toggle_step(step_id):
    step = TaskStep.query.get_or_404(step_id)
    if step.task.user_id != current_user.id:
        return jsonify({'error': 'Forbidden'}), 403

    step.completed = not step.completed
    task = step.task

    if task.steps:
        all_done = all(s.completed for s in task.steps)
        task.completed = all_done

    db.session.commit()
    return jsonify({'status': 'success'})

@app.route('/api/toggle_task/<int:task_id>', methods=['POST'])
@login_required
def toggle_task(task_id):
    task = Task.query.get_or_404(task_id)
    if task.user_id != current_user.id:
        return jsonify({'error': 'Forbidden'}), 403

    new_state = not task.completed
    task.completed = new_state

    for step in task.steps:
        step.completed = new_state

    db.session.commit()
    return jsonify({'status': 'success'})

@app.route('/api/get_weather')
@login_required
def get_weather():
    city = request.args.get('city', 'Moscow')
    url = f"https://api.openweathermap.org/data/2.5/forecast?q={city}&appid={OPENWEATHER_KEY}&units=metric&lang=ru"
    try:
        response = requests.get(url)
        return jsonify(response.json())
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/get_currency')
@login_required
def get_currency():
    base = request.args.get('from', 'USD')
    target = request.args.get('to', 'RUB')
    url = f"https://hexarate.paikama.co/api/rates/latest/{base}?target={target}"
    try:
        response = requests.get(url)
        data = response.json()
        if response.status_code == 200:
            return jsonify(data)
        return jsonify({'error': 'API Error'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)