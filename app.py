from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import json

app = Flask(__name__)
app.secret_key = 'poultry_secret_key'

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///newro_poultry.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- MODELS ---

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)

class EntryLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    shift = db.Column(db.String(10), nullable=False) # 'day' or 'night'
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    birds = db.Column(db.Integer, nullable=True)
    weight = db.Column(db.Float, nullable=True)
    raw_batches = db.Column(db.Text, nullable=True) # Stores JSON string of batch breakdown
    
    product = db.relationship('Product', backref=db.backref('logs', lazy=True))

class ShiftSummaryInput(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(10), nullable=False)
    
    day_before_birds = db.Column(db.Integer, default=0)
    day_before_weight = db.Column(db.Float, default=0.0)
    night_before_birds = db.Column(db.Integer, default=0)
    night_before_weight = db.Column(db.Float, default=0.0)

    __table_args__ = (db.UniqueConstraint('date', name='_date_summary_uc'),)

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

# --- ROUTES ---

@app.route('/', methods=['GET', 'POST'])
def home():
    selected_date_str = request.args.get('date') or request.form.get('date') or datetime.utcnow().strftime('%Y-%m-%d')
    entry_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()

    if request.method == 'POST':
        EntryLog.query.filter_by(date=entry_date).delete()
        products = Product.query.all()
        
        for product in products:
            # Process Day Shift
            day_birds = request.form.get(f'day_birds_{product.id}')
            day_weight = request.form.get(f'day_weight_{product.id}')
            day_batches = request.form.get(f'day_batches_{product.id}')
            if day_birds or day_weight:
                db.session.add(EntryLog(
                    date=entry_date, shift='day', product_id=product.id,
                    birds=int(day_birds) if day_birds else None,
                    weight=float(day_weight) if day_weight else None,
                    raw_batches=day_batches if day_batches else None
                ))

            # Process Night Shift
            night_birds = request.form.get(f'night_birds_{product.id}')
            night_weight = request.form.get(f'night_weight_{product.id}')
            night_batches = request.form.get(f'night_batches_{product.id}')
            if night_birds or night_weight:
                db.session.add(EntryLog(
                    date=entry_date, shift='night', product_id=product.id,
                    birds=int(night_birds) if night_birds else None,
                    weight=float(night_weight) if night_weight else None,
                    raw_batches=night_batches if night_batches else None
                ))
                
        db.session.commit()
        flash("Production data for both shifts saved successfully!", "success")
        return redirect(url_for('home', date=selected_date_str))
        
    products = Product.query.order_by(Product.code).all()
    logs = EntryLog.query.filter_by(date=entry_date).all()
    
    existing_logs = {}
    for log in logs:
        if log.product_id not in existing_logs:
            existing_logs[log.product_id] = {}
        if log.shift == 'day':
            existing_logs[log.product_id]['day_birds'] = log.birds
            existing_logs[log.product_id]['day_weight'] = log.weight
            existing_logs[log.product_id]['day_batches'] = log.raw_batches or ""
        elif log.shift == 'night':
            existing_logs[log.product_id]['night_birds'] = log.birds
            existing_logs[log.product_id]['night_weight'] = log.weight
            existing_logs[log.product_id]['night_batches'] = log.raw_batches or ""

    return render_template('index.html', products=products, current_date=selected_date_str, existing_logs=existing_logs)

@app.route('/products', methods=['GET', 'POST'])
def products_manager():
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
        return redirect(url_for('products_manager'))

    all_products = Product.query.order_by(Product.code).all()
    return render_template('products.html', products=all_products)

@app.route('/products/edit/<int:id>', methods=['POST'])
def edit_product(id):
    product = Product.query.get(id)
    if not product:
        flash("Product not found.", "danger")
        return redirect(url_for('products_manager'))
        
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
    return redirect(url_for('products_manager'))

@app.route('/products/delete/<int:id>', methods=['POST'])
def delete_product(id):
    product = Product.query.get(id)
    if product:
        EntryLog.query.filter_by(product_id=id).delete()
        db.session.delete(product)
        db.session.commit()
        flash(f"Product '{product.code}' and its log history deleted successfully.", "success")
    else:
        flash("Product not found.", "danger")
    return redirect(url_for('products_manager'))

@app.route('/summary', methods=['GET', 'POST'])
def summary():
    selected_date = request.args.get('date') or request.form.get('date') or datetime.today().strftime('%Y-%m-%d')
    query_date = datetime.strptime(selected_date, '%Y-%m-%d').date()

    if request.method == 'POST':
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
            log_map[log.product_id] = {'day': None, 'night': None}
        log_map[log.product_id][log.shift] = log

    product_summary_list = []
    tot_day_after_birds = 0
    tot_day_after_weight = 0.0
    tot_night_after_birds = 0
    tot_night_after_weight = 0.0

    for p in products:
        day_log = log_map.get(p.id, {}).get('day')
        night_log = log_map.get(p.id, {}).get('night')

        d_birds = (day_log.birds if day_log and day_log.birds else 0)
        d_weight = (day_log.weight if day_log and day_log.weight else 0.0)
        n_birds = (night_log.birds if night_log and night_log.birds else 0)
        n_weight = (night_log.weight if night_log and night_log.weight else 0.0)

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

@app.route('/summary/delete', methods=['POST'])
def delete_summary():
    selected_date = request.form.get('date')
    if selected_date:
        ShiftSummaryInput.query.filter_by(date=selected_date).delete()
        db.session.commit()
        flash(f"Summary data for {selected_date} deleted successfully.")
    return redirect(url_for('summary', date=selected_date))

@app.route('/log/delete', methods=['POST'])
def delete_log_entries():
    selected_date = request.form.get('date')
    if selected_date:
        target_date = datetime.strptime(selected_date, '%Y-%m-%d').date()
        EntryLog.query.filter_by(date=target_date).delete()
        db.session.commit()
        flash(f"All production quantities for {selected_date} have been deleted.", "success")
    return redirect(url_for('home', date=selected_date))

if __name__ == '__main__':
    app.run(debug=True)