from flask import Flask, jsonify, render_template, request, redirect, url_for, session, flash
from flask_mysqldb import MySQL
import MySQLdb.cursors
import re
from datetime import datetime, timedelta
import json

app = Flask(__name__)

# Configuration
app.secret_key = 'your_secret_key'
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = '********'
app.config['MYSQL_DB'] = 'smartstore_new'
app.config['MYSQL_CURSORCLASS'] = 'DictCursor'

mysql = MySQL(app)

# Login route
@app.route('/', methods=['GET', 'POST'])
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST' and 'email' in request.form and 'password' in request.form:
        email = request.form['email']
        password = request.form['password']
        
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute('SELECT * FROM users WHERE email = %s AND password = %s', (email, password))
        user = cursor.fetchone()
        
        if user:
            session['loggedin'] = True
            session['user_id'] = user['id']
            session['username'] = user['username']
            flash('Login successful!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Incorrect email/password!', 'danger')
    
    return render_template('login.html')

# Registration route
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').lower().strip()
        password = request.form.get('password', '').strip()

        # Basic validation
        if not all([username, email, password]):
            flash('Please fill out all fields!', 'danger')
            return render_template('register.html')
                
                
        # Minimum password length check
        if len(password) < 6:
            flash('Password must be at least 6 characters long!', 'danger')
            return render_template('register.html')


        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

        try:
            # 1. Uniqueness check (server-side)
            cursor.execute('SELECT 1 FROM users WHERE email = %s OR username = %s LIMIT 1', (email, username))
            if cursor.fetchone():
                flash('Email or username is already taken!', 'danger')
                return render_template('register.html')

            # 2. Create user
            cursor.execute(
                'INSERT INTO users (username, email, password) VALUES (%s, %s, %s)',
                (username, email, password)
            )
            mysql.connection.commit()
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('login'))

        except MySQLdb.IntegrityError as e:
            mysql.connection.rollback()
            if 'email' in str(e):
                flash('This email is already in use!', 'danger')
            elif 'username' in str(e):
                flash('This username is already in use!', 'danger')
            else:
                flash('There was a problem with registration!', 'danger')
            return render_template('register.html')

        except Exception as e:
            mysql.connection.rollback()
            flash('System error! Please try again later.', 'danger')
            return render_template('register.html')

        finally:
            cursor.close()

    return render_template('register.html')

# check_availability route
@app.route('/check_availability')
def check_availability():
    email = request.args.get('email', '').lower().strip()
    username = request.args.get('username', '').strip()
    
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    response = {
        'email_available': True,
        'username_available': True,
        'message': ''
    }

    try:
        if email:
            cursor.execute('SELECT 1 FROM users WHERE email = %s LIMIT 1', (email,))
            response['email_available'] = cursor.fetchone() is None

        if username:
            cursor.execute('SELECT 1 FROM users WHERE username = %s LIMIT 1', (username,))
            response['username_available'] = cursor.fetchone() is None

    except Exception as e:
        response['message'] = 'There was an error during availability check'
    
    finally:
        cursor.close()

    return jsonify(response)


# Dashboard route
@app.route('/dashboard')
def dashboard():
    if 'loggedin' in session:
        # Get counts for dashboard
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        
        # Product count
        cursor.execute('SELECT COUNT(*) as product_count FROM products')
        product_count = cursor.fetchone()['product_count']
        
        # Low stock count
        cursor.execute('SELECT COUNT(*) as low_stock FROM products WHERE quantity < 5')
        low_stock = cursor.fetchone()['low_stock']
        
        # Today's sales
        today = datetime.now().strftime('%Y-%m-%d')
        cursor.execute('SELECT SUM(total_amount) as today_sales FROM orders WHERE DATE(created_at) = %s', (today,))
        today_sales = cursor.fetchone()['today_sales'] or 0
        
        return render_template('dashboard.html', 
                             username=session['username'],
                             product_count=product_count,
                             low_stock=low_stock,
                             today_sales=today_sales)
    
    return redirect(url_for('login'))

# Products management
# Products management route - updated for soft delete
@app.route('/products', methods=['GET', 'POST'])
def products():
    if 'loggedin' not in session:
        return redirect(url_for('login'))
    
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    if request.method == 'POST':
        # Add new product
        if 'add_product' in request.form:
            name = request.form['name']
            price = request.form['price']
            quantity = request.form['quantity']
            unit = request.form['unit']
            category = request.form['category']
            description = request.form['description']
            
            cursor.execute('''
                INSERT INTO products (name, price, quantity, unit, category, description)
                VALUES (%s, %s, %s, %s, %s, %s)
            ''', (name, price, quantity, unit, category, description))
            
            # Log stock change
            product_id = cursor.lastrowid
            cursor.execute('''
                INSERT INTO stock_log (product_id, old_quantity, new_quantity, change_type, user_id)
                VALUES (%s, %s, %s, %s, %s)
            ''', (product_id, 0, quantity, 'manual', session['user_id']))
            
            mysql.connection.commit()
            flash('Product added successfully!', 'success')
        
        # # Delete product (soft delete)
        # elif 'delete_product' in request.form:
        #     product_id = request.form['product_id']
        #     cursor.execute('''
        #         UPDATE products 
        #         SET is_deleted = TRUE, deleted_at = CURRENT_TIMESTAMP
        #         WHERE id = %s
        #     ''', (product_id,))
        #     mysql.connection.commit()
        #     flash('Product marked as deleted!', 'success')
    
    # Get all active products
    cursor.execute('SELECT * FROM products WHERE is_deleted = FALSE ORDER BY name')
    products = cursor.fetchall()
    
    return render_template('products.html', products=products)

# Add this new route in app.py (around line 200, with other product-related routes)
@app.route('/update_stock/<int:product_id>', methods=['GET', 'POST'])
def update_stock(product_id):
    if 'loggedin' not in session:
        return redirect(url_for('login'))
    
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    if request.method == 'POST':
        quantity_to_add = int(request.form['quantity'])
        
        # Get current quantity
        cursor.execute('SELECT quantity FROM products WHERE id = %s', (product_id,))
        product = cursor.fetchone()
        current_quantity = product['quantity']
        new_quantity = current_quantity + quantity_to_add
        
        # Update product quantity
        cursor.execute('UPDATE products SET quantity = %s WHERE id = %s', 
                      (new_quantity, product_id))
        
        # Log stock change
        cursor.execute('''
            INSERT INTO stock_log (product_id, old_quantity, new_quantity, change_type, user_id)
            VALUES (%s, %s, %s, %s, %s)
        ''', (product_id, current_quantity, new_quantity, 'purchase', session['user_id']))
        
        mysql.connection.commit()
        flash(f'Stock updated successfully! Added {quantity_to_add} items.', 'success')
        return redirect(url_for('products'))
    
    # Get product info for display
    cursor.execute('SELECT * FROM products WHERE id = %s', (product_id,))
    product = cursor.fetchone()
    
    return render_template('update_stock.html', product=product)

# app.py-তে নিচের রাউটগুলো যোগ করুন (অন্যান্য product রাউটের সাথে)

@app.route('/edit_product/<int:product_id>', methods=['GET', 'POST'])
def edit_product(product_id):
    if 'loggedin' not in session:
        return redirect(url_for('login'))
    
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    if request.method == 'POST':
        name = request.form['name']
        price = float(request.form['price'])
        quantity = int(request.form['quantity'])
        unit = request.form['unit']
        category = request.form.get('category', '')
        description = request.form.get('description', '')
        
        # Get old price for logging
        cursor.execute('SELECT price FROM products WHERE id = %s', (product_id,))
        old_price = cursor.fetchone()['price']
        
        # Update product
        cursor.execute('''
            UPDATE products 
            SET name=%s, price=%s, quantity=%s, unit=%s, category=%s, description=%s
            WHERE id=%s
        ''', (name, price, quantity, unit, category, description, product_id))
        
        # Log price change if price was modified
        if old_price != price:
            cursor.execute('''
                INSERT INTO price_log (product_id, old_price, new_price, user_id)
                VALUES (%s, %s, %s, %s)
            ''', (product_id, old_price, price, session['user_id']))
        
        mysql.connection.commit()
        flash('Product updated successfully!', 'success')
        return redirect(url_for('products'))
    
    # Get product info
    cursor.execute('SELECT * FROM products WHERE id = %s', (product_id,))
    product = cursor.fetchone()
    
    return render_template('edit_product.html', product=product)

# app.py-তে নিচের রাউট যোগ করুন
@app.route('/price_history/<int:product_id>')
def price_history(product_id):
    if 'loggedin' not in session:
        return redirect(url_for('login'))
    
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    # Get product info
    cursor.execute('SELECT id, name FROM products WHERE id = %s', (product_id,))
    product = cursor.fetchone()
    
    # Get price history
    cursor.execute('''
        SELECT pl.old_price, pl.new_price, pl.changed_at, u.username
        FROM price_log pl
        LEFT JOIN users u ON pl.user_id = u.id
        WHERE pl.product_id = %s
        ORDER BY pl.changed_at DESC
    ''', (product_id,))
    price_history = cursor.fetchall()
    
    return render_template('price_history.html', 
                         product=product,
                         price_history=price_history)

# Sales reports
@app.route('/sales')
def sales():
    if 'loggedin' not in session:
        return redirect(url_for('login'))
    
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    # Daily sales
    cursor.execute('''
        SELECT DATE(created_at) as date, SUM(total_amount) as total
        FROM orders
        GROUP BY DATE(created_at)
        ORDER BY date DESC
        LIMIT 30
    ''')
    daily_sales = cursor.fetchall()
    
    # Monthly profit/loss (simplified - assuming cost is 70% of revenue)
    cursor.execute('''
        SELECT 
            DATE_FORMAT(created_at, '%Y-%m') as month,
            SUM(total_amount) as revenue,
            SUM(total_amount) * 0.7 as cost,
            SUM(total_amount) * 0.3 as profit
        FROM orders
        GROUP BY DATE_FORMAT(created_at, '%Y-%m')
        ORDER BY month DESC
        LIMIT 12
    ''')
    monthly_reports = cursor.fetchall()
    
    # Best selling products
    cursor.execute('''
        SELECT p.name, SUM(od.quantity) as total_quantity, SUM(od.total_price) as total_sales
        FROM order_details od
        JOIN products p ON od.product_id = p.id
        GROUP BY p.name
        ORDER BY total_quantity DESC
        LIMIT 10
    ''')
    best_sellers = cursor.fetchall()
    
    return render_template('sales.html', 
                         daily_sales=daily_sales,
                         monthly_reports=monthly_reports,
                         best_sellers=best_sellers)

# Inventory management
@app.route('/inventory')
def inventory():
    if 'loggedin' not in session:
        return redirect(url_for('login'))
    
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    # Current stock
    cursor.execute('''
        SELECT id, name, quantity, unit, 
               CASE WHEN quantity = 0 THEN 'Out of Stock'
                    WHEN quantity < 5 THEN 'Low Stock'
                    ELSE 'In Stock' END as status
        FROM products
        ORDER BY status, name
    ''')
    inventory = cursor.fetchall()
    
    # Stock history
    cursor.execute('''
        SELECT sl.id, p.name, sl.old_quantity, sl.new_quantity, 
               sl.change_type, sl.created_at, u.username
        FROM stock_log sl
        JOIN products p ON sl.product_id = p.id
        LEFT JOIN users u ON sl.user_id = u.id
        ORDER BY sl.created_at DESC
        LIMIT 50
    ''')
    stock_history = cursor.fetchall()
    
    return render_template('inventory.html', 
                         inventory=inventory,
                         stock_history=stock_history)

#Point of Sales route
# Update the point_of_sale route in app.py
@app.route('/pos', methods=['GET', 'POST'])
def point_of_sale():
    if 'loggedin' not in session:
        return redirect(url_for('login'))
    
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    if request.method == 'POST':
        # Add to cart
        if 'add_to_cart' in request.form:
            product_id = request.form['product_id']
            quantity = int(request.form['quantity'])
            
            # Check product availability
            cursor.execute('SELECT quantity FROM products WHERE id = %s', (product_id,))
            product = cursor.fetchone()
            
            if not product or product['quantity'] < quantity:
                flash('Not enough stock available!', 'danger')
                return redirect(url_for('point_of_sale'))
            
            # Check if product already in cart
            cursor.execute('SELECT * FROM temp_cart WHERE product_id = %s AND user_id = %s', 
                         (product_id, session['user_id']))
            existing_item = cursor.fetchone()
            
            if existing_item:
                new_quantity = existing_item['quantity'] + quantity
                cursor.execute('UPDATE temp_cart SET quantity = %s WHERE id = %s', 
                             (new_quantity, existing_item['id']))
            else:
                cursor.execute('INSERT INTO temp_cart (product_id, quantity, user_id) VALUES (%s, %s, %s)', 
                             (product_id, quantity, session['user_id']))
            
            # Reduce stock
            new_stock = product['quantity'] - quantity
            cursor.execute('UPDATE products SET quantity = %s WHERE id = %s', 
                          (new_stock, product_id))
            
            # Log stock change
            cursor.execute('''
                INSERT INTO stock_log (product_id, old_quantity, new_quantity, change_type, user_id)
                VALUES (%s, %s, %s, %s, %s)
            ''', (product_id, product['quantity'], new_stock, 'reserved', session['user_id']))
            
            mysql.connection.commit()
            flash('Item added to cart!', 'success')
        
        # Remove from cart
        elif 'remove_from_cart' in request.form:
            cart_id = request.form['cart_id']
            
            # Get cart item details
            cursor.execute('''
                SELECT tc.product_id, tc.quantity, p.quantity as current_stock
                FROM temp_cart tc
                JOIN products p ON tc.product_id = p.id
                WHERE tc.id = %s AND tc.user_id = %s
            ''', (cart_id, session['user_id']))
            item = cursor.fetchone()
            
            if item:
                # Restore stock
                new_stock = item['current_stock'] + item['quantity']
                cursor.execute('UPDATE products SET quantity = %s WHERE id = %s', 
                             (new_stock, item['product_id']))
                
                # Log stock change
                cursor.execute('''
                    INSERT INTO stock_log (product_id, old_quantity, new_quantity, change_type, user_id)
                    VALUES (%s, %s, %s, %s, %s)
                ''', (item['product_id'], item['current_stock'], new_stock, 'restored', session['user_id']))
                
                # Remove from cart
                cursor.execute('DELETE FROM temp_cart WHERE id = %s AND user_id = %s', 
                             (cart_id, session['user_id']))
                
                mysql.connection.commit()
                flash('Item removed from cart and stock restored!', 'success')
        
        # Process sale
        elif 'process_sale' in request.form:
            customer_name = request.form['customer_name'].strip()
            
            # Get cart items
            cursor.execute('''
                SELECT tc.id, p.id as product_id, p.name, p.price, tc.quantity
                FROM temp_cart tc
                JOIN products p ON tc.product_id = p.id
                WHERE tc.user_id = %s
            ''', (session['user_id'],))
            cart_items = cursor.fetchall()
            
            if not cart_items:
                flash('Cart is empty!', 'danger')
                return redirect(url_for('point_of_sale'))
            
            # Calculate total
            total_amount = sum(item['price'] * item['quantity'] for item in cart_items)
            
            # Create order
            cursor.execute('''
                INSERT INTO orders (customer_name, total_amount, user_id)
                VALUES (%s, %s, %s)
            ''', (customer_name, total_amount, session['user_id']))
            order_id = cursor.lastrowid
            
            # Add order details and update stock logs
            for item in cart_items:
                # Add to order details
                cursor.execute('''
                    INSERT INTO order_details (order_id, product_id, quantity, unit_price, total_price)
                    VALUES (%s, %s, %s, %s, %s)
                ''', (order_id, item['product_id'], item['quantity'], item['price'], 
                     item['price'] * item['quantity']))
                
                # Log stock change (from reserved to sold)
                cursor.execute('''
                    INSERT INTO stock_log (product_id, old_quantity, new_quantity, change_type, user_id)
                    VALUES (%s, %s, %s, %s, %s)
                ''', (item['product_id'], item['quantity'], 0, 'sale', session['user_id']))
            
            # Clear cart
            cursor.execute('DELETE FROM temp_cart WHERE user_id = %s', (session['user_id'],))
            
            mysql.connection.commit()
            flash(f'Sale processed successfully! Order ID: {order_id}', 'success')
            return redirect(url_for('view_receipt', order_id=order_id))
    
    # Get all available products (quantity > 0)
    cursor.execute('SELECT * FROM products WHERE quantity > 0 ORDER BY name')
    products = cursor.fetchall()
    
    # Get cart items
    cursor.execute('''
        SELECT tc.id as cart_id, p.id as product_id, p.name, p.price, tc.quantity, 
               (p.price * tc.quantity) as total
        FROM temp_cart tc
        JOIN products p ON tc.product_id = p.id
        WHERE tc.user_id = %s
    ''', (session['user_id'],))
    cart_items = cursor.fetchall()
    
    # Calculate cart total
    cart_total = sum(item['total'] for item in cart_items)
    
    return render_template('pos.html', 
                         products=products,
                         cart_items=cart_items,
                         cart_total=cart_total)

# Update the clear_cart route in app.py
@app.route('/clear_cart')
def clear_cart():
    if 'loggedin' not in session:
        return redirect(url_for('login'))
    
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    try:
        # Get all items in cart
        cursor.execute('''
            SELECT tc.product_id, tc.quantity, p.quantity as current_stock
            FROM temp_cart tc
            JOIN products p ON tc.product_id = p.id
            WHERE tc.user_id = %s
        ''', (session['user_id'],))
        cart_items = cursor.fetchall()
        
        # Restore stock for each item
        for item in cart_items:
            new_stock = item['current_stock'] + item['quantity']
            cursor.execute('UPDATE products SET quantity = %s WHERE id = %s', 
                         (new_stock, item['product_id']))
            
            # Log stock change
            cursor.execute('''
                INSERT INTO stock_log (product_id, old_quantity, new_quantity, change_type, user_id)
                VALUES (%s, %s, %s, %s, %s)
            ''', (item['product_id'], item['current_stock'], new_stock, 'restored', session['user_id']))
        
        # Clear cart
        cursor.execute('DELETE FROM temp_cart WHERE user_id = %s', (session['user_id'],))
        
        mysql.connection.commit()
        flash('Cart cleared and stock restored!', 'success')
    except Exception as e:
        mysql.connection.rollback()
        flash('Error clearing cart: ' + str(e), 'danger')
    
    return redirect(url_for('point_of_sale'))

# View receipt
@app.route('/receipt/<int:order_id>')
def view_receipt(order_id):
    if 'loggedin' not in session:
        return redirect(url_for('login'))
    
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    # Get order details
    cursor.execute('''
        SELECT o.id, o.customer_name, o.total_amount, o.created_at,
               od.product_id, p.name as product_name, od.quantity, 
               od.unit_price, od.total_price
        FROM orders o
        JOIN order_details od ON o.id = od.order_id
        JOIN products p ON od.product_id = p.id
        WHERE o.id = %s
    ''', (order_id,))
    order_details = cursor.fetchall()
    
    if not order_details:
        flash('Order not found!', 'danger')
        return redirect(url_for('point_of_sale'))
    
    return render_template('receipt.html', 
                         order=order_details[0],
                         items=order_details)

#order details route
# app.py-তে নিচের রাউটটি যোগ করুন
@app.route('/orders')
def orders():
    if 'loggedin' not in session:
        return redirect(url_for('login'))
    
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    # Get all orders with customer and user info
    cursor.execute('''
        SELECT o.id, o.customer_name, o.total_amount, o.created_at, u.username as cashier
        FROM orders o
        JOIN users u ON o.user_id = u.id
        ORDER BY o.created_at DESC
    ''')
    orders = cursor.fetchall()
    
    return render_template('orders.html', orders=orders)

@app.route('/order_details/<int:order_id>')
def order_details(order_id):
    if 'loggedin' not in session:
        return redirect(url_for('login'))
    
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    # Get order header info
    cursor.execute('''
        SELECT o.id, o.customer_name, o.total_amount, o.created_at, u.username as cashier
        FROM orders o
        JOIN users u ON o.user_id = u.id
        WHERE o.id = %s
    ''', (order_id,))
    order = cursor.fetchone()
    
    if not order:
        flash('Order not found!', 'danger')
        return redirect(url_for('orders'))
    
    # Get order details
    cursor.execute('''
        SELECT od.id, p.name as product_name, od.quantity, od.unit_price, od.total_price
        FROM order_details od
        JOIN products p ON od.product_id = p.id
        WHERE od.order_id = %s
    ''', (order_id,))
    items = cursor.fetchall()
    
    return render_template('order_details.html', order=order, items=items)

# Logout
@app.route('/logout')
def logout():
    session.pop('loggedin', None)
    session.pop('user_id', None)
    session.pop('username', None)
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)