# from flask import Flask, render_template
# from flask_sqlalchemy import SQLAlchemy


# app = Flask(__name__)


# app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///newro_poultry.db'
# app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# db = SQLAlchemy(app)

# with app.app_context():
#     db.create_all()


# @app.route('/')
# def home():
#     return render_template('index.html')



# if __name__ == '__main__':
#     app.run(debug=True)


from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'poultry_secret_key'

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///newro_poultry.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- MODELS ---

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)  # e.g., NW00001
    name = db.Column(db.String(100), nullable=False)              # e.g., Fresh Chicken

class EntryLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    birds = db.Column(db.Integer, nullable=True)
    weight = db.Column(db.Float, nullable=True)
    
    product = db.relationship('Product', backref=db.backref('logs', lazy=True))

# --- DATABASE SEEDING ---
# This automatically inserts the entire paperwork catalog if the database table is empty.
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
        print("Success: All products populated from paperwork list!")

with app.app_context():
    db.create_all()
    seed_products()

# --- ROUTES ---

# 1. HOME PAGE: The Production Entry Sheet
@app.route('/', methods=['GET', 'POST'])
def home():
    if request.method == 'POST':
        date_str = request.form.get('date')
        entry_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else datetime.utcnow().date()
        
        products = Product.query.all()
        
        for product in products:
            birds = request.form.get(f'birds_{product.id}')
            weight = request.form.get(f'weight_{product.id}')
            
            # Save only if at least one field is filled out
            if birds or weight:
                log = EntryLog(
                    date=entry_date,
                    product_id=product.id,
                    birds=int(birds) if birds else None,
                    weight=float(weight) if weight else None
                )
                db.session.add(log)
                
        db.session.commit()
        flash("Production data saved successfully!", "success")
        return redirect(url_for('home'))
        
    products = Product.query.all()
    current_date = datetime.utcnow().strftime('%Y-%m-%d')
    return render_template('index.html', products=products, current_date=current_date)


# 2. PRODUCT MANAGER PAGE: Add / View Products
@app.route('/products', methods=['GET', 'POST'])
def products_manager():
    if request.method == 'POST':
        code = request.form.get('code').strip()
        name = request.form.get('name').strip()
        
        if code and name:
            # Check if product code already exists
            existing = Product.query.filter_by(code=code).first()
            if existing:
                flash(f"Product code {code} already exists!", "danger")
            else:
                new_product = Product(code=code, name=name)
                db.session.add(new_product)
                db.session.commit()
                flash(f"Product '{code} - {name}' added successfully!", "success")
        return redirect(url_for('products_manager'))

    all_products = Product.query.order_by(Product.code).all()
    return render_template('products.html', products=all_products)


if __name__ == '__main__':
    app.run(debug=True)