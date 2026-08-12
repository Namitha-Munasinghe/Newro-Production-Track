from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timezone, timedelta
import hmac
import os
import sys

# Running as a PyInstaller-frozen desktop build vs. the normal `python app.py` web app.
# Frozen builds extract templates/static into a temp dir (sys._MEIPASS) and must store
# the database somewhere durable outside that temp dir instead.
FROZEN = getattr(sys, 'frozen', False)
BASE_DIR = sys._MEIPASS if FROZEN else os.path.dirname(os.path.abspath(__file__))

def get_app_data_dir():
    """Writable, persistent per-user folder for the SQLite database (desktop build only)."""
    if sys.platform == 'win32':
        base = os.environ.get('APPDATA') or os.path.expanduser('~')
    elif sys.platform == 'darwin':
        base = os.path.expanduser('~/Library/Application Support')
    else:
        base = os.environ.get('XDG_DATA_HOME') or os.path.expanduser('~/.local/share')
    path = os.path.join(base, 'NewroOperations')
    os.makedirs(path, exist_ok=True)
    return path

# 1. Initialize Flask App first so @app decorators work
app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, 'templates'),
    static_folder=os.path.join(BASE_DIR, 'static')
)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'poultry_secret_key')

if FROZEN:
    db_path = os.path.join(get_app_data_dir(), 'newro_poultry.db')
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + db_path
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///newro_poultry.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Session PIN gate: 30 minutes of inactivity logs the terminal out.
# SESSION_REFRESH_EACH_REQUEST (Flask default: True) makes this a sliding
# idle timeout rather than a fixed 30 minutes from login.
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)
app.config['SESSION_REFRESH_EACH_REQUEST'] = True

# Endpoints reachable without being logged in.
PUBLIC_ENDPOINTS = {'login', 'static'}

def is_safe_redirect_target(target):
    """Only allow same-site relative redirects for the post-login `next` param."""
    return bool(target) and target.startswith('/') and not target.startswith('//')

# --- MODELS ---

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)

class EntryLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, default=lambda: datetime.now(timezone.utc).date())
    shift = db.Column(db.String(10), nullable=False) # 'day' or 'night'
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    birds = db.Column(db.Integer, nullable=True)
    weight = db.Column(db.Float, nullable=True)
    
    product = db.relationship('Product', backref=db.backref('logs', lazy=True))

class ShiftSummaryInput(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(10), nullable=False)
    
    day_before_birds = db.Column(db.Integer, default=0)
    day_before_weight = db.Column(db.Float, default=0.0)
    night_before_birds = db.Column(db.Integer, default=0)
    night_before_weight = db.Column(db.Float, default=0.0)

    __table_args__ = (db.UniqueConstraint('date', name='_date_summary_uc'),)

class SystemSetting(db.Model):
    """Small key/value store for application-wide supervisor settings."""
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.String(255), nullable=False)

def get_system_pin():
    """Return the configured master PIN, creating the default on first use."""
    setting = SystemSetting.query.filter_by(key='master_pin').first()
    if not setting:
        setting = SystemSetting(key='master_pin', value='1234')
        db.session.add(setting)
        db.session.commit()
    return setting.value

def verify_system_pin(entered_pin):
    """Accept the stored PIN or the emergency environment override key."""
    candidate = str(entered_pin or '')
    stored_pin = get_system_pin()
    override_key = os.environ.get('MASTER_OVERRIDE_KEY', '')
    return (
        hmac.compare_digest(candidate, stored_pin)
        or (bool(override_key) and hmac.compare_digest(candidate, override_key))
    )

# --- DATABASE SEEDING ---
def seed_products():
    initial_products = [
        {"code": "NW00001", "name": "Fresh Chicken"},
        {"code": "NW00002", "name": "S/L Chicken"},
        {"code": "NW00003", "name": "Full Chicken"},
        {"code": "NW00004", "name": "Half Chicken"},
        {"code": "NW00006", "name": "Parent Chicken"},
        {"code": "NW00008", "name": "S/L Chicken Fresh"},
        {"code": "NW00011", "name": "Breast - Fresh"},
        {"code": "NW00012", "name": "Breast - Frozen"},
        {"code": "NW00021", "name": "Thigh - Fresh"},
        {"code": "NW00022", "name": "Thigh - M (90g-100g)"},
        {"code": "NW00023", "name": "Thigh - L (100g-120g)"},
        {"code": "NW00024", "name": "Thigh S/L XL (120g-140g)"},
        {"code": "NW00026", "name": "Drumstick - Fresh"},
        {"code": "NW00028", "name": "Drumstick - M (90g-100g)"},
        {"code": "NW00029", "name": "Drumstick - L (100g-120g)"},
        {"code": "NW00031", "name": "Wings - Fresh"},
        {"code": "NW00032", "name": "S/L Wings"},
        {"code": "NW00033", "name": "Wings - Factory Damage"},
        {"code": "NW00036", "name": "Neck - Frozen"},
        {"code": "NW00037", "name": "Neck - Fresh"},
        {"code": "NW00046", "name": "Off Cut - Fresh"},
        {"code": "NW00047", "name": "Chicken Paw (Feet)"},
        {"code": "NW00048", "name": "Chicken Head"},
        {"code": "NW00049", "name": "Off Cut - Frozen"},
        {"code": "NW00051", "name": "Liver - Frozen"},
        {"code": "NW00052", "name": "Liver - Fresh"},
        {"code": "NW00056", "name": "Gizzard - Frozen"},
        {"code": "NW00057", "name": "Gizzard - Fresh"},
        {"code": "NW00061", "name": "Giblet"},
        {"code": "NW00071", "name": "Curry Pieces - 01"},
        {"code": "NW00072", "name": "Curry Pieces - 02"},
        {"code": "NW00073", "name": "Curry Pieces - 500g"},
        {"code": "NW00074", "name": "Super Catering"},
        {"code": "NW00076", "name": "Pet Food"},
        {"code": "NW00079", "name": "Bite Mix"},
        {"code": "NW00080", "name": "Drumstick XL (120g-140g)"},
        {"code": "NW00081", "name": "Drumstick - Frozen"},
        {"code": "NW00082", "name": "Wings - Frozen"},
        {"code": "NW00083", "name": "Thigh - Frozen"},
        {"code": "NW00092", "name": "Family Pack 400g"},
        {"code": "NW00093", "name": "Family Pack 700g"},
        {"code": "NW00095", "name": "Family Pack 5kg Skin On"},
        {"code": "NW00096", "name": "Family Pack R/M"},
        {"code": "NW00101", "name": "Whole Skinless Fresh Chicken"},
        {"code": "NW00102", "name": "Fresh Whole Chicken"},
        {"code": "NW00103", "name": "Whole Skinless Fresh Value Pack"},
        {"code": "NW00104", "name": "Fresh Whole Value Pack"},
        {"code": "NW00106", "name": "Nonpack Skin Less - With Neck"}
    ]
    
    if Product.query.count() == 0:
        for p in initial_products:
            db.session.add(Product(code=p["code"], name=p["name"]))
        db.session.commit()

with app.app_context():
    db.create_all()
    seed_products()
    get_system_pin()

@app.before_request
def require_login():
    if request.endpoint in PUBLIC_ENDPOINTS or request.endpoint is None:
        return
    if not session.get('authenticated'):
        next_target = request.full_path if request.query_string else request.path
        return redirect(url_for('login', next=next_target))

# --- AUTH ROUTES ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    next_url = request.values.get('next', '')
    if not is_safe_redirect_target(next_url):
        next_url = ''

    if request.method == 'POST':
        if verify_system_pin(request.form.get('pin')):
            session.clear()
            session['authenticated'] = True
            session.permanent = True
            return redirect(next_url or url_for('home'))
        flash("Incorrect PIN. Please try again.", "danger")
        return redirect(url_for('login', next=next_url))

    if session.get('authenticated'):
        return redirect(next_url or url_for('home'))

    return render_template('login.html', next=next_url)

@app.route('/logout')
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for('login'))

# --- MAIN ROUTES ---

@app.route('/')
def home():
    selected_date_str = request.args.get('date') or datetime.now(timezone.utc).strftime('%Y-%m-%d')
    entry_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
    
    products = Product.query.order_by(Product.code).all()
    logs = EntryLog.query.filter_by(date=entry_date).all()
    
    existing_logs = {}
    for log in logs:
        if log.product_id not in existing_logs:
            existing_logs[log.product_id] = {'day_birds': 0, 'day_weight': 0.0, 'night_birds': 0, 'night_weight': 0.0}
        
        if log.shift == 'day':
            existing_logs[log.product_id]['day_birds'] += (log.birds or 0)
            existing_logs[log.product_id]['day_weight'] += (log.weight or 0.0)
        elif log.shift == 'night':
            existing_logs[log.product_id]['night_birds'] += (log.birds or 0)
            existing_logs[log.product_id]['night_weight'] += (log.weight or 0.0)

    return render_template('index.html', products=products, current_date=selected_date_str, existing_logs=existing_logs)

@app.route('/entry')
def batch_entry():
    selected_date_str = request.args.get('date') or datetime.now(timezone.utc).strftime('%Y-%m-%d')
    initial_shift = request.args.get('shift', 'night')
    if initial_shift not in ('day', 'night'):
        initial_shift = 'night'
    products = Product.query.order_by(Product.code).all()
    return render_template('batch_entry.html', products=products, current_date=selected_date_str, initial_shift=initial_shift)

# --- BATCH ENTRY API ENDPOINTS ---

@app.route('/api/get-saved-batches', methods=['GET'])
def get_saved_batches():
    selected_date_str = request.args.get('date') or datetime.now(timezone.utc).strftime('%Y-%m-%d')
    shift = request.args.get('shift', 'day')

    try:
        entry_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
        logs = EntryLog.query.filter_by(date=entry_date, shift=shift).all()

        grouped_entries = {}
        for log in logs:
            if log.product_id not in grouped_entries:
                grouped_entries[log.product_id] = []
            
            grouped_entries[log.product_id].append({
                'birds': log.birds if log.birds is not None else '',
                'weight': log.weight if log.weight is not None else ''
            })

        entries = [
            {'product_id': p_id, 'batches': batches}
            for p_id, batches in grouped_entries.items()
        ]

        return jsonify({'status': 'success', 'entries': entries})

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/save-batches', methods=['POST'])
def save_batches():
    data = request.get_json()
    if not data:
        return jsonify({'status': 'error', 'message': 'Invalid data payload'}), 400

    selected_date_str = data.get('date')
    shift = data.get('shift')
    entries = data.get('entries', [])

    try:
        entry_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
        if entry_date < datetime.now(timezone.utc).date() and not verify_system_pin(data.get('auth_pin')):
            return jsonify({
                'status': 'error',
                'message': 'Supervisor PIN is required to edit historical entries.'
            }), 403

        for entry in entries:
            product_id = entry.get('product_id')
            batches = entry.get('batches', [])

            EntryLog.query.filter_by(date=entry_date, shift=shift, product_id=product_id).delete()

            for b in batches:
                raw_birds = b.get('birds')
                raw_weight = b.get('weight')
                
                birds_val = int(raw_birds) if raw_birds not in (None, '', 'null') else None
                weight_val = float(raw_weight) if raw_weight not in (None, '', 'null') else None

                if birds_val is not None or weight_val is not None:
                    db.session.add(EntryLog(
                        date=entry_date,
                        shift=shift,
                        product_id=product_id,
                        birds=birds_val,
                        weight=weight_val
                    ))

        db.session.commit()
        return jsonify({'status': 'success', 'message': f'Saved successfully for {shift.upper()} shift!'})

    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/verify-supervisor-pin', methods=['POST'])
def verify_supervisor_pin():
    data = request.get_json(silent=True) or {}
    if verify_system_pin(data.get('auth_pin')):
        return jsonify({'status': 'success'})
    return jsonify({'status': 'error', 'message': 'Invalid supervisor PIN.'}), 403

# --- SUMMARY & PRODUCT MANAGEMENT ROUTES ---

@app.route('/products', methods=['GET', 'POST'])
def products_manager():
    selected_date_str = request.args.get('date') or datetime.now(timezone.utc).strftime('%Y-%m-%d')

    if request.method == 'POST':
        code = request.form.get('code').strip()
        name = request.form.get('name').strip()
        if code and name:
            existing = Product.query.filter_by(code=code).first()
            if existing:
                flash(f"Product code {code} already exists!", "danger")
            else:
                db.session.add(Product(code=code, name=name))
                db.session.commit()
                flash(f"Product '{code} - {name}' added successfully!", "success")
        return redirect(url_for('products_manager', date=selected_date_str))

    all_products = Product.query.order_by(Product.code).all()
    return render_template('products.html', products=all_products, current_date=selected_date_str)

@app.route('/products/edit/<int:id>', methods=['POST'])
def edit_product(id):
    selected_date_str = request.args.get('date') or datetime.now(timezone.utc).strftime('%Y-%m-%d')
    product = Product.query.get(id)
    if not product:
        flash("Product not found.", "danger")
        return redirect(url_for('products_manager', date=selected_date_str))
        
    code = request.form.get('code').strip()
    name = request.form.get('name').strip()
    
    if code and name:
        existing = Product.query.filter(Product.code == code, Product.id != id).first()
        if existing:
            flash(f"Product code {code} is already in use by another product!", "danger")
        else:
            product.code = code
            product.name = name
            db.session.commit()
            flash("Product updated successfully!", "success")

    return redirect(url_for('products_manager', date=selected_date_str))

@app.route('/products/delete/<int:id>', methods=['POST'])
def delete_product(id):
    selected_date_str = request.args.get('date') or datetime.now(timezone.utc).strftime('%Y-%m-%d')
    if not verify_system_pin(request.form.get('auth_pin')):
        flash("A valid supervisor PIN is required to delete a product.", "danger")
        return redirect(url_for('products_manager', date=selected_date_str))

    product = Product.query.get(id)
    if product:
        EntryLog.query.filter_by(product_id=id).delete()
        db.session.delete(product)
        db.session.commit()
        flash(f"Product '{product.code}' and its log history deleted successfully.", "success")
    else:
        flash("Product not found.", "danger")

    return redirect(url_for('products_manager', date=selected_date_str))

@app.route('/settings', methods=['GET', 'POST'])
def settings():
    if request.method == 'POST':
        current_pin = request.form.get('current_pin')
        new_pin = request.form.get('new_pin', '').strip()
        confirm_pin = request.form.get('confirm_pin', '').strip()

        if not verify_system_pin(current_pin):
            flash("The current supervisor PIN is incorrect.", "danger")
        elif not new_pin:
            flash("Enter a new supervisor PIN.", "danger")
        elif new_pin != confirm_pin:
            flash("The new PIN and confirmation do not match.", "danger")
        else:
            setting = SystemSetting.query.filter_by(key='master_pin').first()
            setting.value = new_pin
            db.session.commit()
            flash("Supervisor PIN updated successfully.", "success")
        return redirect(url_for('settings'))

    return render_template('settings.html')

@app.route('/summary', methods=['GET', 'POST'])
def summary():
    selected_date = request.args.get('date') or request.form.get('date') or datetime.now(timezone.utc).strftime('%Y-%m-%d')
    query_date = datetime.strptime(selected_date, '%Y-%m-%d').date()

    if request.method == 'POST':
        if query_date < datetime.now(timezone.utc).date() and not verify_system_pin(request.form.get('auth_pin')):
            flash("A valid supervisor PIN is required to edit historical summary data.", "danger")
            return redirect(url_for('summary', date=selected_date))

        day_b_birds = int(request.form.get('day_before_birds') or 0)
        day_b_weight = float(request.form.get('day_before_weight') or 0.0)
        night_b_birds = int(request.form.get('night_before_birds') or 0)
        night_b_weight = float(request.form.get('night_before_weight') or 0.0)

        summary_input = ShiftSummaryInput.query.filter_by(date=selected_date).first()
        if not summary_input:
            summary_input = ShiftSummaryInput(date=selected_date)
            db.session.add(summary_input)

        summary_input.day_before_birds = day_b_birds
        summary_input.day_before_weight = day_b_weight
        summary_input.night_before_birds = night_b_birds
        summary_input.night_before_weight = night_b_weight
        
        db.session.commit()
        flash(f"Before-Process data saved for {selected_date}!", "success")
        return redirect(url_for('summary', date=selected_date))

    summary_input = ShiftSummaryInput.query.filter_by(date=selected_date).first()
    products = Product.query.order_by(Product.code).all()
    logs = EntryLog.query.filter_by(date=query_date).all()

    log_map = {}
    for log in logs:
        if log.product_id not in log_map:
            log_map[log.product_id] = {'day_birds': 0, 'day_weight': 0.0, 'night_birds': 0, 'night_weight': 0.0}
        
        if log.shift == 'day':
            log_map[log.product_id]['day_birds'] += (log.birds or 0)
            log_map[log.product_id]['day_weight'] += (log.weight or 0.0)
        elif log.shift == 'night':
            log_map[log.product_id]['night_birds'] += (log.birds or 0)
            log_map[log.product_id]['night_weight'] += (log.weight or 0.0)

    product_summary_list = []
    tot_day_after_birds = 0
    tot_day_after_weight = 0.0
    tot_night_after_birds = 0
    tot_night_after_weight = 0.0

    for p in products:
        p_data = log_map.get(p.id, {'day_birds': 0, 'day_weight': 0.0, 'night_birds': 0, 'night_weight': 0.0})

        d_birds = p_data['day_birds']
        d_weight = p_data['day_weight']
        n_birds = p_data['night_birds']
        n_weight = p_data['night_weight']

        tot_day_after_birds += d_birds
        tot_day_after_weight += d_weight
        tot_night_after_birds += n_birds
        tot_night_after_weight += n_weight

        product_summary_list.append({
            'code': p.code,
            'name': p.name,
            'day_birds': d_birds,
            'day_weight': d_weight,
            'night_birds': n_birds,
            'night_weight': n_weight,
            'total_birds': d_birds + n_birds,
            'total_weight': d_weight + n_weight
        })

    day_b_birds = summary_input.day_before_birds if summary_input else 0
    day_b_weight = summary_input.day_before_weight if summary_input else 0.0
    day_yield_pct = (tot_day_after_weight / day_b_weight * 100) if day_b_weight > 0 else 0.0
    day_avg_live_wt = (day_b_weight / day_b_birds) if day_b_birds > 0 else 0.0
    day_avg_proc_wt = (tot_day_after_weight / tot_day_after_birds) if tot_day_after_birds > 0 else 0.0

    night_b_birds = summary_input.night_before_birds if summary_input else 0
    night_b_weight = summary_input.night_before_weight if summary_input else 0.0
    night_yield_pct = (tot_night_after_weight / night_b_weight * 100) if night_b_weight > 0 else 0.0
    night_avg_live_wt = (night_b_weight / night_b_birds) if night_b_birds > 0 else 0.0
    night_avg_proc_wt = (tot_night_after_weight / tot_night_after_birds) if tot_night_after_birds > 0 else 0.0

    grand_before_birds = day_b_birds + night_b_birds
    grand_before_weight = day_b_weight + night_b_weight
    grand_after_birds = tot_day_after_birds + tot_night_after_birds
    grand_after_weight = tot_day_after_weight + tot_night_after_weight
    grand_yield_pct = (grand_after_weight / grand_before_weight * 100) if grand_before_weight > 0 else 0.0

    return render_template(
        'summary.html',
        selected_date=selected_date,
        summary_input=summary_input,
        product_summary_list=product_summary_list,
        tot_day_after_birds=tot_day_after_birds,
        tot_day_after_weight=tot_day_after_weight,
        tot_night_after_birds=tot_night_after_birds,
        tot_night_after_weight=tot_night_after_weight,
        day_yield_pct=day_yield_pct,
        day_avg_live_wt=day_avg_live_wt,
        day_avg_proc_wt=day_avg_proc_wt,
        night_yield_pct=night_yield_pct,
        night_avg_live_wt=night_avg_live_wt,
        night_avg_proc_wt=night_avg_proc_wt,
        grand_before_birds=grand_before_birds,
        grand_before_weight=grand_before_weight,
        grand_after_birds=grand_after_birds,
        grand_after_weight=grand_after_weight,
        grand_yield_pct=grand_yield_pct
    )

@app.route('/final-summary', methods=['GET'])
def final_summary():
    selected_date = request.args.get('date') or datetime.now(timezone.utc).strftime('%Y-%m-%d')
    query_date = datetime.strptime(selected_date, '%Y-%m-%d').date()

    summary_input = ShiftSummaryInput.query.filter_by(date=selected_date).first()
    products = Product.query.order_by(Product.code).all()
    logs = EntryLog.query.filter_by(date=query_date).all()

    log_map = {}
    for log in logs:
        if log.product_id not in log_map:
            log_map[log.product_id] = {'day_birds': 0, 'day_weight': 0.0, 'night_birds': 0, 'night_weight': 0.0}
        
        if log.shift == 'day':
            log_map[log.product_id]['day_birds'] += (log.birds or 0)
            log_map[log.product_id]['day_weight'] += (log.weight or 0.0)
        elif log.shift == 'night':
            log_map[log.product_id]['night_birds'] += (log.birds or 0)
            log_map[log.product_id]['night_weight'] += (log.weight or 0.0)

    product_summary_list = []
    tot_day_after_birds = 0
    tot_day_after_weight = 0.0
    tot_night_after_birds = 0
    tot_night_after_weight = 0.0

    for p in products:
        p_data = log_map.get(p.id, {'day_birds': 0, 'day_weight': 0.0, 'night_birds': 0, 'night_weight': 0.0})

        d_birds = p_data['day_birds']
        d_weight = p_data['day_weight']
        n_birds = p_data['night_birds']
        n_weight = p_data['night_weight']

        tot_day_after_birds += d_birds
        tot_day_after_weight += d_weight
        tot_night_after_birds += n_birds
        tot_night_after_weight += n_weight

        product_summary_list.append({
            'code': p.code,
            'name': p.name,
            'day_birds': d_birds,
            'day_weight': d_weight,
            'night_birds': n_birds,
            'night_weight': n_weight,
            'total_birds': d_birds + n_birds,
            'total_weight': d_weight + n_weight
        })

    day_before_wt = summary_input.day_before_weight if summary_input else 0.0
    day_before_birds = summary_input.day_before_birds if summary_input else 0
    night_before_wt = summary_input.night_before_weight if summary_input else 0.0
    night_before_birds = summary_input.night_before_birds if summary_input else 0

    day_yield_pct = (tot_day_after_weight / day_before_wt * 100) if day_before_wt > 0 else 0.0
    day_avg_live_wt = (day_before_wt / day_before_birds) if day_before_birds > 0 else 0.0
    day_avg_proc_wt = (tot_day_after_weight / tot_day_after_birds) if tot_day_after_birds > 0 else 0.0

    night_yield_pct = (tot_night_after_weight / night_before_wt * 100) if night_before_wt > 0 else 0.0
    night_avg_live_wt = (night_before_wt / night_before_birds) if night_before_birds > 0 else 0.0
    night_avg_proc_wt = (tot_night_after_weight / tot_night_after_birds) if tot_night_after_birds > 0 else 0.0

    grand_before_wt = night_before_wt + day_before_wt
    grand_after_wt = tot_night_after_weight + tot_day_after_weight
    grand_yield_pct = (grand_after_wt / grand_before_wt * 100) if grand_before_wt > 0 else 0.0

    return render_template(
        'final_summary.html',
        selected_date=selected_date,
        summary_input=summary_input,
        product_summary_list=product_summary_list,
        tot_night_after_birds=tot_night_after_birds,
        tot_night_after_weight=tot_night_after_weight,
        tot_day_after_birds=tot_day_after_birds,
        tot_day_after_weight=tot_day_after_weight,
        night_yield_pct=night_yield_pct,
        day_yield_pct=day_yield_pct,
        grand_yield_pct=grand_yield_pct,
        night_avg_live_wt=night_avg_live_wt,
        night_avg_proc_wt=night_avg_proc_wt,
        day_avg_live_wt=day_avg_live_wt,
        day_avg_proc_wt=day_avg_proc_wt
    )

@app.route('/product-breakdown', methods=['GET'])
def product_breakdown():
    selected_date = request.args.get('date') or datetime.now(timezone.utc).strftime('%Y-%m-%d')
    query_date = datetime.strptime(selected_date, '%Y-%m-%d').date()

    products = Product.query.order_by(Product.code).all()
    logs = EntryLog.query.filter_by(date=query_date).all()

    log_map = {}
    for log in logs:
        if log.product_id not in log_map:
            log_map[log.product_id] = {'day_birds': 0, 'day_weight': 0.0, 'night_birds': 0, 'night_weight': 0.0}

        if log.shift == 'day':
            log_map[log.product_id]['day_birds'] += (log.birds or 0)
            log_map[log.product_id]['day_weight'] += (log.weight or 0.0)
        elif log.shift == 'night':
            log_map[log.product_id]['night_birds'] += (log.birds or 0)
            log_map[log.product_id]['night_weight'] += (log.weight or 0.0)

    product_summary_list = []
    tot_day_after_birds = 0
    tot_day_after_weight = 0.0
    tot_night_after_birds = 0
    tot_night_after_weight = 0.0

    for p in products:
        p_data = log_map.get(p.id, {'day_birds': 0, 'day_weight': 0.0, 'night_birds': 0, 'night_weight': 0.0})

        d_birds = p_data['day_birds']
        d_weight = p_data['day_weight']
        n_birds = p_data['night_birds']
        n_weight = p_data['night_weight']

        tot_day_after_birds += d_birds
        tot_day_after_weight += d_weight
        tot_night_after_birds += n_birds
        tot_night_after_weight += n_weight

        if d_birds or d_weight or n_birds or n_weight:
            product_summary_list.append({
                'code': p.code,
                'name': p.name,
                'day_birds': d_birds,
                'day_weight': d_weight,
                'night_birds': n_birds,
                'night_weight': n_weight,
                'total_birds': d_birds + n_birds,
                'total_weight': d_weight + n_weight
            })

    grand_total_birds = tot_day_after_birds + tot_night_after_birds
    grand_total_weight = tot_day_after_weight + tot_night_after_weight

    return render_template(
        'product_breakdown.html',
        selected_date=selected_date,
        product_summary_list=product_summary_list,
        tot_day_after_birds=tot_day_after_birds,
        tot_day_after_weight=tot_day_after_weight,
        tot_night_after_birds=tot_night_after_birds,
        tot_night_after_weight=tot_night_after_weight,
        grand_total_birds=grand_total_birds,
        grand_total_weight=grand_total_weight
    )

@app.route('/summary/delete', methods=['POST'])
def delete_summary():
    selected_date = request.form.get('date')
    if not verify_system_pin(request.form.get('auth_pin')):
        flash("A valid supervisor PIN is required to delete summary data.", "danger")
        return redirect(url_for('summary', date=selected_date))

    if selected_date:
        ShiftSummaryInput.query.filter_by(date=selected_date).delete()
        db.session.commit()
        flash(f"Summary data for {selected_date} deleted successfully.")
    return redirect(url_for('summary', date=selected_date))

@app.route('/log/delete', methods=['POST'])
def delete_log_entries():
    selected_date = request.form.get('date')
    if not verify_system_pin(request.form.get('auth_pin')):
        flash("A valid supervisor PIN is required to delete production logs.", "danger")
        return redirect(url_for('home', date=selected_date))

    if selected_date:
        target_date = datetime.strptime(selected_date, '%Y-%m-%d').date()
        EntryLog.query.filter_by(date=target_date).delete()
        db.session.commit()
        flash(f"All production quantities for {selected_date} have been deleted.", "success")
    return redirect(url_for('home', date=selected_date))

if __name__ == '__main__':
    app.run(debug=True)
