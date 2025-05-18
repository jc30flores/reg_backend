import os
from flask import Flask, jsonify, request
from flask_cors import CORS, cross_origin
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor

# Load environment variables from .env file
load_dotenv()

# Database configuration from environment
DB_HOST = os.getenv("PGHOST", "cfls9h51f4i86c.cluster-czrs8kj4isg7.us-east-1.rds.amazonaws.com")
DB_NAME = os.getenv("PGDATABASE", "dfc2jmocqkio6k")
DB_USER = os.getenv("PGUSER", "uf6s7k0lvso94d")
DB_PASSWORD = os.getenv("PGPASSWORD", "p26334802041005114bc98db3c5f0766326cca1abea7a6899ef860a12e79b95e8")
DB_PORT = os.getenv("PGPORT", "5432")

def get_db_connection():
    """
    Establishes a new database connection using psycopg2.
    Returns a connection object.
    """
    conn = psycopg2.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        port=DB_PORT
    )
    return conn

# Initialize Flask app
app = Flask(__name__)
# Configure CORS to allow requests from the frontend for all /api/*
# Configure CORS to allow all origins and methods for API and elements endpoints
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)
# Ensure 'shape', 'rotation', and 'color' columns exist in 'tables'
try:
    conn = get_db_connection()
    cur = conn.cursor()
    # Add shape column if missing
    cur.execute("ALTER TABLE tables ADD COLUMN IF NOT EXISTS shape TEXT;")
    # Add rotation and color columns for table orientation and coloring
    cur.execute("ALTER TABLE tables ADD COLUMN IF NOT EXISTS rotation INT NOT NULL DEFAULT 0;")
    cur.execute("ALTER TABLE tables ADD COLUMN IF NOT EXISTS color TEXT;")
    conn.commit()
    cur.close()
    conn.close()
except Exception as e:
    print(f"Warning: could not ensure 'shape' column: {e}")

# Ensure map_elements table exists for custom map objects
try:
    conn = get_db_connection()
    cur = conn.cursor()
    # Create the map_elements table if it does not exist (with color column support)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS map_elements (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        type TEXT NOT NULL,
        position_x INT NOT NULL,
        position_y INT NOT NULL,
        width INT NOT NULL DEFAULT 0,
        height INT NOT NULL DEFAULT 0,
        rotation INT NOT NULL DEFAULT 0,
        content TEXT,
        color TEXT,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        updated_at TIMESTAMPTZ DEFAULT NOW()
    );
    """)
    conn.commit()
    cur.close()
    conn.close()
except Exception as e:
    print(f"Warning: could not ensure 'map_elements' table: {e}")

"""
Ensure 'color' and 'section_id' columns exist in 'map_elements', and 'access_code' column in 'employees'.
"""
try:
    conn = get_db_connection()
    cur = conn.cursor()
    # Add color column if missing
    cur.execute("ALTER TABLE map_elements ADD COLUMN IF NOT EXISTS color TEXT;")
    # Add section_id column to link elements to a restaurant section
    cur.execute("ALTER TABLE map_elements ADD COLUMN IF NOT EXISTS section_id UUID;")
    # Add font_size and font_style columns for text elements
    cur.execute("ALTER TABLE map_elements ADD COLUMN IF NOT EXISTS font_size INT;")
    cur.execute("ALTER TABLE map_elements ADD COLUMN IF NOT EXISTS font_style TEXT;")
    conn.commit()
    cur.close()
    conn.close()
except Exception as e:
    print(f"Warning: could not ensure 'color' or 'section_id' columns: {e}")

# Ensure 'access_code' column exists in 'employees'
try:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("ALTER TABLE employees ADD COLUMN IF NOT EXISTS access_code TEXT;")
    conn.commit()
    cur.close()
    conn.close()
except Exception as e:
    print(f"Warning: could not ensure 'access_code' column in 'employees': {e}")

### Map Elements Endpoints ###
@app.route('/api/elements', methods=['GET'])
@cross_origin()
def get_elements():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM map_elements;")
    elems = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify(elems)

@app.route('/api/elements', methods=['POST'])
@cross_origin()
def create_element():
    data = request.get_json() or {}
    columns, values, placeholders = [], [], []
    # Allow setting of type, section_id, position, size, rotation, content, and color
    for key in ['type','section_id','position_x','position_y','width','height','rotation','content','color','font_size','font_style']:
        if key in data:
            columns.append(key)
            values.append(data[key])
            placeholders.append('%s')
    if not columns:
        return jsonify({'error': 'No element data provided'}), 400
    sql = f"INSERT INTO map_elements ({', '.join(columns)}) VALUES ({', '.join(placeholders)}) RETURNING *;"
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute(sql, tuple(values))
    new_elem = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    return jsonify(new_elem), 201

@app.route('/api/elements/<string:elem_id>', methods=['PUT'])
@cross_origin()
def update_element(elem_id):
    data = request.get_json() or {}
    fields, values = [], []
    # Allow updating of type, section_id, position, size, rotation, content, and color
    for key in ['type','section_id','position_x','position_y','width','height','rotation','content','color','font_size','font_style']:
        if key in data:
            fields.append(f"{key} = %s")
            values.append(data[key])
    if not fields:
        return jsonify({'error': 'No valid fields provided'}), 400
    values.append(elem_id)
    sql = f"UPDATE map_elements SET {', '.join(fields)}, updated_at = NOW() WHERE id = %s RETURNING *;"
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute(sql, tuple(values))
    updated = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    if updated:
        return jsonify(updated)
    else:
        return jsonify({'error': 'Element not found'}), 404

@app.route('/api/elements/<string:elem_id>', methods=['DELETE'])
@cross_origin()
def delete_element(elem_id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("DELETE FROM map_elements WHERE id = %s RETURNING id;", (elem_id,))
    deleted = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    if deleted:
        return jsonify({'id': deleted['id']})
    else:
        return jsonify({'error': 'Element not found'}), 404

@app.route('/ping', methods=['GET'])
def ping():
    """Health check endpoint returning a simple pong response."""
    return jsonify({"message": "pong"})
    
@app.route('/api/tables', methods=['GET'])
def get_tables():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM tables;")
    tables = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify(tables)

@app.route('/api/tables/<string:table_id>', methods=['GET'])
def get_table(table_id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM tables WHERE id = %s;", (table_id,))
    table = cur.fetchone()
    cur.close()
    conn.close()
    if table:
        return jsonify(table)
    else:
        return jsonify({"error": "Table not found"}), 404

@app.route('/api/tables/<string:table_id>', methods=['PUT'])
def update_table(table_id):
    data = request.get_json()
    fields = []
    values = []
    # Include 'shape' field for table shape support
    # Allow updating of table orientation and color in addition to existing fields
    for key in ['number', 'capacity', 'status', 'section_id', 'position_x', 'position_y', 'width', 'height', 'shape', 'rotation', 'color']:
        if key in data:
            fields.append(f"{key} = %s")
            values.append(data[key])
    if not fields:
        return jsonify({"error": "No valid fields provided"}), 400
    fields.append("updated_at = NOW()")
    sql = f"UPDATE tables SET {', '.join(fields)} WHERE id = %s RETURNING *;"
    values.append(table_id)
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute(sql, tuple(values))
    updated = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    if updated:
        return jsonify(updated)
    else:
        return jsonify({"error": "Table not found"}), 404

@app.route('/api/tables', methods=['POST'])
def create_table():
    data = request.get_json() or {}
    columns, values, placeholders = [], [], []
    # Allow setting of rotation and color for new tables
    for key in ['number', 'capacity', 'status', 'section_id', 'position_x', 'position_y', 'width', 'height', 'shape', 'rotation', 'color']:
        if key in data:
            columns.append(key)
            values.append(data[key])
            placeholders.append('%s')
    if not columns:
        return jsonify({'error': 'No table data provided'}), 400
    sql = f"INSERT INTO tables ({', '.join(columns)}) VALUES ({', '.join(placeholders)}) RETURNING *;"
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute(sql, tuple(values))
    new_table = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    return jsonify(new_table), 201

@app.route('/api/tables/<string:table_id>', methods=['DELETE'])
def delete_table(table_id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("DELETE FROM tables WHERE id = %s RETURNING id;", (table_id,))
    deleted = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    if deleted:
        return jsonify({'id': deleted['id']})
    else:
        return jsonify({'error': 'Table not found'}), 404

@app.route('/api/menu', methods=['GET'])
def get_menu():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM menu_items;")
    items = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify(items)
    
@app.route('/api/menu', methods=['POST'])
def create_menu_item():
    data = request.get_json()
    columns, values, placeholders = [], [], []
    for key in ['name', 'price', 'category', 'image']:
        if key in data:
            columns.append(key)
            values.append(data[key])
            placeholders.append('%s')
    if not columns:
        return jsonify({'error': 'No menu item data provided'}), 400
    sql = f"INSERT INTO menu_items ({', '.join(columns)}) VALUES ({', '.join(placeholders)}) RETURNING *;"
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute(sql, tuple(values))
    new_item = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    return jsonify(new_item), 201

@app.route('/api/menu/<string:item_id>', methods=['PUT', 'DELETE'])
def modify_menu_item(item_id):
    if request.method == 'PUT':
        data = request.get_json()
        fields, values = [], []
        for key in ['name', 'price', 'category', 'image']:
            if key in data:
                fields.append(f"{key} = %s")
                values.append(data[key])
        if not fields:
            return jsonify({'error': 'No menu item data provided'}), 400
        values.append(item_id)
        sql = f"UPDATE menu_items SET {', '.join(fields)}, updated_at = NOW() WHERE id = %s RETURNING *;"
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(sql, tuple(values))
        updated = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        if updated:
            return jsonify(updated)
        else:
            return jsonify({'error': 'Menu item not found'}), 404
    else:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("DELETE FROM menu_items WHERE id = %s RETURNING id;", (item_id,))
        deleted = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        if deleted:
            return jsonify({'id': deleted['id']})
        else:
            return jsonify({'error': 'Menu item not found'}), 404

@app.route('/api/orders', methods=['POST'])
def create_order():
    data = request.get_json()
    columns = []
    values = []
    placeholders = []
    for key in ['table_number', 'server', 'status', 'subtotal', 'tax', 'tip', 'total', 'discount_type', 'discount_value', 'payment_method', 'paid', 'client_count']:
        if key in data:
            columns.append(key)
            values.append(data[key])
            placeholders.append('%s')
    if not columns:
        return jsonify({"error": "No order data provided"}), 400
    sql = f"INSERT INTO orders ({', '.join(columns)}) VALUES ({', '.join(placeholders)}) RETURNING *;"
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute(sql, tuple(values))
    new_order = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    return jsonify(new_order), 201
    
@app.route('/api/orders', methods=['GET'])
def list_orders():
    """
    Retrieve all orders.
    """
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM orders;")
    orders = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify(orders)

@app.route('/api/orders/<string:order_id>', methods=['GET'])
def get_order(order_id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM orders WHERE id = %s;", (order_id,))
    order = cur.fetchone()
    cur.close()
    conn.close()
    if order:
        return jsonify(order)
    else:
        return jsonify({"error": "Order not found"}), 404

@app.route('/api/orders/<string:order_id>', methods=['PUT'])
def update_order(order_id):
    data = request.get_json()
    fields = []
    values = []
    for key in ['status', 'payment_method', 'paid']:
        if key in data:
            fields.append(f"{key} = %s")
            values.append(data[key])
    if not fields:
        return jsonify({"error": "No valid fields provided"}), 400
    fields.append("updated_at = NOW()")
    sql = f"UPDATE orders SET {', '.join(fields)} WHERE id = %s RETURNING *;"
    values.append(order_id)
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute(sql, tuple(values))
    updated = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    if updated:
        return jsonify(updated)
    else:
        return jsonify({"error": "Order not found"}), 404

@app.route('/api/order-items/<string:order_id>', methods=['GET'])
def get_order_items(order_id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM order_items WHERE order_id = %s;", (order_id,))
    items = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify(items)

@app.route('/api/order-items', methods=['POST'])
def create_order_item():
    data = request.get_json()
    columns = []
    values = []
    placeholders = []
    for key in ['order_id', 'menu_item_id', 'quantity', 'price', 'notes', 'client_number']:
        if key in data:
            columns.append(key)
            values.append(data[key])
            placeholders.append('%s')
    if not columns:
        return jsonify({"error": "No order item data provided"}), 400
    sql = f"INSERT INTO order_items ({', '.join(columns)}) VALUES ({', '.join(placeholders)}) RETURNING *;"
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute(sql, tuple(values))
    new_item = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    return jsonify(new_item), 201

@app.route('/api/employees', methods=['GET', 'POST'])
def employees():
    """
    GET: List all employees.
    POST: Create a new employee.
    """
    if request.method == 'GET':
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM employees;")
        employees = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify(employees)
    else:
        # Create new employee
        data = request.get_json() or {}
        fields = []
        values = []
        placeholders = []
        for key in ['name', 'position', 'status', 'hourly_rate']:
            if key in data:
                fields.append(key)
                values.append(data[key])
                placeholders.append('%s')
        if not fields:
            return jsonify({'error': 'No employee data provided'}), 400
        sql = f"INSERT INTO employees ({', '.join(fields)}) VALUES ({', '.join(placeholders)}) RETURNING *;"
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(sql, tuple(values))
        new_emp = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        return jsonify(new_emp), 201

@app.route('/api/inventory', methods=['GET'])
def get_inventory():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM inventory_items;")
    inventory = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify(inventory)

@app.route('/api/inventory_items/<string:item_id>', methods=['PUT', 'DELETE'])
def modify_inventory_item(item_id):
    """
    PUT: update an existing inventory item.
    DELETE: delete an inventory item.
    """
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    if request.method == 'PUT':
        data = request.get_json() or {}
        fields = []
        values = []
        for key in ['name', 'supplier', 'quantity', 'unit', 'cost', 'image']:
            if key in data:
                fields.append(f"{key} = %s")
                values.append(data[key])
        if not fields:
            cur.close()
            conn.close()
            return jsonify({'error': 'No data provided'}), 400
        # Update timestamp
        fields.append('updated_at = NOW()')
        sql = f"UPDATE inventory_items SET {', '.join(fields)} WHERE id = %s RETURNING *;"
        values.append(item_id)
        try:
            cur.execute(sql, tuple(values))
            updated = cur.fetchone()
            conn.commit()
        except Exception as e:
            conn.rollback()
            cur.close()
            conn.close()
            return jsonify({'error': str(e)}), 500
        cur.close()
        conn.close()
        if updated:
            return jsonify(updated)
        return jsonify({'error': 'Item not found'}), 404
    else:
        # DELETE
        try:
            cur.execute("DELETE FROM inventory_items WHERE id = %s RETURNING id;", (item_id,))
            deleted = cur.fetchone()
            conn.commit()
        except Exception as e:
            conn.rollback()
            cur.close()
            conn.close()
            return jsonify({'error': str(e)}), 500
        cur.close()
        conn.close()
        if deleted:
            return jsonify({'id': deleted['id']})
        return jsonify({'error': 'Item not found'}), 404

@app.route('/api/inventory_items', methods=['POST'])
def create_inventory_item():
    """
    Create a new inventory item.
    Expected JSON body: { name, supplier, quantity, unit, cost, image? }
    """
    data = request.get_json() or {}
    # Validate required fields
    required = ['name', 'quantity', 'unit', 'cost']
    missing = [f for f in required if f not in data or data.get(f) is None]
    if missing:
        return jsonify({ 'error': f'Missing fields: {", ".join(missing)}' }), 400
    # Prepare columns and values
    cols = ['name', 'quantity', 'unit', 'cost']
    vals = [ data['name'], data['quantity'], data['unit'], data['cost'] ]
    # Optional fields
    if 'supplier' in data:
        cols.append('supplier')
        vals.append(data['supplier'])
    if 'image' in data:
        cols.append('image')
        vals.append(data['image'])
    # Use default created_at
    placeholders = ['%s'] * len(cols)
    sql = f"INSERT INTO inventory_items ({', '.join(cols)}) VALUES ({', '.join(placeholders)}) RETURNING *;"
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(sql, tuple(vals))
        new_item = cur.fetchone()
        conn.commit()
    except Exception as e:
        conn.rollback()
        cur.close()
        conn.close()
        return jsonify({ 'error': str(e) }), 500
    cur.close()
    conn.close()
    return jsonify(new_item), 201

# Restaurant sections endpoints
@app.route('/api/sections', methods=['GET', 'POST'])
def sections():
    if request.method == 'GET':
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM restaurant_sections ORDER BY name;")
        sections = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify(sections)
    else:
        # Create new section
        data = request.get_json()
        name = data.get('name')
        if not name:
            return jsonify({'error': 'Name is required'}), 400
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            "INSERT INTO restaurant_sections (name) VALUES (%s) RETURNING *;",
            (name,)
        )
        new_section = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        return jsonify(new_section), 201

@app.route('/api/sections/<string:section_id>', methods=['PUT', 'DELETE'])
def modify_section(section_id):
    if request.method == 'PUT':
        data = request.get_json()
        name = data.get('name')
        if not name:
            return jsonify({'error': 'Name is required'}), 400
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            "UPDATE restaurant_sections SET name = %s, updated_at = NOW() WHERE id = %s RETURNING *;",
            (name, section_id)
        )
        updated = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        if updated:
            return jsonify(updated)
        else:
            return jsonify({'error': 'Section not found'}), 404
    else:
        # DELETE
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM restaurant_sections WHERE id = %s RETURNING id;", (section_id,))
        deleted = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        if deleted:
            return jsonify({'id': deleted[0]})
        else:
            return jsonify({'error': 'Section not found'}), 404

# Create and delete table endpoints
@app.route('/api/tables', methods=['GET', 'POST'])
def tables_collection():
    if request.method == 'GET':
        # existing get_tables logic
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM tables;")
        tables = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify(tables)
    else:
        # Create new table
        data = request.get_json()
        # Expect fields: number, capacity, status, section_id, position_x, position_y, width, height, shape
        columns = []
        values = []
        placeholders = []
        # Include 'shape' to store table shape
        for key in ['number','capacity','status','section_id','position_x','position_y','width','height','shape']:
            if key in data:
                columns.append(key)
                values.append(data[key])
                placeholders.append('%s')
        if not columns:
            return jsonify({'error':'No valid fields provided'}),400
        sql = f"INSERT INTO tables ({', '.join(columns)}) VALUES ({', '.join(placeholders)}) RETURNING *;"
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(sql, tuple(values))
        new_table = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        return jsonify(new_table), 201

@app.route('/api/tables/<string:table_id>', methods=['GET', 'PUT', 'DELETE'])
def table_item(table_id):
    if request.method == 'GET':
        return get_table(table_id)
    elif request.method == 'PUT':
        return update_table(table_id)
    else:
        # DELETE table
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("DELETE FROM tables WHERE id = %s RETURNING id;", (table_id,))
        deleted = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        if deleted:
            return jsonify({'id': deleted['id']})
        else:
            return jsonify({'error':'Table not found'}),404

# Break history endpoints
@app.route('/api/break-history', methods=['GET', 'POST'])
def break_history_collection():
    if request.method == 'GET':
        employee_id = request.args.get('employee_id')
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        if employee_id:
            cur.execute(
                "SELECT * FROM break_history WHERE employee_id = %s ORDER BY break_start DESC;",
                (employee_id,)
            )
        else:
            cur.execute("SELECT * FROM break_history ORDER BY break_start DESC;")
        records = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify(records)
    else:
        data = request.get_json()
        cols, vals, ph = [], [], []
        for key in ['employee_id','break_start','break_end','date']:
            if key in data:
                cols.append(key)
                vals.append(data[key])
                ph.append('%s')
        if not cols:
            return jsonify({'error':'No data provided'}),400
        sql = f"INSERT INTO break_history ({', '.join(cols)}) VALUES ({', '.join(ph)}) RETURNING *;"
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(sql, tuple(vals))
        new_record = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        return jsonify(new_record),201

@app.route('/api/break-history/<string:record_id>', methods=['PUT'])
def break_history_item(record_id):
    data = request.get_json()
    fields, vals = [], []
    for key in ['employee_id','break_start','break_end','date']:
        if key in data:
            fields.append(f"{key} = %s")
            vals.append(data[key])
    if not fields:
        return jsonify({'error':'No data provided'}),400
    vals.append(record_id)
    sql = f"UPDATE break_history SET {', '.join(fields)} WHERE id = %s RETURNING *;"
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute(sql, tuple(vals))
    updated = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    if updated:
        return jsonify(updated)
    else:
        return jsonify({'error':'Record not found'}),404

# Seed mock data for menu_items and inventory_items if tables are empty
try:
    conn = get_db_connection()
    cur = conn.cursor()
    # Menu items
    cur.execute("SELECT COUNT(*) FROM menu_items;")
    if cur.fetchone()[0] == 0:
        # Seed some mock menu items across Breakfast, Lunch, Dinner
        mock_menu = [
            ('Pancakes', 5.99, 'Breakfast', 'pancakes.png'),
            ('Omelette', 6.49, 'Breakfast', 'omelette.png'),
            ('Coffee', 2.50, 'Breakfast', 'coffee.png'),
            ('BLT Sandwich', 7.50, 'Lunch', 'blt_sandwich.png'),
            ('Caesar Salad', 8.00, 'Lunch', 'caesar_salad.png'),
            ('Burger', 9.25, 'Lunch', 'burger.png'),
            ('Steak Dinner', 15.00, 'Dinner', 'steak_dinner.png'),
            ('Grilled Salmon', 14.50, 'Dinner', 'grilled_salmon.png'),
            ('Ice Cream', 4.00, 'Dessert', 'ice_cream.png')
        ]
        for name, price, category, image in mock_menu:
            cur.execute(
                "INSERT INTO menu_items (name, price, category, image) VALUES (%s, %s, %s, %s);",
                (name, price, category, image)
            )
    # Inventory items
    cur.execute("SELECT COUNT(*) FROM inventory_items;")
    if cur.fetchone()[0] == 0:
        mock_inv = [
            ('Coffee Beans', 20, 'kg', 15.0, 'Local Supplier', None),
            ('Milk', 10, 'liters', 1.2, 'Dairy Co', None),
            ('Bread Loaf', 30, 'pcs', 0.5, 'Bakery Inc', None),
            ('Lettuce', 25, 'heads', 0.8, 'Green Farms', None)
        ]
        for name, quantity, unit, cost, supplier, image in mock_inv:
            cur.execute(
                "INSERT INTO inventory_items (name, quantity, unit, cost, supplier, image) VALUES (%s, %s, %s, %s, %s, %s);",
                (name, quantity, unit, cost, supplier, image)
            )
    # Seed owner employee if none exist
    cur.execute("SELECT COUNT(*) FROM employees;")
    if cur.fetchone()[0] == 0:
        cur.execute(
            "INSERT INTO employees (name, position, status, hourly_rate, access_code) VALUES (%s, %s, %s, %s, %s);",
            ("Carlos Flores", "owner", "active", 0, "1020304")
        )
    conn.commit()
    cur.close()
    conn.close()
except Exception as e:
    print(f"Warning: could not seed mock data: {e}")

if __name__ == '__main__':
    import os
    port = int(os.getenv('FLASK_PORT', '5050'))  # usa 5050 por defecto si no existe FLASK_PORT
    app.run(host='0.0.0.0', port=port, debug=True)
